"""Standalone diagnostic facade. Backend integration is intentionally omitted.

This facade provides a local, testable entry point and optional LLM-assisted
question proposal. It never claims to run checks, write backend worklogs, route,
or resolve a ticket because those operations require the backend integration.
"""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from .engine import start_investigation, build_result, submit_answer
from .llm import OpenAICompatibleClient, LLMConfigurationError, LLMRequestError, propose_next_step
from .models import TicketInput
from .session_store import JsonSessionStore


def _knowledge_match_strength(state: Any) -> str:
    """Derive knowledge-match strength from actual retrieval scores."""
    if not state.knowledge_matches:
        return "LOW"
    best_score = max(m.get("score", 0) for m in state.knowledge_matches)
    if best_score >= 5:
        return "HIGH"
    if best_score >= 2:
        return "MEDIUM"
    return "LOW"


def _historical_agreement(state: Any) -> str:
    """Compute how many similar historical tickets share the confirmed/leading diagnosis."""
    if not state.historical_matches:
        return "NOT_AVAILABLE"
    # Count matches whose diagnosis_code agrees with the current leading candidate.
    leading = state.final_diagnosis
    if leading is None and state.candidates:
        # Use the top-ranked candidate as a proxy for in-progress sessions.
        from .engine import rank_candidates
        ranked = rank_candidates(state)
        leading = ranked[0]["diagnosis_id"] if ranked else None
    if leading is None:
        return "NOT_AVAILABLE"
    agreeing = sum(
        1 for m in state.historical_matches
        if m.get("diagnosis_code") == leading
    )
    total = len(state.historical_matches)
    return f"{agreeing}/{total}"


def _public_result(state: Any) -> dict[str, Any]:
    from .answers import diagnostic_findings
    result = asdict(build_result(state))
    # Replace internal heuristic float with evidence-based categorical confidence.
    result.pop("confidence", None)

    km_strength = _knowledge_match_strength(state)
    hist_agreement = _historical_agreement(state)
    alternatives_excluded = bool(state.eliminated_diagnoses)

    if state.status == "diagnosed":
        # Confidence is graded: HIGH needs strong match + history agreement
        if (km_strength == "HIGH"
                and hist_agreement != "NOT_AVAILABLE"
                and int(hist_agreement.split('/')[0]) > 0
                and alternatives_excluded):
            confidence = "HIGH"
        elif km_strength in ("HIGH", "MEDIUM") or alternatives_excluded:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        basis = {
            "knowledge_match_strength": km_strength,
            "evidence_completeness": "PARTIAL",  # no backend checks in standalone
            "historical_agreement": hist_agreement,
            "alternatives_excluded": alternatives_excluded,
            "note": "Standalone mode: no backend checks performed; verify with integrated mode.",
        }
    elif state.status == "escalated":
        confidence = "LOW"
        basis = {
            "knowledge_match_strength": km_strength,
            "evidence_completeness": "LOW",
            "historical_agreement": hist_agreement,
            "alternatives_excluded": False,
        }
    else:
        confidence = "LOW"
        basis = {
            "knowledge_match_strength": km_strength,
            "evidence_completeness": "LOW",
            "historical_agreement": hist_agreement,
            "alternatives_excluded": alternatives_excluded,
        }
    result["confidence"] = confidence
    result["confidence_basis"] = basis
    result["outcome"] = "HUMAN_REQUIRED" if state.recommended_action == "escalate" else ("DIAGNOSED" if state.final_diagnosis else "INCONCLUSIVE")
    result["recommended_action"] = {
        "investigate": "ASK_MORE",
        "route": "ROUTE",
        "escalate": "ESCALATE",
    }.get(state.recommended_action, "ASK_MORE")
    result["diagnosis_code"] = state.final_diagnosis
    result["knowledge_article_ids"] = sorted({
        str(item.get("article_id")) for item in state.knowledge_matches if item.get("article_id")
    })
    result["historical_ticket_ids"] = sorted({
        str(item.get("ticket_id")) for item in state.historical_matches if item.get("ticket_id")
    })
    result["evidence_ids"] = [e.evidence_id for e in state.evidence]
    result["next_question"] = state.next_question
    result["completed_actions"] = []
    result["integration_status"] = "LOCAL_ONLY_BACKEND_NOT_CONNECTED"
    result['diagnostic_findings'] = diagnostic_findings(state)
    result['available_self_service_guides'] = [m['self_service_guidance'] for m in state.knowledge_matches if m.get('self_service_guidance')]
    return result


