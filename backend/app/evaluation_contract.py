"""Offline evaluation schemas. These models are never part of agent OpenAPI."""
from typing import Literal
from pydantic import Field
from .schemas import Model, Identifier, Text, State

class Answer(Model):
    topic: Identifier
    answer: Text
    eliminates: list[Identifier]
    answer_en: Text | None = None

class AccountFixture(Model):
    enabled: State
    locked: State
    password_expired: State
    mfa_enrolled: State
    mfa_locked: State

class EntitlementFixture(Model):
    application_id: Identifier
    entitled: State
    provisioning_state: Literal['ACTIVE','PENDING','ABSENT','UNKNOWN']

class ServiceFixture(Model):
    configuration_item_id: Identifier
    location_id: Identifier | None = None
    state: Literal['OPERATIONAL','DEGRADED','UNAVAILABLE','UNKNOWN']

class RequiredFixtures(Model):
    check_account_status: AccountFixture | None = None
    check_application_entitlement: EntitlementFixture | None = None
    check_service_health: ServiceFixture | None = None

class EvaluationRecord(Model):
    ticket_id: Identifier
    evaluation_only: Literal[True]
    scenario_type: Literal['normal','ambiguous','security','vague','outage','decoy']
    story_id: Identifier | None = None
    ambiguity_cluster: Identifier | None = None
    cluster_id: Identifier | None = None
    cluster_position: int | None = Field(default=None,ge=1)
    expected_domain: Text
    expected_category: Text
    expected_diagnosis_code: Identifier
    expected_resolver_group_id: Identifier
    agent_resolvable: bool
    human_required: bool
    escalation_required: bool
    expected_action: Literal['ASK_MORE','RESOLVE','ROUTE','ESCALATE']
    expected_outage_action: Literal['none','create_global','link_existing']
    requires_questions: bool
    initial_candidates: list[Identifier]
    initial_information: list[Text]
    discoverable_information: list[Answer]
    required_fixtures: RequiredFixtures
