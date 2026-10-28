"""Explicit API routes and a shared transaction/retry boundary."""
import hashlib
import hmac
import json
from uuid import uuid4
from fastapi import APIRouter, Depends, Request, Path
from fastapi.security import APIKeyHeader
from sqlalchemy import text
from . import schemas as s, services as svc, repositories as repo, models as m
from .policy import DomainError, active, redact, utc, fail

agent_key=APIKeyHeader(name='X-API-Key',scheme_name='ServiceApiKey',auto_error=False)
admin_key=APIKeyHeader(name='X-Admin-Key',scheme_name='AdminApiKey',auto_error=False)

def authenticate(request:Request, key=Depends(agent_key)):
    expected=request.app.state.settings.api_key
    if not expected or not key or not hmac.compare_digest(key,expected):
        raise DomainError(401,'UNAUTHORIZED','Valid X-API-Key required')

def admin_auth(request:Request,key=Depends(admin_key)):
    expected=request.app.state.settings.admin_api_key
    if not expected or not key or not hmac.compare_digest(key,expected):
        raise DomainError(401,'UNAUTHORIZED','Valid X-Admin-Key required')

ERRORS={code:{'model':s.Error,'description':description} for code,description in {401:'Missing or invalid API key',404:'Unknown ticket or reference',409:'Retry conflict, invalid status or relationship conflict',422:'Invalid request or policy rejection',500:'Unexpected server error; use request_id'}.items()}
router=APIRouter(dependencies=[Depends(authenticate)],responses=ERRORS,tags=['agent-tools'])
admin=APIRouter(prefix='/admin',dependencies=[Depends(admin_auth)],responses=ERRORS,tags=['admin'])
TicketID = Path(description='Server-generated ticket ID, for example INC-1001', examples=['INC-1001'])

