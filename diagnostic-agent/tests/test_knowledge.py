
import json

from pathlib import Path

from diagnostic_agent.knowledge import (
    load_articles,
    search_articles,
    get_article_by_id,
    get_next_questions,
)


def test_search_returns_only_approved_articles(tmp_path: Path):
    fixture = [
        {
            "article_id": "KB-TEST-001",
            "title": "Password expired",
            "approval_status": "approved",
            "symptoms": ["Cannot sign in"],
            "diagnostic_questions": [
                "Can you access other corporate applications?"
            ],
        },
        {
            "article_id": "KB-TEST-002",
            "title": "Account locked",
            "approval_status": "draft",
            "symptoms": ["Cannot sign in"],
        },
    ]

    path = tmp_path / "diagnostic_articles.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    articles = load_articles(path=path)
    results = search_articles("password expired", path=path)

    assert len(articles) == 1
    assert articles[0]["article_id"] == "KB-TEST-001"
    assert results[0]["article_id"] == "KB-TEST-001"


def test_get_article_by_id(tmp_path: Path):
    fixture = [
        {
            "article_id": "KB-TEST-003",
            "title": "VPN connection failure",
            "status": "approved",
        }
    ]

    path = tmp_path / "diagnostic_articles.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    article = get_article_by_id("KB-TEST-003", path=path)

    assert article is not None
    assert article["title"] == "VPN connection failure"


def test_questions_are_extracted():
    article = {
        "diagnostic_questions": [
            "Can other users access the service?",
            "Does the problem happen on another network?",
        ]
    }

    assert len(get_next_questions(article)) == 2