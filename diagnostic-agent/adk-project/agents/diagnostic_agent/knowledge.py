
"""Knowledge retrieval for the IT Diagnostic Agent.

Uses approved diagnostic articles stored as JSON.
Retrieval is deterministic and explainable; it does not diagnose
a ticket or authorize a resolution by itself.
"""

import json
import re
from pathlib import Path
from typing import Any


# Locate the knowledge directory relative to the adk-project root.
# File is at: adk-project/agents/diagnostic_agent/knowledge.py
# parents[2]  => adk-project/

ADK_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = ADK_ROOT / "knowledge"
ARTICLES_FILE = KNOWLEDGE_DIR / "diagnostic_articles.json"

APPROVED_STATUSES = {"approved", "published", "active"}
MIN_SCORE = 1


def _normalise(text: str) -> str:
    """Lowercase text and standardize whitespace."""
    return " ".join(text.lower().strip().split())


def _tokens(text: str) -> set[str]:
    """Extract simple word tokens for deterministic matching."""
    return set(re.findall(r"[^\W]+", _normalise(text), flags=re.UNICODE))


def _load_json(path: Path) -> Any:
    """Read and parse a JSON file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Knowledge file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_articles(data: Any) -> list[dict]:
    """Support common top-level JSON article structures."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        # Common collection keys used by knowledge exports.
        for key in ("articles", "diagnostic_articles", "items", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]

        # A single article document.
        if any(
            key in data
            for key in ("article_id", "knowledge_id", "diagnosis")
        ):
            return [data]

    raise ValueError(
        "Unsupported diagnostic articles JSON structure. "
        "Inspect diagnostic_articles.json and update "
        "_extract_articles() to match its actual schema."
    )


def _article_id(article: dict) -> str | None:
    """Return the article's identifier using known field names."""
    for key in ("article_id", "knowledge_id", "id", "kb_id"):
        value = article.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _is_approved(article: dict) -> bool:
    """Fail closed: articles without explicit approval are excluded."""
    status = article.get("approval_status", article.get("status"))

    if isinstance(status, str):
        return status.strip().lower() in APPROVED_STATUSES

    # Support an explicit boolean approval field.
    for key in ("approved", "is_approved"):
        if article.get(key) is True:
            return True

    return False


def _collect_text(value: Any) -> str:
    """Convert nested article content into searchable text."""
    if isinstance(value, str):
        return value

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, list):
        return " ".join(_collect_text(item) for item in value)

    if isinstance(value, dict):
        return " ".join(
            _collect_text(item) for item in value.values()
        )

    return ""


def _searchable_text(article: dict) -> str:
    """Build the text used for article matching."""
    fields = (
        "title",
        "name",
        "diagnosis",
        "diagnosis_code",
        "domain",
        "category",
        "subcategory",
        "symptoms",
        "symptoms_en",
        "symptoms_ar",
        "symptoms_franco_ar",
        "discriminating_questions",
        "safe_checks",
        "resolution_steps",
        "resolution_conditions",
        "mandatory_human_escalation_conditions",
        "competing_diagnoses",
        "keywords",
        "possible_causes",
        "causes",
        "required_evidence",
        "diagnostic_questions",
        "questions",
        "exclusion_criteria",
        "similar_diagnoses",
    )

    return " ".join(
        _collect_text(article.get(field, ""))
        for field in fields
    )


def load_articles(
    path: Path | str = ARTICLES_FILE,
    approved_only: bool = True,
) -> list[dict]:
    """Load articles and optionally restrict to approved articles."""
    data = _load_json(Path(path))
    articles = _extract_articles(data)

    if approved_only:
        articles = [
            article for article in articles
            if _is_approved(article)
        ]

    # Ignore records without IDs so results can be traced reliably.
    return [
        article for article in articles
        if _article_id(article) is not None
    ]


