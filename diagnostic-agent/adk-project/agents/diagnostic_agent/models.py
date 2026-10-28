# This file defines the language our agent uses to represent a ticket, a possible diagnosis, a piece of evidence, and a diagnostic decision. 

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------
# 1. Incoming ticket: information available at intake
# ---------------------------------------------------------

@dataclass
class TicketInput:
    """Ticket information available when the agent starts."""

    ticket_id: str
    summary: str
    description: str

    # Maps to reported_priority in the historical dataset.
    priority: str = "unknown"

    ticket_class: str = "INCIDENT"
    impact: Optional[str] = None
    urgency: Optional[str] = None
    language: Optional[str] = None

    domain: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    severity: Optional[str] = None

    asset_id: Optional[str] = None
    configuration_item_id: Optional[str] = None
    location_id: Optional[str] = None

    security_sensitive: bool = False
    privileged_access: bool = False

    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------
# 2. Historical ticket: information about a past case
# ---------------------------------------------------------

@dataclass
class HistoricalTicket:
    """A historical ticket and its recorded outcome."""

    ticket: TicketInput

    status: str
    diagnosis_code: Optional[str] = None
    owner_group_id: Optional[str] = None
    owner_id: Optional[str] = None
    reported_by_id: Optional[str] = None
    affected_person_id: Optional[str] = None

    initial_owner_group_id: Optional[str] = None
    linked_solution_id: Optional[str] = None
    resolution_summary: Optional[str] = None

    is_global: bool = False
    global_ticket_id: Optional[str] = None

    reported_at: Optional[str] = None
    target_finish_at: Optional[str] = None
    actual_finish_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Additional source columns that we may need later.
    extra_fields: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------
# 3. Evidence collected during the investigation
# ---------------------------------------------------------

@dataclass
class Evidence:
    """A fact collected during the current investigation."""

    evidence_id: str
    description: str
    value: Any
    source: str
    # Examples: ticket, user_answer, diagnostic_check,
    # historical_ticket
    timestamp: Optional[str] = None
    supports: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)


# ---------------------------------------------------------
# 4. Possible diagnoses
# ---------------------------------------------------------

@dataclass
class DiagnosisCandidate:
    """One possible explanation for the reported symptoms."""

    diagnosis_id: str
    name: str
    domain: str
    category: str
    resolver_group: str

    required_evidence: List[str] = field(default_factory=list)
    supporting_evidence_ids: List[str] = field(default_factory=list)
    contradicting_evidence_ids: List[str] = field(default_factory=list)

    # Allowed states: plausible, confirmed, eliminated
    status: str = "plausible"
    elimination_reason: Optional[str] = None
    knowledge_article_id: Optional[str] = None


# ---------------------------------------------------------
# 5. Trace of diagnostic decisions
# ---------------------------------------------------------

@dataclass
class DiagnosticStep:
    """One event in the diagnostic trace."""

    step_number: int
    event_type: str
    description: str
    evidence_ids: List[str] = field(default_factory=list)
    candidate_ids: List[str] = field(default_factory=list)
    rationale: Optional[str] = None


# ---------------------------------------------------------
# 6. Current investigation state
# ---------------------------------------------------------

@dataclass
class DiagnosticState:
    """Everything the agent needs to remember while investigating."""

    ticket: TicketInput
    candidates: List[DiagnosisCandidate] = field(default_factory=list)
    archived_candidates: List[DiagnosisCandidate] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)
    eliminated_diagnoses: List[Dict[str, str]] = field(default_factory=list)
    trace: List[DiagnosticStep] = field(default_factory=list)
    # Retrieved context is advisory, not proof about the current ticket.
    knowledge_matches: List[Dict[str, Any]] = field(default_factory=list)
    historical_matches: List[Dict[str, Any]] = field(default_factory=list)

    next_question: Optional[str] = None
    final_diagnosis: Optional[str] = None
    confidence: Optional[float] = None
    recommended_action: str = "investigate"
    rationale: Optional[str] = None
    status: str = "in_progress"
    diagnostic_result_id: Optional[str] = None
    diagnostic_result_version: Optional[int] = None


# ---------------------------------------------------------
# 7. Structured result returned by the agent
# ---------------------------------------------------------

@dataclass
class DiagnosticResult:
    """The structured result returned by the agent."""

    ticket_id: str
    diagnosis: Optional[str]
    evidence: List[Evidence]
    confidence: Optional[float]
    recommended_action: str
    rationale: str
    next_question: Optional[str]
    remaining_candidates: List[DiagnosisCandidate]
    eliminated_diagnoses: List[Dict[str, str]]
    trace: List[DiagnosticStep]
    status: str
    knowledge_article_id: Optional[str] = None
    knowledge_matches: List[Dict[str, Any]] = field(default_factory=list)
    historical_matches: List[Dict[str, Any]] = field(default_factory=list)
    candidate_rankings: List[Dict[str, Any]] = field(default_factory=list)
