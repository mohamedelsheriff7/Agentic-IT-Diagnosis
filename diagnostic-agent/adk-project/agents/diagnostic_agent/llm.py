"""Optional OpenAI-compatible Chat Completions client for diagnostic planning.

No credentials are embedded. This module does not call backend tools and never
allows the model to execute mutations. The model proposes; deterministic code
and the eventual backend enforce policy.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_AGENT_DIR = Path(__file__).resolve().parent
_PROMPT_DIR = _AGENT_DIR / "prompts"


def load_system_prompt() -> str:
    """Return shared instructions followed by the Diagnostic Agent role."""
    shared = (_PROMPT_DIR / "shared_instructions.md").read_text(encoding="utf-8")
    role = (_PROMPT_DIR / "diagnostic_agent_role.md").read_text(encoding="utf-8")
    return shared.strip() + "\n\n---\n\n" + role.strip()


def redact_secrets(value: str) -> str:
    """Redact common secret-like values before sending text to a model."""
    patterns = [
        (r"(?i)\b(password|passwd|pwd)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
        (r"(?i)\b(token|api[_ -]?key|secret|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
        (r"\b[A-Za-z0-9_-]{28,}\b", lambda match: match.group(0) if match.group(0) in {
            'diagnosis_confirmed_by_current_ticket_evidence',
            'security_policy_lock_confirmed', 'privileged_access_review_required',
            'entitlement_missing_confirmed', 'application_failure_confirmed',
        } else '[REDACTED_LONG_TOKEN]'),
    ]
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    return value


class LLMConfigurationError(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    pass


class OpenAICompatibleClient:
    """Minimal standard-library client for a compatible Chat Completions API.

    Configure DIAGNOSTIC_LLM_BASE_URL, DIAGNOSTIC_LLM_API_KEY, and
    DIAGNOSTIC_LLM_MODEL in the environment. Base URL should be the API root
    (for example, https://host.example/v1); /chat/completions is appended.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.getenv("DIAGNOSTIC_LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("DIAGNOSTIC_LLM_API_KEY", "")
        self.model = model or os.getenv("DIAGNOSTIC_LLM_MODEL", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def chat_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise LLMConfigurationError(
                "Set DIAGNOSTIC_LLM_BASE_URL, DIAGNOSTIC_LLM_API_KEY, and DIAGNOSTIC_LLM_MODEL."
            )
        user_content = redact_secrets(json.dumps(user_payload, ensure_ascii=False))
        body = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise LLMRequestError(f"LLM endpoint returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMRequestError(f"LLM endpoint could not be reached: {type(exc).__name__}.") from exc
        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError("LLM response was not valid Chat Completions JSON.") from exc
        if not isinstance(result, dict):
            raise LLMRequestError("LLM response JSON must be an object.")
        return result


def propose_next_step(client: OpenAICompatibleClient, context: dict[str, Any]) -> dict[str, Any]:
    """Ask the LLM for a proposal; validate shape and safe action vocabulary."""
    proposal = client.chat_json(load_system_prompt(), context)
    allowed_actions = {"ASK_MORE", "ROUTE", "ESCALATE", "RESOLVE"}
    action = proposal.get("recommended_action", "ASK_MORE")
    if action not in allowed_actions:
        proposal["recommended_action"] = "ASK_MORE"
        proposal.setdefault("validation_warnings", []).append("Invalid action replaced with ASK_MORE.")
    if not isinstance(proposal.get("candidate_diagnoses", []), list):
        proposal["candidate_diagnoses"] = []
    if not isinstance(proposal.get("missing_information", []), list):
        proposal["missing_information"] = []
    if not isinstance(proposal.get("proposed_exclusions", []), list):
        proposal["proposed_exclusions"] = []
    # Model cannot establish approval, evidence IDs, or completed mutations.
    for forbidden in ("tool_results", "evidence_ids_created", "resolved", "assigned", "escalated_completed"):
        proposal.pop(forbidden, None)
    return proposal
