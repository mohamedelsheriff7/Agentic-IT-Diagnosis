"""Workstream A/B portable dataset schemas. Hidden evaluation files are never imported."""
from typing import Literal
from pydantic import Field, model_validator
from .schemas import Model, Text, Identifier, State, Article, TicketOut

class Label(Model):
    id: Identifier
    label: Text

class Taxonomy(Model):
    diagnosis_code: Identifier
    domain: Text
    category: Text
    label: Text
    resolver_group_id: Identifier
    security_sensitive: bool = False
    privileged_access: bool = False

class Routing(Model):
    diagnosis_code: Identifier
    owner_group_id: Identifier
    boundary: Text
    alternative_group_ids: list[Identifier]

class AccountState(Model):
    id: Identifier
    user_id: Identifier
    enabled: State
    locked: State
    password_expired: State
    mfa_enrolled: State
    mfa_locked: State

class EntitlementState(Model):
    id: Identifier
    user_id: Identifier
    application_id: Identifier
    entitled: State
    roles: list[Identifier]
    provisioning_state: Literal['ACTIVE','PENDING','ABSENT','UNKNOWN']

class ServiceState(Model):
    id: Identifier
    configuration_item_id: Identifier
    location_id: Identifier | None = None
    state: Literal['OPERATIONAL','DEGRADED','UNAVAILABLE','UNKNOWN']
    scope: Text
    details: Text

class ImportedTicket(TicketOut):
    reported_priority: int = Field(ge=1,le=4)
    impact: int = Field(ge=1,le=3)
    urgency: int = Field(ge=1,le=3)
    initial_owner_group_id: Identifier | None = None
    @model_validator(mode='after')
    def chronology(self):
        for k in ('resolved_at','closed_at','actual_finish_at','updated_at'):
            v=getattr(self,k)
            if v and v < self.reported_at: raise ValueError('Timestamp precedes report')
        if self.status in ('RESOLVED','CLOSED') and (not self.resolution_summary or not self.resolved_at or not self.diagnosis_code): raise ValueError('Historical ticket requires diagnosis, resolution and time')
        if self.status=='CLOSED' and not self.closed_at: raise ValueError('Closed ticket requires closed_at')
        if self.status not in ('RESOLVED','CLOSED') and (self.diagnosis_code or self.resolution_summary or self.linked_solution_id): raise ValueError('Open starter tickets cannot expose hidden diagnoses or solutions')
        return self

class Threshold(Model):
    category: Text
    configuration_item_id: Identifier
    location_id: Identifier
    window_minutes: int = Field(ge=1,le=10080)
    minimum_count: int = Field(ge=1)

class SeverityRules(Model):
    SEV1: Text
    SEV2: Text
    SEV3: Text

class EscalationPolicy(Model):
    id: Identifier
    mandatory_human_cases: list[Text]
    severity_rules: SeverityRules
    outage_thresholds: list[Threshold]

REFERENCE_SCHEMAS={'taxonomy':Taxonomy,'resolver_groups':Label,'users':Label,'assets':Label,'configuration_items':Label,'locations':Label,'routing_matrix':Routing,'account_states':AccountState,'application_entitlements':EntitlementState,'service_health':ServiceState,'diagnostic_articles':Article,'escalation_policy':EscalationPolicy}
