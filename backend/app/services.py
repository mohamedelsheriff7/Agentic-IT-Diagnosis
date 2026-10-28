"""Business transactions. Routes own BEGIN IMMEDIATE/commit/rollback, including retry records."""
import json
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from . import models as m
from . import repositories as repo
from .policy import fail, active, mandatory, redact, utc
from .retrieval import rank


def uid(prefix):
    return prefix + '-' + uuid4().hex[:16]

def log(db, t, now, entry_type, summary, rationale, body=None, actor='AGENT'):
    body = body or {}
    data = redact(dict(worklog_id=uid('WL'), ticket_id=t.ticket_id, timestamp=now, actor_id=actor,
        entry_type=entry_type, summary=summary, rationale=rationale, action_id=body.get('action_id'),
        evidence_ids=body.get('evidence_ids', []), knowledge_article_ids=body.get('knowledge_article_ids', []),
        historical_ticket_ids=body.get('historical_ticket_ids', [])))
    db.add(m.Worklog(worklog_id=data['worklog_id'], ticket_id=t.ticket_id, data=data))
    t.updated_at = now
    db.flush()
    return data

def details(db, t):
    d = {c.name: getattr(t, c.name) for c in m.Ticket.__table__.columns if c.name != 'active_scope'}
    last = repo.latest(db, t.ticket_id)
    return redact(dict(**d, related_ticket_ids=repo.related(db,t),
        worklogs=[w.data for w in db.scalars(select(m.Worklog).where(m.Worklog.ticket_id==t.ticket_id).order_by(m.Worklog.data['timestamp'], m.Worklog.worklog_id))],
        evidence=[{k:v for k,v in e.data.items() if k not in ('facts','tool')} for e in db.scalars(select(m.Evidence).where(m.Evidence.ticket_id==t.ticket_id))],
        latest_diagnostic_result=last.data if last else None))

def validate_context(db, b):
    # Accept the project brief's singular/reporting bucket labels while storing
    # the backend's canonical taxonomy names.
    domain_aliases = {'Application': 'Applications', 'Endpoint': 'Endpoints', 'Network/Other': 'Network'}
    category_domain_aliases = {
        ('Network', 'Storage'): 'Infrastructure',
        ('Network', 'Compute'): 'Infrastructure',
        ('Network', 'Certificates'): 'Infrastructure',
        ('Network', 'Threat'): 'Security',
        ('Network', 'Data Protection'): 'Security',
        ('Network', 'How To'): 'Service Desk',
        ('Network', 'Unclassified'): 'Service Desk',
    }
    if b.get('domain') in domain_aliases:
        b['domain'] = domain_aliases[b['domain']]
    mapping = {'reported_by_id':'users','affected_person_id':'users','owner_group_id':'resolver_groups',
               'owner_id':'users','asset_id':'assets','configuration_item_id':'configuration_items','location_id':'locations'}
    for key, kind in mapping.items():
        if b.get(key): repo.reference(db, b[key], kind)
    taxonomy = repo.refs(db, 'taxonomy')
    if b.get('domain') and not any(d['domain']==b['domain'] for d in taxonomy): fail('Unknown domain')
    if b.get('category'):
        matches = [d for d in taxonomy if d['category'] == b['category']]
        scoped = [d for d in matches if not b.get('domain') or d['domain'] == b['domain']]
        if not scoped:
            # Larger Workstream A datasets may use the brief's broad
            # Network/Other bucket for categories owned by other domains.
            # Preserve the ticket's category while canonicalizing its domain
            # when the category has one unambiguous taxonomy owner.
            preferred = category_domain_aliases.get((b.get('domain'), b.get('category')))
            if preferred and any(d['domain'] == preferred for d in matches):
                b['domain'] = preferred
                return
            owners = {d['domain'] for d in matches}
            if len(owners) == 1:
                b['domain'] = next(iter(owners))
            else:
                fail('Unknown category or domain/category combination')

def create(db, b, now):
    validate_context(db,b)
    fields = {k:v for k,v in b.items() if k != 'action_id'}
    fields['affected_person_id'] = b.get('affected_person_id') or b['reported_by_id']
    t = m.Ticket(ticket_id=uid('INC' if b['ticket_class']=='INCIDENT' else 'TKT'), status='NEW', reported_at=now, updated_at=now, **fields)
    db.add(t); db.flush()
    log(db,t,now,'NOTE','Ticket created', 'Issue captured; classification may be unknown.',b)
    return details(db,t)

