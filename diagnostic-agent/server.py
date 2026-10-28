"""HTTP hosting for the independently runnable diagnostic agent.

Run with python serve.py. Credentials are loaded from the repository .env.
"""
from __future__ import annotations

import os
import secrets
import sys
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'adk-project' / 'agents'))
from diagnostic_agent.backend_client import DiagnosticBackendClient, BackendConfigurationError, BackendRequestError
from diagnostic_agent.engine import submit_answer
from diagnostic_agent.integrated import investigate_ticket, submit_answer_and_continue, confirm_resolution_and_close
from diagnostic_agent.models import TicketInput
from diagnostic_agent.session_store import JsonSessionStore
from diagnostic_agent.standalone import run_ticket, _public_result
from diagnostic_agent.llm import redact_secrets

Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')]
Mode = Literal['local', 'backend']
lock = RLock()  # serialize state transitions; run one worker for the JSON store
api_key = APIKeyHeader(name='X-API-Key', auto_error=False)

def authorize(key: str | None = Depends(api_key)):
    expected = os.getenv('DIAGNOSTIC_SERVICE_API_KEY', '')
    if not expected or not key or not secrets.compare_digest(key, expected):
        raise HTTPException(401, 'Valid agent service X-API-Key required.')

app = FastAPI(title='IT Diagnostic Agent API', version='1.0.0',
    description='Stateful diagnosis, targeted questions, evidence and confirmed resolution. Local mode performs no backend actions.',
    servers=[{'url': os.getenv('DIAGNOSTIC_PUBLIC_URL', 'http://127.0.0.1:8080')}])

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class LocalTicket(Input):
    ticket_id: Identifier
    summary: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=16000)
    priority: str = '3'
    language: str | None = None
    security_sensitive: bool = False
    privileged_access: bool = False
    configuration_item_id: str | None = None
    location_id: str | None = None

class Start(Input):
    mode: Mode = 'local'
    ticket_id: Identifier
    ticket: LocalTicket | None = None
    use_llm: bool = False

class Answer(Input):
    mode: Mode = 'local'
    answer: str = Field(min_length=1, max_length=16000)
    evidence_id: Identifier

class Confirm(Input):
    confirmed_by_user: bool
    completed_step_ids: list[str] = Field(default_factory=list)

class GraphChat(Input):
    session_id: Identifier
    message: str = Field(min_length=1, max_length=32000)
    mode: Mode = 'local'

def store_for(mode: Mode):
    return JsonSessionStore(Path(os.getenv('DIAGNOSTIC_SESSIONS_DIR', str(ROOT / 'data' / 'sessions'))) / mode)

def knowledge_options():
    path = os.getenv('DIAGNOSTIC_ARTICLES_FILE')
    return {'articles_path': Path(path) if Path(path).is_absolute() else ROOT / path} if path else {}

def execute(fn):
    try:
        with lock:
            def sanitized(value, field=''):
                if field.endswith(('_id', '_ids')) or field in {'event_type', 'diagnosis_code', 'diagnosis_id', 'remaining_candidates', 'source', 'tool', 'status', 'recommended_action', 'framework'}:
                    return value  # Exact canonical identifiers are references, not free text.
                if isinstance(value, str):
                    return redact_secrets(value)
                if isinstance(value, dict):
                    return {k: sanitized(v, k) for k, v in value.items()}
                if isinstance(value, list):
                    return [sanitized(v) for v in value]
                return value
            return sanitized(fn())
    except BackendConfigurationError:
        raise HTTPException(503, 'Set DIAGNOSTIC_BACKEND_API_KEY in the server .env, then restart.') from None
    except BackendRequestError as exc:
        raise HTTPException(502, {'message': str(exc), 'backend_status': exc.status}) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None

@app.get('/health', operation_id='agent_health')
def health():
    return {'status': 'ok', 'backend_configured': bool(os.getenv('DIAGNOSTIC_BACKEND_API_KEY')),
            'llm_configured': all(os.getenv(k) for k in ('DIAGNOSTIC_LLM_BASE_URL', 'DIAGNOSTIC_LLM_API_KEY', 'DIAGNOSTIC_LLM_MODEL'))}

