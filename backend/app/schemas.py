from __future__ import annotations
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

Text = Annotated[str, Field(min_length=1, max_length=16000)]
Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')]
Confidence = Literal['HIGH', 'MEDIUM', 'LOW']
Status = Literal['NEW','QUEUED','IN_PROGRESS','PENDING','RESOLVED','CLOSED']
EntryType = Literal['NOTE','QUESTION','EVIDENCE','DIAGNOSIS','ASSIGNMENT','RESOLUTION','ESCALATION','OUTAGE','NOTIFICATION']
Severity = Literal['SEV1','SEV2','SEV3']
State = Literal['TRUE','FALSE','UNKNOWN']

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Error(Model):
    code: str
    message: str
    details: list[str] = []
    request_id: str

class Action(Model):
    action_id: Identifier = Field(description='Unique retry key. Reuse only for identical operation and inputs.', examples=['demo-action-001'])

class Sources(Model):
    evidence_ids: list[Identifier] = Field(default_factory=list, description='Recorded evidence IDs belonging to this ticket.')
    knowledge_article_ids: list[Identifier] = []
    historical_ticket_ids: list[Identifier] = []

class EvidenceInput(Model):
    source_type: Literal['USER_RESPONSE','KNOWLEDGE_ARTICLE','HISTORICAL_TICKET']
    source_id: Identifier
    observation: Text
    observed_at: AwareDatetime | None = None

class EvidenceOut(Model):
    evidence_id: str
    source_type: Literal['USER_RESPONSE','TOOL_CHECK','KNOWLEDGE_ARTICLE','HISTORICAL_TICKET']
    source_id: str
    observation: str
    observed_at: AwareDatetime

class WorklogOut(Sources):
    worklog_id: str
    ticket_id: str
    timestamp: AwareDatetime
    actor_id: str
    entry_type: EntryType
    summary: str
    rationale: str
    action_id: str | None = None

class CreateTicket(Action):
    summary: Annotated[str, Field(min_length=1, max_length=250)]
    description: Text
    reported_by_id: Identifier
    affected_person_id: Identifier | None = None
    ticket_class: Literal['SERVICE_REQUEST','INCIDENT','PROBLEM','CHANGE'] = 'INCIDENT'
    reported_priority: Annotated[int, Field(ge=1, le=4)] = 3
    impact: Annotated[int, Field(ge=1, le=3)] = 3
    urgency: Annotated[int, Field(ge=1, le=3)] = 2
    language: Literal['en','ar','franco_ar'] = 'en'
    domain: Text | None = None
    category: Text | None = None
    subcategory: Text | None = None
    asset_id: Identifier | None = None
    configuration_item_id: Identifier | None = None
    location_id: Identifier | None = None
    security_sensitive: bool = False
    privileged_access: bool = False

class TicketOut(Model):
    ticket_id: str
    ticket_class: Literal['SERVICE_REQUEST','INCIDENT','PROBLEM','CHANGE']
    summary: str
    description: str
    status: Status
    reported_priority: int
    impact: int
    urgency: int
    language: Literal['en','ar','franco_ar']
    domain: str | None = None
    category: str | None = None
    subcategory: str | None = None
    diagnosis_code: str | None = None
    owner_group_id: str | None = None
    owner_id: str | None = None
    reported_by_id: str
    affected_person_id: str
    asset_id: str | None = None
    configuration_item_id: str | None = None
    location_id: str | None = None
    reported_at: AwareDatetime
    target_finish_at: AwareDatetime | None = None
    actual_finish_at: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    closed_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    linked_solution_id: str | None = None
    resolution_summary: str | None = None
    is_global: bool = False
    global_ticket_id: str | None = None
    severity: Severity | None = None
    security_sensitive: bool = False
    privileged_access: bool = False

class Candidate(Model):
    diagnosis_code: Identifier
    reason: Text

class ConfidenceBasis(Model):
    knowledge_match_strength: Confidence
    evidence_completeness: Confidence
    historical_agreement: Literal['AGREES','DISAGREES','NOT_AVAILABLE']
    alternatives_excluded: bool

class DiagnosticInput(Action, Sources):
    diagnosis_code: Identifier | None = None
    outcome: Literal['DIAGNOSED','INCONCLUSIVE','HUMAN_REQUIRED']
    candidate_diagnoses: list[Candidate] = []
    eliminated_diagnoses: list[Candidate] = []
    confidence: Confidence
    confidence_basis: ConfidenceBasis
    recommended_action: Literal['ASK_MORE','RESOLVE','ROUTE','ESCALATE']
    missing_information: list[Text] = []
    rationale: Text

class DiagnosticOut(DiagnosticInput):
    diagnostic_result_id: str
    version: int
    recorded_at: AwareDatetime

class TicketDetails(TicketOut):
    related_ticket_ids: list[str] = []
    worklogs: list[WorklogOut] = []
    evidence: list[EvidenceOut] = []
    latest_diagnostic_result: DiagnosticOut | None = None

class SearchTickets(Model):
    description: Text
    domain: Text | None = None
    category: Text | None = None
    language: Literal['en','ar','franco_ar'] | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 5

class SimilarTicket(Model):
    ticket_id: str
    symptoms: str
    diagnosis_code: str | None
    resolver_group_id: str | None
    resolution: str | None
    relevance_score: float = Field(description='Lexical similarity, not diagnostic confidence.')

class SimilarResults(Model):
    results: list[SimilarTicket]

class AssignTicket(Action, Sources):
    resolver_group_id: Identifier
    confidence: Confidence
    reason: Text
    alternative_resolver_group_ids: Annotated[list[Identifier], Field(max_length=3)] = []