def search(db,b):
    candidates = [t for t in db.scalars(select(m.Ticket).where(m.Ticket.status.in_(['RESOLVED','CLOSED'])))
                  if all(not b.get(k) or getattr(t,k)==b[k] for k in ('domain','category','language'))]
    by_id = {t.ticket_id:t for t in candidates}
    return {'results':[dict(ticket_id=i, symptoms=by_id[i].description, diagnosis_code=by_id[i].diagnosis_code,
                resolver_group_id=by_id[i].owner_group_id, resolution=by_id[i].resolution_summary, relevance_score=score)
                for i,score in rank(b['description'],[(t.ticket_id,t.summary+' '+t.description) for t in candidates],b['limit'])]}

def assign(db,t,b,now):
    repo.reference(db,b['resolver_group_id'],'resolver_groups')
    for group in b['alternative_resolver_group_ids']: repo.reference(db,group,'resolver_groups')
    approved = db.scalar(select(m.Review).where(m.Review.ticket_id==t.ticket_id,m.Review.group_id==b['resolver_group_id'],m.Review.state=='APPROVED'))
    group = b['resolver_group_id'] if b['confidence']=='HIGH' else 'GRP-L1'
    if mandatory(t) and group!='GRP-L1' and not approved:
        fail('Mandatory human case requires admin-approved review for this specialist group', 'HUMAN_REVIEW_REQUIRED')
    triage = b['confidence']=='LOW' or (mandatory(t) and not approved)
    t.owner_group_id, t.status = group, 'PENDING' if triage else 'QUEUED'
    result = dict(ticket_id=t.ticket_id, assigned_group_id=group, recommended_group_id=b['resolver_group_id'],
        alternative_resolver_group_ids=b['alternative_resolver_group_ids'], confidence=b['confidence'], human_triage_required=bool(triage), status=t.status)
    db.add(m.Assignment(id=uid('ASG'),ticket_id=t.ticket_id,group_id=group,data=redact(dict(**result, reason=b['reason']))))
    log(db,t,now,'ASSIGNMENT',json.dumps(result),b['reason'],b)
    return result

def note(db,t,b,now):
    ids = list(b['evidence_ids'])
    for e in b['evidence']:
        if e['source_type']=='KNOWLEDGE_ARTICLE': repo.reference(db,e['source_id'],'diagnostic_articles')
        elif e['source_type']=='HISTORICAL_TICKET': repo.validate_sources(db,t.ticket_id,{'historical_ticket_ids':[e['source_id']]})
        elif e['source_id'] != t.affected_person_id: fail('User evidence must reference the affected person')
        when = e.get('observed_at') or now
        from datetime import datetime
        when = utc(datetime.fromisoformat(when.replace('Z','+00:00')))
        if when > now: fail('Evidence cannot be in the future')
        identifier=uid('EV')
        db.add(m.Evidence(evidence_id=identifier,ticket_id=t.ticket_id,data=redact(dict(**e, evidence_id=identifier) | {'observed_at':when})))
        ids.append(identifier)
    return log(db,t,now,b['entry_type'],b['summary'],b['rationale'],dict(b,evidence_ids=ids))