def run(request, operation, body=None, ticket_id=None):
    settings=request.app.state.settings
    b=body.model_dump(mode='json') if body else {}
    action=b.get('action_id')
    fingerprint=hashlib.sha256(json.dumps([operation,ticket_id,b],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with request.app.state.sessions() as db:
        # Serialize SQLite write transactions before reading retry/scope state.
        if action: db.execute(text('BEGIN IMMEDIATE'))
        try:
            if action:
                old=db.get(m.Idempotency,action)
                if old:
                    if old.fingerprint != fingerprint: fail('action_id already used with different operation or inputs','IDEMPOTENCY_CONFLICT',409)
                    return old.response
            now=utc(settings.now())
            t=repo.ticket(db,ticket_id) if ticket_id and operation!='admin_review' else None
            if t and action:
                active(t); repo.validate_sources(db,ticket_id,b)
            if operation=='get_ticket_details': result=svc.details(db,t)
            elif operation=='create_ticket': result=svc.create(db,redact(b),now)
            elif operation=='search_similar_tickets': result=svc.search(db,b)
            elif operation=='assign_ticket': result=svc.assign(db,t,b,now)
            elif operation=='add_worklog_entry': result=svc.note(db,t,b,now)
            elif operation=='record_diagnostic_result': result=svc.diagnose(db,t,b,now)
            elif operation=='resolve_ticket': result=svc.resolve(db,t,b,now)
            elif operation=='count_recent_tickets':
                svc.validate_context(db,b); result=svc.count(db,b,settings.now())
            elif operation=='find_open_global_tickets':
                svc.validate_context(db,b); result=svc.globals_search(db,b)
            elif operation=='create_global_ticket': result=svc.create_global(db,b,now)
            elif operation=='link_ticket_to_global_ticket': result=svc.link(db,t,b,now)
            elif operation.startswith('check_'):
                t=repo.ticket(db,b['ticket_id']);active(t)
                result=svc.check(db,t,b,now,operation)
            elif operation=='request_human_review': result=svc.review(db,t,b,now)
            elif operation=='notify_resolver_group': result=svc.notify(db,t,b,now)
            elif operation=='search_diagnostic_knowledge': result=svc.knowledge(db,b)
            elif operation=='admin_review':
                review=db.get(m.Review,ticket_id)
                if not review: fail('Unknown review','NOT_FOUND',404)
                t=repo.ticket(db,review.ticket_id);active(t)
                if review.state!='REQUESTED': fail('Review already decided','REVIEW_CONFLICT',409)
                review.state='APPROVED' if b['approved'] else 'REJECTED'
                review.data=redact(dict(review.data,decision=b,decided_at=now))
                svc.log(db,t,now,'ESCALATION','Human review '+review.state,b['reason'],b,actor='ADMIN')
                result=dict(review_id=review.id,ticket_id=t.ticket_id,state=review.state)
            else: raise RuntimeError('Unknown operation')
            result=redact(result)
            if action: db.add(m.Idempotency(action_id=action,fingerprint=fingerprint,response=result))
            db.commit()
            return result
        except Exception:
            db.rollback();raise

@router.get('/tickets/{ticket_id}',operation_id='get_ticket_details',response_model=s.TicketDetails,summary='Read a ticket and its recorded evidence',description='Use before deciding next steps. Returns worklogs, related global issue, evidence and latest versioned diagnosis; no hidden answers.')
def get_ticket_details(request:Request,ticket_id:str=TicketID): return run(request,'get_ticket_details',ticket_id=ticket_id)

@router.post('/tickets/search-similar',operation_id='search_similar_tickets',response_model=s.SimilarResults,summary='Retrieve resolved historical examples',description='Use to compare symptoms with resolved/closed tickets. Deterministic lexical score is not diagnostic confidence; no useful overlap returns an empty list.')
def search_similar_tickets(body:s.SearchTickets,request:Request): return run(request,'search_similar_tickets',body)

@router.post('/tickets',operation_id='create_ticket',response_model=s.TicketDetails,summary='Capture a chat issue',description='Use when no ticket exists. Requires a synthetic reporter; preserves unknown classification. Supply a stable action_id for retries.')
def create_ticket(body:s.CreateTicket,request:Request): return run(request,'create_ticket',body)

@router.post('/tickets/{ticket_id}/assignment',operation_id='assign_ticket',response_model=s.AssignmentOut,summary='Route with confidence and evidence',description='Use after diagnostic investigation. HIGH routes to requested group subject to review. MEDIUM routes to L1 preserving alternatives. LOW requires human triage.')
def assign_ticket(body:s.AssignTicket,request:Request,ticket_id:str=TicketID): return run(request,'assign_ticket',body,ticket_id)

@router.post('/tickets/{ticket_id}/worklogs',operation_id='add_worklog_entry',response_model=s.WorklogOut,summary='Record a question, response or diagnostic note',description='Use for intermediate reasoning and user responses. Cannot change status or owner. New evidence is limited to asserted user/knowledge/history sources; tool evidence comes only from checks.')
def add_worklog_entry(body:s.AddWorklog,request:Request,ticket_id:str=TicketID): return run(request,'add_worklog_entry',body,ticket_id)

@router.post('/tickets/{ticket_id}/resolution',operation_id='resolve_ticket',response_model=s.TicketDetails,summary='Resolve a safely diagnosed issue',description='Use only after approved article conditions and steps are met, with recorded diagnosis and explicit user success confirmation. Mandatory human cases are rejected. Sets RESOLVED, never CLOSED.')
def resolve_ticket(body:s.ResolveTicket,request:Request,ticket_id:str=TicketID): return run(request,'resolve_ticket',body,ticket_id)

@router.post('/tickets/count-recent',operation_id='count_recent_tickets',response_model=s.CountOut,summary='Count an active issue cluster in a UTC window',description='Use for outage investigation. Supplied filters use AND; requires a filter. Inclusive window excludes global, resolved, closed and already globally linked tickets.')
def count_recent_tickets(body:s.CountRecent,request:Request): return run(request,'count_recent_tickets',body)

@router.post('/global-tickets/search',operation_id='find_open_global_tickets',response_model=s.GlobalResults,summary='Find an active global issue in a scope',description='Use before creating a global issue. All supplied exact-match filters use AND; empty filters are rejected. Closed/resolved global issues are excluded.')
def find_open_global_tickets(body:s.Grouping,request:Request): return run(request,'find_open_global_tickets',body)

@router.post('/global-tickets',operation_id='create_global_ticket',response_model=s.GlobalCreated,summary='Create or reuse a scoped global incident',description='Use after the agent evaluates outage thresholds. Requires category, CI, location and active related tickets in that scope. Atomic linking and unique active scope prevent duplicates.')
def create_global_ticket(body:s.CreateGlobal,request:Request): return run(request,'create_global_ticket',body)

@router.post('/tickets/{ticket_id}/global-link',operation_id='link_ticket_to_global_ticket',response_model=s.LinkOut,summary='Link an affected ticket to an existing outage',description='Use when an active global issue already covers this exact category/CI/location. Conflicting, self and inactive links are rejected; identical links add no duplicate worklogs.')
def link_ticket_to_global_ticket(body:s.LinkGlobal,request:Request,ticket_id:str=TicketID): return run(request,'link_ticket_to_global_ticket',body,ticket_id)

@router.post('/diagnostics/account-status',operation_id='check_account_status',response_model=s.AccountOut,summary='Observe synthetic account state',description='Use to discriminate lockout, password expiry and MFA conditions. Reads stored state; unknown state remains UNKNOWN. Records evidence only, never modifies accounts or returns secrets.')
def check_account_status(body:s.AccountCheck,request:Request): return run(request,'check_account_status',body)

@router.post('/diagnostics/application-entitlement',operation_id='check_application_entitlement',response_model=s.EntitlementOut,summary='Observe synthetic application access',description='Use to distinguish missing entitlement or role from authentication failure. Reads stored provisioning state and records evidence; never grants access.')
def check_application_entitlement(body:s.EntitlementCheck,request:Request): return run(request,'check_application_entitlement',body)

@router.post('/diagnostics/service-health',operation_id='check_service_health',response_model=s.HealthOut,summary='Observe independent synthetic service health',description='Use to compare local symptoms with a stored service observation for the exact CI/location. Never infers health from ticket counts. Records evidence, with UNKNOWN when absent.')
def check_service_health(body:s.HealthCheck,request:Request): return run(request,'check_service_health',body)

@router.post('/tickets/{ticket_id}/human-reviews',operation_id='request_human_review',response_model=s.ReviewOut,summary='Request human review or triage',description='Use for mandatory human cases or uncertainty. Sets PENDING and records a REQUESTED review; this is not approval. Only authenticated admin can decide a review.')
def request_human_review(body:s.RequestReview,request:Request,ticket_id:str=TicketID): return run(request,'request_human_review',body,ticket_id)

@router.post('/tickets/{ticket_id}/notifications',operation_id='notify_resolver_group',response_model=s.NotificationOut,summary='Store a mock resolver notification',description='Use after routing or escalation to record intended communication. Stores SQLite notification and worklog; sends no external message.')
def notify_resolver_group(body:s.Notify,request:Request,ticket_id:str=TicketID): return run(request,'notify_resolver_group',body,ticket_id)

@router.post('/knowledge/search',operation_id='search_diagnostic_knowledge',response_model=s.KnowledgeResults,summary='Retrieve approved diagnostic guidance',description='Use to choose discriminating questions, safe checks and next steps. Returns approved portable articles with evidence, exclusions, resolution and escalation conditions.')
def search_diagnostic_knowledge(body:s.KnowledgeSearch,request:Request): return run(request,'search_diagnostic_knowledge',body)

@router.post('/tickets/{ticket_id}/diagnostic-results',operation_id='record_diagnostic_result',response_model=s.DiagnosticOut,summary='Persist a structured diagnostic conclusion',description='Use after collecting evidence. Stores agent assertions and confidence basis as a new version, validates sources/policy and updates valid taxonomy. Does not resolve or assign automatically.')
def record_diagnostic_result(body:s.DiagnosticInput,request:Request,ticket_id:str=TicketID): return run(request,'record_diagnostic_result',body,ticket_id)

@admin.post('/human-reviews/{review_id}/decision',response_model=s.ReviewOut,operation_id='admin_decide_review')
def decide_review(review_id:str,body:s.ReviewDecision,request:Request):
    # Review ID is not a ticket ID; the shared runner resolves it only in this branch.
    return run(request,'admin_review',body,review_id)