@app.get('/', include_in_schema=False, response_class=HTMLResponse)
def home():
    return '<h1>IT Diagnostic Agent</h1><p>Service is running. Open <a href="/docs">Swagger API console</a> to start an investigation.</p>'

@app.post('/investigations', operation_id='start_diagnostic_investigation', dependencies=[Depends(authorize)])
def start(body: Start) -> dict:
    def run():
        store = store_for(body.mode)
        if body.mode == 'backend':
            if body.ticket is not None or body.use_llm:
                raise ValueError('Backend mode fetches the ticket by ID and currently uses deterministic diagnostic rules.')
            return investigate_ticket(DiagnosticBackendClient(), body.ticket_id, store=store, **knowledge_options())
        if body.ticket is None or body.ticket.ticket_id != body.ticket_id:
            raise ValueError('Local mode needs ticket data with the same ticket_id.')
        return run_ticket(body.ticket.model_dump(), store=store, use_llm=body.use_llm, **knowledge_options())
    return execute(run)

@app.post('/investigations/{ticket_id}/answers', operation_id='answer_diagnostic_question', dependencies=[Depends(authorize)])
def answer(ticket_id: Identifier, body: Answer) -> dict:
    def run():
        store = store_for(body.mode)
        if body.mode == 'backend':
            return submit_answer_and_continue(DiagnosticBackendClient(), ticket_id, body.answer, body.evidence_id, store, **knowledge_options())
        state = store.load(ticket_id)
        if state is None:
            raise HTTPException(404, 'No investigation exists for this ticket.')
        submit_answer(state, redact_secrets(body.answer), body.evidence_id)
        store.save(state)
        return _public_result(state)
    return execute(run)

@app.get('/investigations/{ticket_id}', operation_id='get_diagnostic_trace', dependencies=[Depends(authorize)])
def trace(ticket_id: Identifier, mode: Mode = 'local') -> dict:
    def run():
        state = store_for(mode).load(ticket_id)
        if state is None:
            raise HTTPException(404, 'No investigation exists for this ticket.')
        return {'mode': mode, 'state': asdict(state)}
    return execute(run)

@app.post('/investigations/{ticket_id}/resolution', operation_id='confirm_diagnostic_resolution', dependencies=[Depends(authorize)])
def resolution(ticket_id: Identifier, body: Confirm) -> dict:
    return execute(lambda: confirm_resolution_and_close(DiagnosticBackendClient(), ticket_id,
        body.confirmed_by_user, body.completed_step_ids, store_for('backend'), **knowledge_options()))

@app.post('/langgraph/chat', operation_id='chat_with_langgraph_agent', dependencies=[Depends(authorize)])
def graph_chat(body: GraphChat) -> dict:
    """Local test host for the same factory that WXO imports natively."""
    def run():
        import json
        import sqlite3
        from langchain_core.messages import HumanMessage
        from langgraph.checkpoint.sqlite import SqliteSaver
        from wxo_langgraph.agent import create_agent, diagnostic_payload
        if not hasattr(app.state, 'langgraph_checkpointer'):
            directory = Path(os.getenv('DIAGNOSTIC_SESSIONS_DIR', str(ROOT / 'data' / 'sessions')))
            directory.mkdir(parents=True, exist_ok=True)
            app.state.langgraph_connection = sqlite3.connect(directory / 'langgraph.sqlite', check_same_thread=False)
            app.state.langgraph_checkpointer = SqliteSaver(app.state.langgraph_connection)
            app.state.langgraph_apps = {}
        if body.mode not in app.state.langgraph_apps:
            builder = create_agent({'configurable': {'mode': body.mode}})
            app.state.langgraph_apps[body.mode] = builder.compile(checkpointer=app.state.langgraph_checkpointer)
        graph = app.state.langgraph_apps[body.mode]
        output = graph.invoke({'messages': [HumanMessage(content=body.message)]},
            {'configurable': {'thread_id': body.mode + ':' + body.session_id}})
        message = output['messages'][-1]
        return {**diagnostic_payload(message), 'reply': message.content}
    return execute(run)