def diagnose(db,t,b,now):
    if b['outcome']=='DIAGNOSED' and not b['diagnosis_code']: fail('DIAGNOSED requires a diagnosis')
    if b['outcome']=='INCONCLUSIVE' and b['diagnosis_code']: fail('Inconclusive result must not establish a diagnosis')
    if b['recommended_action']=='RESOLVE' and (b['outcome']!='DIAGNOSED' or b['confidence']!='HIGH' or mandatory(t)): fail('Resolution recommendation is inconsistent with outcome, confidence or safety')
    if b['outcome']=='HUMAN_REQUIRED' and b['recommended_action']!='ESCALATE': fail('Human-required results must recommend escalation')
    if mandatory(t) and b['recommended_action'] not in ('ESCALATE','ASK_MORE'): fail('Mandatory human case requires escalation or more information')
    candidate_codes = {x['diagnosis_code'] for x in b['candidate_diagnoses']}
    eliminated_codes = {x['diagnosis_code'] for x in b['eliminated_diagnoses']}
    if candidate_codes & eliminated_codes or b['diagnosis_code'] in eliminated_codes: fail('Contradictory diagnoses')
    for code in candidate_codes | eliminated_codes: repo.reference(db,code,'taxonomy')
    if b['diagnosis_code']:
        tax=repo.reference(db,b['diagnosis_code'],'taxonomy')
        scoped_global=repo.ticket(db,t.global_ticket_id) if t.global_ticket_id else t if t.is_global else None
        if scoped_global and tax['category']!=scoped_global.category: fail('Diagnosis cannot change the category of a globally scoped ticket')
        t.diagnosis_code,t.domain,t.category,t.subcategory=tax['diagnosis_code'],tax['domain'],tax['category'],tax['label']
        t.security_sensitive = t.security_sensitive or tax.get('security_sensitive',False)
        t.privileged_access = t.privileged_access or tax.get('privileged_access',False)
        if mandatory(t) and b['recommended_action'] not in ('ASK_MORE','ESCALATE'): fail('Diagnosis establishes a mandatory human case')
    else: t.diagnosis_code=None
    last=repo.latest(db,t.ticket_id)
    result=redact(dict(b,diagnostic_result_id=uid('DR'),version=last.version+1 if last else 1,recorded_at=now))
    db.add(m.Diagnostic(id=result['diagnostic_result_id'],ticket_id=t.ticket_id,version=result['version'],data=result))
    log(db,t,now,'DIAGNOSIS',b['diagnosis_code'] or b['outcome'],b['rationale'],b)
    return result

def resolve(db,t,b,now):
    if mandatory(t): fail('Mandatory human cases cannot be agent-resolved', 'HUMAN_REVIEW_REQUIRED')
    last=repo.latest(db,t.ticket_id)
    if not last or last.data['outcome']!='DIAGNOSED' or t.diagnosis_code!=b['diagnosis_code']: fail('A matching recorded diagnosis is required')
    if last.data['confidence']!='HIGH' or last.data['recommended_action']!='RESOLVE': fail('Latest diagnosis must recommend resolution with HIGH confidence')
    article=repo.reference(db,b['knowledge_article_id'],'diagnostic_articles')
    if not article['approved'] or not article['agent_resolvable'] or article['diagnosis_code']!=b['diagnosis_code']: fail('Article does not authorize this resolution')
    if not b['user_confirmed_success']: fail('Explicit user confirmation required','CONFIRMATION_REQUIRED')
    if not set(s['step_id'] for s in article['resolution_steps']).issubset(b['steps_completed']): fail('Required resolution steps incomplete')
    if any(s['level']=='SPECIALIST' for s in article['resolution_steps']): fail('Specialist steps cannot be agent-resolved')
    evidence=[db.get(m.Evidence,i).data for i in b['evidence_ids']]
    for condition in article['resolution_conditions']:
        if not any(e.get('tool')==condition['tool'] and str(e.get('facts',{}).get(condition['field']))==condition['equals'] for e in evidence):
            fail('Recorded tool evidence does not satisfy article conditions','MISSING_EVIDENCE')
    if not article['resolution_conditions']: fail('Article has no machine-verifiable conditions')
    t.status='RESOLVED'; t.resolved_at=t.actual_finish_at=now; t.active_scope=None
    t.linked_solution_id=b['knowledge_article_id']; t.resolution_summary=redact(b['resolution_summary'])
    log(db,t,now,'RESOLUTION',b['resolution_summary'],'User asserted success; this is not independent verification.',dict(b,knowledge_article_ids=[b['knowledge_article_id']]))
    return details(db,t)

def grouped(t,b):
    return all(not b.get(k) or getattr(t,k)==b[k] for k in ('domain','category','configuration_item_id','location_id'))

