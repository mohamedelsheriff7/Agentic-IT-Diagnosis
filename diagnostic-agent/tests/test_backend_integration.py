from __future__ import annotations
import json
from diagnostic_agent.backend_client import DiagnosticBackendClient, BackendConfigurationError
from diagnostic_agent.integrated import investigate_ticket

class FakeBackend:
    def __init__(self, ticket):
        self.ticket = ticket
        self.calls = []
    def get_ticket_details(self, ticket_id):
        self.calls.append(("get_ticket_details", ticket_id)); return self.ticket
    def search_diagnostic_knowledge(self, payload):
        self.calls.append(("search_diagnostic_knowledge", payload)); return {"results": []}
    def search_similar_tickets(self, payload):
        self.calls.append(("search_similar_tickets", payload)); return {"results": []}
    def check_account_status(self, payload):
        self.calls.append(("check_account_status", payload)); return {"status": "UNKNOWN", "evidence_id": "E-1"}
    def check_application_entitlement(self, payload):
        self.calls.append(("check_application_entitlement", payload)); return {"status": "UNKNOWN", "evidence_id": "E-2"}
    def check_service_health(self, payload):
        self.calls.append(("check_service_health", payload)); return {"status": "UNKNOWN", "evidence_id": "E-3"}
    def request_human_review(self, ticket_id, payload):
        self.calls.append(("request_human_review", payload)); return {"state": "REQUESTED"}
    def record_diagnostic_result(self, ticket_id, payload):
        self.calls.append(("record_diagnostic_result", payload)); return {"result_id": "DR-1"}
    def add_worklog_entry(self, ticket_id, payload):
        self.calls.append(("add_worklog_entry", payload)); return {"worklog_id": "WL-1"}

def test_backend_client_requires_key():
    try:
        DiagnosticBackendClient(base_url="https://example.test", api_key="")
    except BackendConfigurationError:
        pass
    else:
        raise AssertionError("API key should be required")

def test_normal_ticket_initial_investigation_records_inconclusive_not_resolve():
    client = FakeBackend({"ticket_id":"T-1", "summary":"Cannot access portal", "description":"Access denied when opening portal", "status":"IN_PROGRESS", "reported_priority":3, "reported_by_id":"U-1", "affected_person_id":"U-1", "configuration_item_id":"APP-1", "language":"en"})
    result = investigate_ticket(client, "T-1")
    assert result["integration_status"] == "BACKEND_CONNECTED"
    assert result["outcome"] == "INCONCLUSIVE"
    assert result["recommended_action"] == "ASK_MORE"
    assert any(c[0] == "check_account_status" for c in client.calls)
    assert any(c[0] == "check_application_entitlement" for c in client.calls)
    assert any(c[0] == "record_diagnostic_result" for c in client.calls)
    assert any(c[0] == "add_worklog_entry" for c in client.calls)
    assert not any(c[0] in {"resolve_ticket", "assign_ticket", "create_global_ticket"} for c in client.calls)

def test_priority_one_mandates_human_review_and_never_resolves():
    client = FakeBackend({"ticket_id":"T-2", "summary":"VPN down", "description":"VPN unavailable", "status":"IN_PROGRESS", "reported_priority":1, "reported_by_id":"U-2", "configuration_item_id":"CI-VPN", "location_id":"LOC-1"})
    result = investigate_ticket(client, "T-2")
    assert result["outcome"] == "HUMAN_REQUIRED"
    assert result["recommended_action"] == "ESCALATE"
    assert any(c[0] == "request_human_review" for c in client.calls)
    record = next(c[1] for c in client.calls if c[0] == "record_diagnostic_result")
    assert record["outcome"] == "HUMAN_REQUIRED"
    assert not any(c[0] in {"resolve_ticket", "assign_ticket", "create_global_ticket"} for c in client.calls)

def test_closed_ticket_is_read_only():
    client = FakeBackend({"ticket_id":"T-3", "summary":"Done", "description":"Already fixed", "status":"CLOSED", "reported_priority":3})
    result = investigate_ticket(client, "T-3")
    assert result["status"] == "CLOSED"
    assert len(client.calls) == 1