def search_articles(
    query: str,
    limit: int = 5,
    path: Path | str = ARTICLES_FILE,
    *, approved_only: bool = True, diagnosis_codes: set[str] | None = None,
) -> list[dict]:
    """Rank approved articles using explainable lexical matching.

    Returns article data, a simple relevance score, and matching terms.
    A score is a ranking signal, not a probability or confidence value.
    """
    if not query or not query.strip():
        return []

    if limit < 1:
        raise ValueError("limit must be at least 1")

    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    results = []

    for article in load_articles(path=path, approved_only=approved_only):
        if diagnosis_codes is not None and article.get('diagnosis_code') not in diagnosis_codes:
            continue
        if article.get('guided_self_service') and not _guidance_topic_matches(article, query):
            continue
        article_text = _normalise(_searchable_text(article))
        article_tokens = _tokens(article_text)

        matched_terms = sorted(query_tokens & article_tokens)

        # Simple baseline: reward query terms found in the article.
        score = len(matched_terms)

        # Reward a full phrase match.
        normalized_query = _normalise(query)
        if normalized_query in article_text:
            score += 3

        if score < MIN_SCORE:
            continue

        results.append({
            "article_id": _article_id(article),
            "title": article.get(
                "title",
                article.get("name", _article_id(article)),
            ),
            "score": score,
            "matched_terms": matched_terms,
            "article": article,
        })

    results.sort(
        key=lambda item: (
            -item["score"],
            str(item["article_id"]),
        )
    )

    return results[:limit]


def _guidance_topic_matches(article: dict, query: str) -> bool:
    """Require a named endpoint topic before suggesting a specific local guide.

    Generic terms such as device, connection and configuration are insufficient.
    This is a retrieval filter, not evidence that the setting caused the fault.
    """
    patterns = {
        'WIFI_DISABLED': r'wi[ -]?fi|wireless|واي.?فاي|وايرلس',
        'WRONG_PRINTER_SELECTED': r'print|طابع|طباع',
        'SPEAKERS_MUTED': r'audio|sound|speaker|volume|صوت|سماع',
        'WRONG_AUDIO_OUTPUT': r'audio|sound|speaker|headset|صوت|سماع',
        'WRONG_TEAMS_MICROPHONE': r'microphone|\bmic\b|ميكروفون|مايك',
        'BROWSER_ZOOM_SETTING': r'zoom|browser.{0,25}(large|small)|زووم|تكبير|تصغير',
        'KEYBOARD_LAYOUT_SETTING': r'keyboard|layout|كيبورد|لوحة المفاتيح',
        'LOW_DISPLAY_BRIGHTNESS': r'brightness|\bdim\b|سطوع|شاشة.{0,15}مظلم',
        'DISPLAY_PROJECTION_SETTING': r'monitor|projection|display mode|second.{0,10}screen|شاشة ثانية|عرض الشاش',
        'BLUETOOTH_DISABLED': r'bluetooth|بلوتوث',
        'CAMERA_SHUTTER_CLOSED': r'camera|webcam|كاميرا',
        'DO_NOT_DISTURB_NOTIFICATIONS': r'notification|do not disturb|اشعار|إشعار|عدم الإزعاج',
    }
    pattern = patterns.get(article.get('scenario_code'))
    return bool(pattern and re.search(pattern, query, re.IGNORECASE))


def get_article_by_id(
    article_id: str,
    path: Path | str = ARTICLES_FILE,
) -> dict | None:
    """Return one approved article by its exact ID."""
    for article in load_articles(path=path, approved_only=True):
        if _article_id(article) == article_id:
            return article

    return None


def get_next_questions(article: dict) -> list:
    """Extract diagnostic questions without inventing new ones."""
    for key in ("diagnostic_questions", "discriminating_questions", "questions"):
        value = article.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            return [value]

    return []


def get_resolution_guidance(article: dict) -> dict:
    """Return guidance and safety conditions; never execute a fix."""
    return {
        "article_id": _article_id(article),
        "resolvable_by_agent": article.get(
            "resolvable_by_agent",
            article.get("agent_resolvable", False),
        ),
        "resolution_steps": article.get(
            "resolution_steps",
            article.get("resolution_steps_by_level", []),
        ),
        "resolution_conditions": article.get(
            "resolution_conditions",
            article.get("agent_resolution_conditions", []),
        ),
        "required_evidence": article.get(
            "required_evidence", []
        ),
        "mandatory_human_escalation": article.get(
            "mandatory_human_escalation_conditions",
            article.get("mandatory_human_escalation", article.get("human_escalation_conditions", [])),
        ),
    }