def count(db,b,now_dt):
    from datetime import datetime
    end=datetime.fromisoformat(b['as_of'].replace('Z','+00:00')) if b.get('as_of') else now_dt
    start=end-timedelta(minutes=b['window_minutes'])
    ids=sorted(t.ticket_id for t in db.scalars(select(m.Ticket)) if not t.is_global and not t.global_ticket_id and t.status not in ('RESOLVED','CLOSED') and utc(start)<=t.reported_at<=utc(end) and grouped(t,b))
    return dict(count=len(ids),matching_ticket_ids=ids,grouping_criteria={k:b.get(k) for k in ('domain','category','configuration_item_id','location_id')},window_start=utc(start),window_end=utc(end))

def globals_search(db,b):
    return {'results':[dict(ticket_id=t.ticket_id,severity=t.severity,owner_group_id=t.owner_group_id,
        affected_scope={k:getattr(t,k) for k in ('domain','category','configuration_item_id','location_id')},related_ticket_ids=repo.related(db,t))
        for t in db.scalars(select(m.Ticket)) if t.is_global and t.status not in ('RESOLVED','CLOSED') and grouped(t,b)]}

def link(db,t,b,now):
    g=repo.ticket(db,b['global_ticket_id']); active(g)
    if t.ticket_id==g.ticket_id or t.is_global or not g.is_global: fail('Must link a non-global child to a distinct global incident')
    if not grouped(t,{'category':g.category,'configuration_item_id':g.configuration_item_id,'location_id':g.location_id}): fail('Ticket does not belong to global affected scope')
    if t.global_ticket_id and t.global_ticket_id!=g.ticket_id: fail('Ticket already linked to another global issue','RELATIONSHIP_CONFLICT',409)
    existed=t.global_ticket_id==g.ticket_id
    if not existed:
        t.global_ticket_id=g.ticket_id
        db.add(m.Relationship(child_id=t.ticket_id,global_id=g.ticket_id))
        log(db,t,now,'OUTAGE','Linked to '+g.ticket_id,b['reason'],b)
        log(db,g,now,'OUTAGE','Related ticket '+t.ticket_id,b['reason'],b)
    return dict(ticket_id=t.ticket_id,global_ticket_id=g.ticket_id,already_linked=existed)

def create_global(db,b,now):
    validate_context(db,b)
    if b['severity']=='SEV1' and b['owner_group_id']!='GRP-L1': fail('Critical global incidents start in human L1 triage', 'HUMAN_REVIEW_REQUIRED')
    children=[repo.ticket(db,i) for i in sorted(set(b['related_ticket_ids']))]
    for child in children:
        active(child)
        if child.is_global or not grouped(child,b): fail('Related tickets must belong to the supplied scope')
        if mandatory(child) and b['owner_group_id']!='GRP-L1': fail('Mandatory human child cases require L1 ownership of a new global issue', 'HUMAN_REVIEW_REQUIRED')
    for identifier in b['knowledge_article_ids']: repo.reference(db,identifier,'diagnostic_articles')
    for identifier in b['historical_ticket_ids']:
        if repo.ticket(db,identifier).status not in ('RESOLVED','CLOSED'): fail('Historical source must be resolved or closed')
    for identifier in b['evidence_ids']:
        e=db.get(m.Evidence,identifier)
        if not e or e.ticket_id not in b['related_ticket_ids']: fail('Global evidence must belong to a related ticket')
    scope=json.dumps([b[k] for k in ('category','configuration_item_id','location_id')])
    g=db.scalar(select(m.Ticket).where(m.Ticket.active_scope==scope))
    reused=g is not None
    if not g:
        g=m.Ticket(ticket_id=uid('GLB'),ticket_class='INCIDENT',summary=redact(b['summary']),description=redact(b['description']),status='QUEUED',
            reported_priority=1 if b['severity']=='SEV1' else 2,impact=1,urgency=1,language='en',category=b['category'],
            configuration_item_id=b['configuration_item_id'],location_id=b['location_id'],owner_group_id=b['owner_group_id'],
            reported_by_id=children[0].reported_by_id,affected_person_id=children[0].affected_person_id,
            reported_at=now,updated_at=now,is_global=True,severity=b['severity'],active_scope=scope,
            security_sensitive=any(c.security_sensitive for c in children),privileged_access=any(c.privileged_access for c in children))
        db.add(g);db.flush()
        log(db,g,now,'OUTAGE','Global incident created',b['reason'],b)
    elif any(c.security_sensitive and not g.security_sensitive or c.privileged_access and not g.privileged_access for c in children):
        g.security_sensitive=g.security_sensitive or any(c.security_sensitive for c in children)
        g.privileged_access=g.privileged_access or any(c.privileged_access for c in children)
        log(db,g,now,'ESCALATION','Global safety flags strengthened','Preserved restrictions of newly related children.',b)
    for child in children: link(db,child,dict(global_ticket_id=g.ticket_id,reason=b['reason'],action_id=b['action_id']),now)
    return dict(ticket_id=g.ticket_id,reused_existing=reused,related_ticket_ids=repo.related(db,g))

