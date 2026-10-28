"""HTTP adapter for the 17 Workstream C diagnostic backend tools.

Configure DIAGNOSTIC_BACKEND_BASE_URL and DIAGNOSTIC_BACKEND_API_KEY in the
process environment. The key is sent only in the X-API-Key header.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Mapping

DEFAULT_BASE_URL = "https://shelf-roman-swimmable.ngrok-free.dev"

class BackendConfigurationError(RuntimeError):
    pass

class BackendRequestError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail

class DiagnosticBackendClient:
    """Small stdlib-only client with explicit methods for all exported tools."""
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 20.0):
        self.base_url = (base_url or os.getenv("DIAGNOSTIC_BACKEND_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("DIAGNOSTIC_BACKEND_API_KEY")
        self.timeout = timeout
        if not self.base_url.startswith("https://") and not self.base_url.startswith("http://localhost") and not self.base_url.startswith("http://127.0.0.1"):
            raise BackendConfigurationError("Backend URL must use HTTPS except for localhost testing.")
        if not self.api_key:
            raise BackendConfigurationError("Set DIAGNOSTIC_BACKEND_API_KEY before calling the backend.")

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        url = self.base_url + path
        body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
        headers = {"Accept": "application/json", "X-API-Key": self.api_key or ""}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = raw[:1000]
            # Never include request headers or API key in exception messages.
            raise BackendRequestError(f"Backend request failed with HTTP {exc.code} for {method.upper()} {path}.", status=exc.code, detail=detail) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendRequestError(f"Could not reach diagnostic backend ({type(exc).__name__}).") from None
        except json.JSONDecodeError:
            raise BackendRequestError(f"Backend returned non-JSON content for {method.upper()} {path}.") from None

    @staticmethod
    def _id(value: str) -> str:
        if not value or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
            raise ValueError("Invalid ticket ID format")
        return value

    def get_ticket_details(self, ticket_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tickets/{self._id(ticket_id)}")
    def create_ticket(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/tickets", payload)
    def search_similar_tickets(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/tickets/search-similar", payload)
    def search_diagnostic_knowledge(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/knowledge/search", payload)
    def check_account_status(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/diagnostics/account-status", payload)
    def check_application_entitlement(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/diagnostics/application-entitlement", payload)
    def check_service_health(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/diagnostics/service-health", payload)
    def add_worklog_entry(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/worklogs", payload)
    def record_diagnostic_result(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/diagnostic-results", payload)
    def resolve_ticket(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Expose backend validation for explicit testing; the agent workflow never calls this automatically."""
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/resolution", payload)
    def assign_ticket(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/assignment", payload)
    def request_human_review(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/human-reviews", payload)
    def notify_resolver_group(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/notifications", payload)
    def count_recent_tickets(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/tickets/count-recent", payload)
    def find_open_global_tickets(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/global-tickets/search", payload)
    def create_global_ticket(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/global-tickets", payload)
    def link_ticket_to_global_ticket(self, ticket_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/tickets/{self._id(ticket_id)}/global-link", payload)
