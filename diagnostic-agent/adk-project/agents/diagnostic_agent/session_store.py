"""Small JSON persistence for standalone diagnostic sessions (no backend required)."""
from __future__ import annotations
import json
import os
import tempfile
import re
import hashlib
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any
from .models import DiagnosticState, TicketInput, DiagnosisCandidate, Evidence, DiagnosticStep


def _state_to_dict(state: DiagnosticState) -> dict[str, Any]:
    return asdict(state)


def _state_from_dict(data: dict[str, Any]) -> DiagnosticState:
    ticket_fields = {f.name for f in fields(TicketInput)}
    ticket = TicketInput(**{k: v for k, v in data["ticket"].items() if k in ticket_fields})
    state = DiagnosticState(ticket=ticket)
    state.candidates = [DiagnosisCandidate(**item) for item in data.get("candidates", [])]
    state.archived_candidates = [DiagnosisCandidate(**item) for item in data.get('archived_candidates', [])]
    state.evidence = [Evidence(**item) for item in data.get("evidence", [])]
    state.trace = [DiagnosticStep(**item) for item in data.get("trace", [])]
    for key in (
        "questions_asked", "eliminated_diagnoses", "knowledge_matches", "historical_matches",
        "next_question", "final_diagnosis", "confidence", "recommended_action", "rationale", "status",
        "diagnostic_result_id", "diagnostic_result_version"
    ):
        if key in data:
            setattr(state, key, data[key])
    return state


class JsonSessionStore:
    """Persists state per ticket using atomic file replacement."""
    def __init__(self, directory: str | Path = "data/sessions"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, ticket_id: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', ticket_id) or ticket_id in {'.', '..'}:
            raise ValueError('Invalid ticket ID')
        # Preserve ordinary IDs; hash colon-containing IDs to avoid Windows-invalid names and collisions.
        safe_id = ticket_id if ':' not in ticket_id else 'id-' + hashlib.sha256(ticket_id.encode()).hexdigest()
        return self.directory / f"{safe_id}.json"

    def save(self, state: DiagnosticState) -> Path:
        target = self._path(state.ticket.ticket_id)
        fd, temp_name = tempfile.mkstemp(prefix=target.name, suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(_state_to_dict(state), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return target

    def load(self, ticket_id: str) -> DiagnosticState | None:
        path = self._path(ticket_id)
        if not path.exists():
            return None
        return _state_from_dict(json.loads(path.read_text(encoding="utf-8")))