def check(db,t,b,now,tool):
    if tool in ('check_account_status','check_application_entitlement') and b['user_id']!=t.affected_person_id: fail('Check must target the affected person')
    if tool=='check_account_status':
        state=next((s for s in repo.refs(db,'account_states') if s['user_id']==b['user_id']),{})
        result=dict(user_id=b['user_id'],**{k:state.get(k,'UNKNOWN') for k in ('enabled','locked','password_expired','mfa_enrolled','mfa_locked')})
    elif tool=='check_application_entitlement':
        state=next((s for s in repo.refs(db,'application_entitlements') if s['user_id']==b['user_id'] and s['application_id']==b['application_id']),{})
        entitled=state.get('entitled','UNKNOWN')
        if state and b.get('required_role') and b['required_role'] not in state.get('roles',[]): entitled='FALSE'
        result=dict(user_id=b['user_id'],application_id=b['application_id'],required_role=b.get('required_role'),entitled=entitled,provisioning_state=state.get('provisioning_state','UNKNOWN'))
    else:
        if t.configuration_item_id and t.configuration_item_id!=b['configuration_item_id']: fail('Service check must target ticket configuration item')
        if t.location_id and b.get('location_id') and t.location_id!=b['location_id']: fail('Service check must target ticket location')
        state=next((s for s in repo.refs(db,'service_health') if s['configuration_item_id']==b['configuration_item_id'] and s.get('location_id')==b.get('location_id')), {})
        result=dict(configuration_item_id=b['configuration_item_id'],location_id=b.get('location_id'),state=state.get('state','UNKNOWN'),scope=state.get('scope','No matching stored scope'),details=state.get('details','No observation available'))
    identifier=uid('EV')
    result=redact(dict(result,observed_at=now,evidence_id=identifier))
    db.add(m.Evidence(evidence_id=identifier,ticket_id=t.ticket_id,data=dict(evidence_id=identifier,source_type='TOOL_CHECK',source_id=tool,tool=tool,facts=result,observation=json.dumps(result,ensure_ascii=False),observed_at=now)))
    log(db,t,now,'EVIDENCE',tool,json.dumps(result,ensure_ascii=False),dict(b,evidence_ids=[identifier]))
    return result

def review(db,t,b,now):
    repo.reference(db,b['suggested_group_id'],'resolver_groups')
    identifier=uid('REV')
    db.add(m.Review(id=identifier,ticket_id=t.ticket_id,group_id=b['suggested_group_id'],state='REQUESTED',data=redact(b)))
    t.status='PENDING'
    log(db,t,now,'ESCALATION','Human review requested',b['reason'],b)
    return dict(review_id=identifier,ticket_id=t.ticket_id,state='REQUESTED')

def notify(db,t,b,now):
    repo.reference(db,b['resolver_group_id'],'resolver_groups')
    identifier=uid('NTF')
    db.add(m.Notification(id=identifier,ticket_id=t.ticket_id,group_id=b['resolver_group_id'],data=redact(dict(b,timestamp=now))))
    log(db,t,now,'NOTIFICATION','Mock notification to '+b['resolver_group_id'],b['message'],b)
    return dict(notification_id=identifier,delivery_mode='MOCK')

def knowledge(db,b):
    articles=[a for a in repo.refs(db,'diagnostic_articles') if a['approved'] and all(not b.get(k) or a[k]==b[k] for k in ('domain','category'))]
    by_id={a['article_id']:a for a in articles}
    return {'results':[by_id[i] for i,_ in rank(b['query'],[(a['article_id'],' '.join(a['symptoms_en']+a['symptoms_ar']+[a['diagnosis_code'],a['category']])) for a in articles],b['limit'])]}
