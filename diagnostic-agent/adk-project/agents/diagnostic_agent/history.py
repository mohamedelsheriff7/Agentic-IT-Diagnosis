
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import HistoricalTicket, TicketInput


@dataclass
class HistoricalMatch:
    """A historical ticket retrieved as a possible match."""

    historical_ticket: HistoricalTicket
    score: float
    matched_on: list[str]


def _redact_secrets(text: str) -> str:
    """Redact synthetic secrets and simple password assignments."""

    text = re.sub(
        r"\bSYNTH_SECRET_[A-Za-z0-9_-]+\b",
        "[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"(?i)\b(password|passwd)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        text,
    )

    return text


def _optional_str(value) -> str | None:
    """Convert a non-empty value to a string, or None."""

    if value is None or value == "":
        return None

    return str(value)


def _optional_bool(value) -> bool:
    """Safely convert common JSON Boolean representations."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}

    return bool(value) if value is not None else False


def _ticket_from_record(record: dict) -> TicketInput:
    """Convert a JSON record into the ticket intake model."""

    summary = _redact_secrets(str(record.get("summary") or ""))
    description = _redact_secrets(
        str(record.get("description") or "")
    )

    return TicketInput(
        ticket_id=str(record["ticket_id"]),
        summary=summary,
        description=description,
        priority=str(record.get("reported_priority", "unknown")),
        ticket_class=str(record.get("ticket_class") or "INCIDENT"),
        impact=_optional_str(record.get("impact")),
        urgency=_optional_str(record.get("urgency")),
        language=_optional_str(record.get("language")),
        domain=_optional_str(record.get("domain")),
        category=_optional_str(record.get("category")),
        subcategory=_optional_str(record.get("subcategory")),
        severity=_optional_str(record.get("severity")),
        asset_id=_optional_str(record.get("asset_id")),
        configuration_item_id=_optional_str(
            record.get("configuration_item_id")
        ),
        location_id=_optional_str(record.get("location_id")),
        security_sensitive=_optional_bool(
            record.get("security_sensitive")
        ),
        privileged_access=_optional_bool(
            record.get("privileged_access")
        ),
        metadata={},
    )


def _historical_ticket_from_record(
    record: dict,
) -> HistoricalTicket:
    """Convert one JSON record into a historical ticket."""

    ticket = _ticket_from_record(record)

    resolution_summary = record.get("resolution_summary")

    if resolution_summary:
        resolution_summary = _redact_secrets(
            str(resolution_summary)
        )

    known_fields = {
        "ticket_id",
        "ticket_class",
        "summary",
        "description",
        "status",
        "reported_priority",
        "impact",
        "urgency",
        "language",
        "domain",
        "category",
        "subcategory",
        "diagnosis_code",
        "owner_group_id",
        "owner_id",
        "reported_by_id",
        "affected_person_id",
        "asset_id",
        "configuration_item_id",
        "location_id",
        "reported_at",
        "target_finish_at",
        "actual_finish_at",
        "resolved_at",
        "closed_at",
        "updated_at",
        "linked_solution_id",
        "resolution_summary",
        "is_global",
        "global_ticket_id",
        "severity",
        "security_sensitive",
        "privileged_access",
        "initial_owner_group_id",
    }

    # Preserve additional source fields without losing their values.
    extra_fields = {
        key: value
        for key, value in record.items()
        if key not in known_fields
    }

    return HistoricalTicket(
        ticket=ticket,
        status=str(record.get("status") or "UNKNOWN"),
        diagnosis_code=_optional_str(record.get("diagnosis_code")),
        owner_group_id=_optional_str(record.get("owner_group_id")),
        owner_id=_optional_str(record.get("owner_id")),
        reported_by_id=_optional_str(record.get("reported_by_id")),
        affected_person_id=_optional_str(
            record.get("affected_person_id")
        ),
        initial_owner_group_id=_optional_str(
            record.get("initial_owner_group_id")
        ),
        linked_solution_id=_optional_str(
            record.get("linked_solution_id")
        ),
        resolution_summary=resolution_summary,
        is_global=_optional_bool(record.get("is_global")),
        global_ticket_id=_optional_str(
            record.get("global_ticket_id")
        ),
        reported_at=_optional_str(record.get("reported_at")),
        target_finish_at=_optional_str(
            record.get("target_finish_at")
        ),
        actual_finish_at=_optional_str(
            record.get("actual_finish_at")
        ),
        resolved_at=_optional_str(record.get("resolved_at")),
        closed_at=_optional_str(record.get("closed_at")),
        updated_at=_optional_str(record.get("updated_at")),
        extra_fields=extra_fields,
    )


def load_historical_tickets(
    path: str | Path,
) -> list[HistoricalTicket]:
    """Load and validate historical tickets from a JSON array."""

    file_path = Path(path)

    with file_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError(
            "Historical ticket JSON must contain a list of ticket objects."
        )

    tickets = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"Record at index {index} must be a JSON object."
            )

        if not record.get("ticket_id"):
            raise ValueError(
                f"Record at index {index} is missing ticket_id."
            )

        tickets.append(_historical_ticket_from_record(record))

    return tickets


def _tokenize(text: str) -> set[str]:
    """Split text into normalized English words and numbers."""

    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _similarity(
    query: TicketInput,
    historical: HistoricalTicket,
) -> HistoricalMatch | None:
    """Score one resolved historical ticket against a new ticket."""

    past_ticket = historical.ticket

    # Do not retrieve the same ticket as its own historical match.
    if query.ticket_id == past_ticket.ticket_id:
        return None

    # Only use tickets with completed outcomes.
    if historical.status.strip().upper() not in {"RESOLVED", "CLOSED"}:
        return None

    query_text = _redact_secrets(
        f"{query.summary} {query.description}"
    )

    past_text = _redact_secrets(
        f"{past_ticket.summary} {past_ticket.description}"
    )

    query_tokens = _tokenize(query_text)
    past_tokens = _tokenize(past_text)

    # Jaccard similarity: shared words / all distinct words.
    union = query_tokens | past_tokens
    intersection = query_tokens & past_tokens

    text_score = (
        len(intersection) / len(union)
        if union
        else 0.0
    )

    # Start the score with text similarity.
    score = 0.7 * text_score

    matched_on = []

    if intersection:
        matched_on.append("shared_ticket_terms")

    # Add points for matching diagnostic classifications.
    for field_name, weight in (
        ("domain", 0.10),
        ("category", 0.10),
        ("subcategory", 0.10),
    ):
        query_value = getattr(query, field_name)
        past_value = getattr(past_ticket, field_name)

        if (
            query_value
            and past_value
            and query_value.strip().casefold()
            == past_value.strip().casefold()
        ):
            score += weight
            matched_on.append(field_name)

    # Filter out matches with almost no similarity.
    min_similarity_score = 0.05

    if score < min_similarity_score:
        return None

    return HistoricalMatch(
        historical_ticket=historical,
        score=min(score, 1.0),
        matched_on=matched_on,
    )


def retrieve_similar_tickets(
    query: TicketInput,
    historical_tickets: list[HistoricalTicket],
    limit: int = 5,
) -> list[HistoricalMatch]:
    """Return the highest-scoring resolved historical tickets."""

    if limit < 1:
        raise ValueError("limit must be at least 1.")

    matches = []

    for historical in historical_tickets:
        match = _similarity(query, historical)

        if match is not None:
            matches.append(match)

    # Sort from the highest score to the lowest.
    matches.sort(
        key=lambda match: match.score,
        reverse=True,
    )

    # Return at most the requested number of matches.
    return matches[:limit]