def run_ticket(ticket_data: dict[str, Any], *, store: JsonSessionStore | None = None,
               use_llm: bool = False, client: OpenAICompatibleClient | None = None,
               articles_path: str | Path | None = None) -> dict[str, Any]:
    ticket = TicketInput(**ticket_data)
    state = store.load(ticket.ticket_id) if store else None
    if state is None:
        state = start_investigation(ticket, **({'articles_path': articles_path} if articles_path else {}))
    # LLM can suggest an improved question, but only if it is configured and
    # the deterministic engine has not already mandated human escalation.
    llm_note = None
    if use_llm and state.status != "escalated":
        try:
            client = client or OpenAICompatibleClient()
            proposal = propose_next_step(client, {
                "ticket": asdict(state.ticket),
                "candidates": [asdict(c) for c in state.candidates],
                "evidence": [asdict(e) for e in state.evidence],
                "knowledge_matches": state.knowledge_matches,
                "historical_matches": state.historical_matches,
                "questions_already_asked": state.questions_asked,
                "current_question": state.next_question,
                "mode": "question_planning_only_no_tool_execution",
            })
            suggested = proposal.get("next_question")
            if isinstance(suggested, str) and suggested.strip() and suggested not in state.questions_asked:
                state.next_question = suggested.strip()
                if state.next_question not in state.questions_asked:
                    state.questions_asked.append(state.next_question)
            llm_note = {
                "status": "proposal_received",
                "question_purpose": proposal.get("question_purpose"),
                "missing_information": proposal.get("missing_information", []),
                "rationale": proposal.get("rationale"),
                "candidate_diagnoses": proposal.get("candidate_diagnoses", []),
                "warning": "LLM suggestions are not evidence and do not authorize actions."
            }
        except (LLMConfigurationError, LLMRequestError) as exc:
            llm_note = {"status": "unavailable", "reason": str(exc), "fallback": "deterministic engine"}
    if store:
        store.save(state)
    result = _public_result(state)
    result["llm"] = llm_note or {"status": "not_used"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the standalone IT Diagnostic Agent (no backend integration).")
    parser.add_argument("--ticket-json", required=True, help="Path to a JSON file containing TicketInput fields")
    parser.add_argument("--sessions-dir", default="data/sessions", help="Directory for persistent local state")
    parser.add_argument("--use-llm", action="store_true", help="Use configured OpenAI-compatible LLM for question planning")
    parser.add_argument("--answer", help="Answer the current question for an existing session")
    parser.add_argument("--evidence-id", help="Evidence ID for --answer")
    args = parser.parse_args()
    payload = json.loads(Path(args.ticket_json).read_text(encoding="utf-8"))
    store = JsonSessionStore(args.sessions_dir)
    if args.answer is not None:
        ticket_id = payload["ticket_id"]
        state = store.load(ticket_id)
        if state is None:
            raise SystemExit(f"No saved session found for {ticket_id!r}; run without --answer first.")
        if not args.evidence_id:
            raise SystemExit("--evidence-id is required with --answer")
        submit_answer(state, args.answer, args.evidence_id)
        store.save(state)
        print(json.dumps(_public_result(state), ensure_ascii=False, indent=2))
        return
    print(json.dumps(run_ticket(payload, store=store, use_llm=args.use_llm), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