class AssignmentOut(Model):
    ticket_id: str
    assigned_group_id: str
    recommended_group_id: str
    alternative_resolver_group_ids: list[str]
    confidence: Confidence
    human_triage_required: bool
    status: Status

class AddWorklog(Action, Sources):
    entry_type: Literal['NOTE','QUESTION','EVIDENCE','DIAGNOSIS']
    summary: Text
    rationale: Text
    evidence: list[EvidenceInput] = []

class ResolveTicket(Action, Sources):
    diagnosis_code: Identifier
    resolution_summary: Text
    steps_completed: list[Text] = Field(min_length=1, description='Exact article step IDs completed by the user or authorized operator.')
    knowledge_article_id: Identifier
    user_confirmed_success: bool = Field(description='Conversation assertion only, not independent verification of the fix.')

class Grouping(Model):
    category: Text | None = None
    configuration_item_id: Identifier | None = None
    location_id: Identifier | None = None
    @model_validator(mode='after')
    def grouping(self):
        if not any(getattr(self, k, None) for k in ('domain','category','configuration_item_id','location_id')):
            raise ValueError('At least one grouping filter is required')
        return self

class CountRecent(Grouping):
    domain: Text | None = None
    window_minutes: Annotated[int, Field(ge=1, le=10080)] = 30
    as_of: AwareDatetime | None = None

class Criteria(Model):
    domain: str | None = None
    category: str | None = None
    configuration_item_id: str | None = None
    location_id: str | None = None

class CountOut(Model):
    count: int
    matching_ticket_ids: list[str]
    grouping_criteria: Criteria
    window_start: AwareDatetime
    window_end: AwareDatetime

class GlobalIssue(Model):
    ticket_id: str
    severity: Severity
    owner_group_id: str
    affected_scope: Criteria
    related_ticket_ids: list[str]

class GlobalResults(Model):
    results: list[GlobalIssue]

class CreateGlobal(Action, Sources):
    summary: Text
    description: Text
    severity: Severity
    category: Text
    configuration_item_id: Identifier
    location_id: Identifier
    owner_group_id: Identifier
    related_ticket_ids: Annotated[list[Identifier], Field(min_length=1)]
    reason: Text

class GlobalCreated(Model):
    ticket_id: str
    reused_existing: bool
    related_ticket_ids: list[str]

class LinkGlobal(Action):
    global_ticket_id: Identifier
    reason: Text

class LinkOut(Model):
    ticket_id: str
    global_ticket_id: str
    already_linked: bool

class AccountCheck(Model):
    ticket_id: Identifier
    user_id: Identifier
    action_id: Identifier = Field(description='Retry key for recording the observation; synthetic account is never modified.')

class AccountOut(Model):
    user_id: str
    enabled: State
    locked: State
    password_expired: State
    mfa_enrolled: State
    mfa_locked: State
    observed_at: AwareDatetime
    evidence_id: str

class EntitlementCheck(AccountCheck):
    application_id: Identifier
    required_role: Identifier | None = None

class EntitlementOut(Model):
    user_id: str
    application_id: str
    required_role: str | None
    entitled: State
    provisioning_state: Literal['ACTIVE','PENDING','ABSENT','UNKNOWN']
    observed_at: AwareDatetime
    evidence_id: str

class HealthCheck(Action):
    ticket_id: Identifier
    configuration_item_id: Identifier
    location_id: Identifier | None = None

class HealthOut(Model):
    configuration_item_id: str
    location_id: str | None
    state: Literal['OPERATIONAL','DEGRADED','UNAVAILABLE','UNKNOWN']
    scope: str
    details: str
    observed_at: AwareDatetime
    evidence_id: str

class RequestReview(Action, Sources):
    reason: Text
    review_type: Literal['SAFETY','TRIAGE','INVESTIGATION','PRIVILEGED_ACCESS']
    suggested_group_id: Identifier

class ReviewOut(Model):
    review_id: str
    ticket_id: str
    state: Literal['REQUESTED','APPROVED','REJECTED']

class ReviewDecision(Action):
    approved: bool
    reason: Text

class Notify(Action):
    resolver_group_id: Identifier
    severity: Severity
    message: Text

class NotificationOut(Model):
    notification_id: str
    delivery_mode: Literal['MOCK'] = 'MOCK'

class KnowledgeSearch(Model):
    query: Text
    domain: Text | None = None
    category: Text | None = None
    limit: Annotated[int, Field(ge=1, le=50)] = 5

class Condition(Model):
    tool: Literal['check_account_status','check_application_entitlement','check_service_health']
    field: str
    equals: str

class ResolutionStep(Model):
    step_id: str
    level: Literal['SELF_SERVICE','L1','SPECIALIST']
    instruction: str

class Article(Model):
    article_id: str
    version: int
    approved: bool
    diagnosis_code: str
    domain: str
    category: str
    symptoms_en: list[str]
    symptoms_ar: list[str]
    possible_causes: list[str]
    discriminating_questions: list[str]
    required_evidence: list[str]
    safe_checks: list[str]
    exclusion_criteria: list[str]
    competing_diagnoses: list[str]
    resolution_steps: list[ResolutionStep]
    agent_resolvable: bool
    resolution_conditions: list[Condition]
    mandatory_human_escalation_conditions: list[str]
    resolver_group_id: str

class KnowledgeResults(Model):
    results: list[Article]

class ResetRequest(Action):
    confirm: Literal['RESET_SYNTHETIC_DEMO']

class ResetOut(Model):
    imported_tickets: int
