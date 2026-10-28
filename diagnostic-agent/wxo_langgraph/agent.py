"""Native WXO LangGraph factory. Returns an UNCOMPILED StateGraph.

Replies are conversational. Diagnostic state travels in message metadata with
an audited backend checkpoint for hosts that retain only the visible text.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
import base64
import io
import tempfile
import zipfile
import hashlib
import importlib
import importlib.util
import threading
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

_EMBEDDED_CORE = ''  # Build script injects the allowlisted core and knowledge archive.
_CORE_DIRECTORY = None
_CORE_FILES = {}
_RESOURCE_LOCK = threading.RLock()
HERE = Path(__file__).resolve().parent
if _EMBEDDED_CORE:
    _CORE_BYTES = base64.b64decode(_EMBEDDED_CORE)
    _CORE_DIGEST = hashlib.sha256(_CORE_BYTES).hexdigest()
    # No TemporaryDirectory finalizer: another imported factory may still use
    # these modules after the entrypoint object is collected by the host.
    ROOT = Path(tempfile.gettempdir()) / ('isys-core-' + _CORE_DIGEST[:32])
    _CORE_DIRECTORY = ROOT
    with zipfile.ZipFile(io.BytesIO(_CORE_BYTES)) as core:
        _CORE_FILES = {name: core.read(name) for name in core.namelist() if not name.endswith('/')}
else:
    # Development checkout; the built entrypoint always uses its embedded copy.
    ROOT = HERE if (HERE / 'adk-project').exists() else HERE.parent


def _ensure_core_resources():
    """Restore bundled files after host cleanup; never write ticket state here."""
    with _RESOURCE_LOCK:
        for name, expected in _CORE_FILES.items():
            target = (ROOT / name).resolve()
            if ROOT.resolve() not in target.parents:
                raise ValueError('Invalid embedded resource path')
            try:
                if target.read_bytes() == expected:
                    continue
            except FileNotFoundError:
                pass
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.restore-', dir=target.parent)
            try:
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(expected)
                try:
                    os.replace(temporary, target)
                except PermissionError:
                    # Windows may deny replacement while another loader reads
                    # a file that a concurrent factory has already restored.
                    if target.read_bytes() != expected:
                        raise
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)


_ensure_core_resources()
if _EMBEDDED_CORE:
    # Warm workers can retain diagnostic_agent from an older package. Relative
    # imports in this private package cannot bind to that old module tree.
    _CORE_PACKAGE = '_isys_diagnostic_' + _CORE_DIGEST
    if _CORE_PACKAGE not in sys.modules:
        package_dir = ROOT / 'adk-project' / 'agents' / 'diagnostic_agent'
        package_spec = importlib.util.spec_from_file_location(_CORE_PACKAGE, package_dir / '__init__.py',
            submodule_search_locations=[str(package_dir)])
        package = importlib.util.module_from_spec(package_spec)
        sys.modules[_CORE_PACKAGE] = package
        package_spec.loader.exec_module(package)
else:
    _CORE_PACKAGE = 'diagnostic_agent'
    sys.path.insert(0, str(ROOT / 'adk-project' / 'agents'))

_CORE_EXPORTS = {
    'backend_client': ('DiagnosticBackendClient', 'BackendConfigurationError', 'BackendRequestError'),
    'integrated': ('investigate_ticket', 'submit_answer_and_continue', 'confirm_resolution_and_close',
        'submit_correction_for_review', 'continue_guided_resolution'),
    'engine': ('submit_answer', 'record_correction_for_review'),
    'llm': ('redact_secrets',), 'session_store': ('_state_from_dict', '_state_to_dict'),
    'standalone': ('run_ticket', '_public_result'),
    'conversation': ('RECEIPT', 'load_checkpoint', 'save_checkpoint', 'render_reply', 'latest_checkpoint'),
    'contract': ('build_contract',),
}
for _module_name, _names in _CORE_EXPORTS.items():
    _module = importlib.import_module(_CORE_PACKAGE + '.' + _module_name)
    globals().update({name: getattr(_module, name) for name in _names})
# Keep CLI verification imports compatible only in a fresh process. Never
# replace another version's canonical aliases in an existing worker.
if _EMBEDDED_CORE and 'diagnostic_agent' not in sys.modules:
    for _name, _module in list(sys.modules.items()):
        if _name == _CORE_PACKAGE or _name.startswith(_CORE_PACKAGE + '.'):
            sys.modules['diagnostic_agent' + _name[len(_CORE_PACKAGE):]] = _module


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    request: dict
    session: dict
    result: dict
    operation: str
    previous_result: dict
    diagnostic_result: dict


def sanitize(value, key=''):
    if (isinstance(value, str) and
            (key == 'integration_error' and value in {'DIAGNOSTIC_RESUME_BLOCKED', 'DIAGNOSTIC_ANSWER_STAGE_MISMATCH'}
             or key == 'kind' and value == 'ACCOUNT_VERIFICATION_UNAVAILABLE')):
        return value
    if key.endswith(('_id', '_ids')) or key in {'event_type', 'diagnosis_code', 'diagnosis_id', 'remaining_candidates', 'source', 'tool', 'status', 'recommended_action', 'framework'}:
        return value
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {k: sanitize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


class MessageSessionStore:
    """One request's state, restored from platform-owned assistant history."""
    def __init__(self, session):
        self.session = session

    def load(self, ticket_id):
        snapshot = self.session.get('snapshot')
        if snapshot and snapshot['ticket']['ticket_id'] == ticket_id:
            return _state_from_dict(snapshot)
        return None

    def save(self, state):
        self.session['snapshot'] = sanitize(_state_to_dict(state))


def _content(message):
    content = message.content
    if isinstance(content, list):
        return '\n'.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
    return str(content)


def diagnostic_payload(message):
    """Read current message metadata or a legacy structured assistant reply."""
    payload = message.additional_kwargs.get('isys_diagnostic')
    if isinstance(payload, dict):
        return payload
    try:
        payload = json.loads(_content(message))
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def backend_key(factory_config: RunnableConfig, runtime_config: RunnableConfig):
    """Accept the named connection at factory creation or per-invocation injection."""
    for candidate in (runtime_config, factory_config):
        credentials = candidate.get('configurable', {}).get('credentials', {})
        key = credentials.get('isys_it_backend_api_key') or credentials.get('workstream_c_api_key')
        if isinstance(key, dict):
            key = key.get('api_key')
        if isinstance(key, str) and key.strip():
            return key.strip()
    return os.getenv('DIAGNOSTIC_BACKEND_API_KEY')


def restore_continuation(client, ticket_id, reference=None, retained=None):
    """Recover one authoritative pending checkpoint; never choose by random ID order."""
    if reference is not None and (not isinstance(reference, str)
            or not re.fullmatch(r'CHK-[a-f0-9]{16}', reference)):
        raise ValueError('Invalid checkpoint reference. Use the actual returned Ticket/Ref receipt.')
    record = client.get_ticket_details(ticket_id)
    if record.get('status') in {'RESOLVED', 'CLOSED'}:
        return None
    latest_id = (record.get('latest_diagnostic_result') or {}).get('diagnostic_result_id')
    if not latest_id:
        raise ValueError('No saved diagnostic question exists. Investigate this ticket before answering.')
    prefixes = ('[DiagnosticAgent] User answered the outstanding diagnostic question.',
                '[DiagnosticAgent] User answered the guided resolution question.')
    recorded_ids = {eid for log in record.get('worklogs', [])
                    if str(log.get('summary', '')).startswith(prefixes)
                    for eid in log.get('evidence_ids', [])}

    def valid(document):
        session = document.get('session', {})
        snapshot = session.get('snapshot', {})
        saved_ids = {item.get('evidence_id') for item in snapshot.get('evidence', [])
                     if isinstance(item, dict)}
        return (session.get('mode') == 'backend' and session.get('ticket_id') == ticket_id
                and snapshot.get('ticket', {}).get('ticket_id') == ticket_id
                and document.get('result', {}).get('diagnostic_result_id') == latest_id
                and recorded_ids.issubset(saved_ids))

    if reference:
        try:
            document = load_checkpoint(client, ticket_id, reference, record=record)
        except BackendRequestError:
            raise ValueError('The saved checkpoint is missing, incomplete, corrupt, or belongs to another ticket. An operator must inspect it.') from None
        if not valid(document):
            raise ValueError('The answer checkpoint is stale or does not match this ticket. Do not replay the answer.')
        return document
    if retained and valid(retained):
        return retained
    if retained:
        # A stale retained question must not silently become a different question.
        raise ValueError('Retained diagnostic context is stale. Recover the current question before answering.')
    references = set()
    for log in record.get('worklogs', []):
        if log.get('entry_type') != 'NOTE' or not str(log.get('summary', '')).startswith('[DiagnosticAgent] Conversation checkpoint '):
            continue
        try:
            part = json.loads(log.get('rationale', ''))
        except (ValueError, TypeError):
            continue
        if (isinstance(part, dict) and part.get('kind') == 'ISYS_CONVERSATION_CHECKPOINT_V1'
                and part.get('part') == 0
                and re.fullmatch(r'CHK-[a-f0-9]{16}', str(part.get('reference', '')))):
            references.add(part['reference'])
    if len(references) > 128:
        raise ValueError('Too many saved checkpoints for automatic recovery; an operator must inspect the current context.')
    candidates = []
    for ref in sorted(references):
        try:
            document = load_checkpoint(client, ticket_id, ref, record=record)
        except BackendRequestError:
            continue
        if valid(document):
            candidates.append(document)
    if not candidates:
        raise ValueError('No complete current checkpoint is available. Recover the pending question before answering.')
    # Timestamps may be frozen. Random CHK identifiers do not encode chronology.
    signatures = {json.dumps({'snapshot': d['session']['snapshot'], 'result': d['result']},
                            sort_keys=True, ensure_ascii=False) for d in candidates}
    if len(signatures) != 1:
        raise ValueError('Multiple different pending checkpoints match. Supply the actual latest checkpoint_ref; do not guess.')
    return candidates[0]


def create_agent(config: RunnableConfig) -> StateGraph:
    """IBM entrypoint; credentials are injected via configurable.credentials."""
    _ensure_core_resources()
    factory_config = config
    settings = config.get('configurable', {})
    base_url = settings.get('backend_url') or os.getenv('DIAGNOSTIC_BACKEND_BASE_URL') or 'https://shelf-roman-swimmable.ngrok-free.dev'
    mode = settings.get('mode', 'backend')
    if mode not in {'local', 'backend'}:
        raise ValueError('mode must be local or backend')
    articles = ROOT / 'adk-project' / 'knowledge' / 'reviewed' / 'diagnostic_articles.json'
    knowledge = {'articles_path': articles}

    def read_request(state, config: RunnableConfig):
        _ensure_core_resources()
        messages = state.get('messages', [])
        session = {'mode': mode}
        previous_result = {}
        humans = [m for m in messages if m.type == 'human']
        text = _content(humans[-1]).strip() if humans else ''
        target = None
        try:
            probe = json.loads(text)
            if isinstance(probe, dict):
                target = probe.get('ticket_id')
        except ValueError:
            match = re.search(r'\b(?:TST|INC|SR|TEST|DEMO)-[A-Za-z0-9_-]+\b', text, re.I)
            target = match.group(0) if match else None
        for message in reversed(messages):
            if message.type != 'ai':
                continue
            recorded = diagnostic_payload(message)
            prior = recorded.get('diagnostic_session', {})
            receipt = RECEIPT.search(_content(message))
            if target and ((prior.get('ticket_id') and prior['ticket_id'] != target)
                           or (not prior and receipt and receipt.group(1) != target)):
                continue
            if not prior and receipt and mode == 'backend':
                try:
                    document = load_checkpoint(DiagnosticBackendClient(base_url=base_url,
                        api_key=backend_key(factory_config, config)), *receipt.groups())
                    prior, recorded = document['session'], document['result']
                except (BackendConfigurationError, BackendRequestError) as exc:
                    # An explicit ticket request can recover by reading backend records.
                    if not re.search(r'\b(?:TST|INC|SR|TEST|DEMO)-[A-Za-z0-9_-]+\b', text, re.I):
                        return {'request': {}, 'session': session, 'previous_result': {},
                            'operation': 'restore_error', 'result': {'error': str(exc),
                                'checkpoint_error': True, 'completed_actions': []}}
                    break
            if prior.get('mode') == mode:
                session = dict(prior)
                previous_result = {k: v for k, v in recorded.items() if k != 'diagnostic_session'}
                break
        if not humans:
            return {'request': {}, 'session': session, 'operation': 'help'}
        if re.search(r'[\u0600-\u06ff]', text):
            session['reply_language'] = 'ar'
        try:
            request = sanitize(json.loads(text))
            if not isinstance(request, dict):
                request = {}
        except ValueError:
            match = re.search(r'\b(?:TST|INC|SR|TEST|DEMO)-[A-Za-z0-9_-]+\b', text, re.I)
            if match:
                request = {'ticket_id': match.group(0), 'operation': 'investigate'}
            elif session.get('ticket_id'):
                request = {'ticket_id': session['ticket_id'], 'operation': 'answer', 'answer': redact_secrets(text)}
            else:
                request = {}
        request.setdefault('ticket_id', session.get('ticket_id'))
        request.setdefault('operation', 'investigate')
        retained_handoff = (request['operation'] == 'answer'
            and request.get('ticket_id') == session.get('ticket_id')
            and (session.get('snapshot', {}).get('status') == 'escalated'
                 or (previous_result.get('recommended_action') in {'ROUTE', 'ESCALATE'}
                     and not previous_result.get('next_question'))))
        if (mode == 'backend' and not retained_handoff and request['operation'] in
                {'answer', 'resolution_answer', 'record_correction', 'confirm_resolution'}
                and isinstance(request.get('ticket_id'), str)
                and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request['ticket_id'])):
            tid = request['ticket_id']
            try:
                retained = ({'session': session, 'result': previous_result}
                            if session.get('snapshot', {}).get('ticket', {}).get('ticket_id') == tid else None)
                reference = request.get('checkpoint_ref')
                document = restore_continuation(DiagnosticBackendClient(base_url=base_url,
                    api_key=backend_key(factory_config, config)), tid, reference, retained)
                if document is None:
                    return {'request': request, 'session': {'mode': mode, 'ticket_id': tid},
                        'previous_result': {}, 'operation': 'restore_error',
                        'result': {'ticket_id': tid, 'outcome': 'ALREADY_CLOSED',
                            'completed_actions': [], 'next_question': None}}
                session = dict(document['session'])
                previous_result = {k: v for k, v in document['result'].items() if k != 'diagnostic_session'}
                progress = session.get('snapshot', {}).get('ticket', {}).get('metadata', {}).get('resolution_progress', {})
                # A Supervisor must not convert a diagnostic yes/no question into
                # a fabricated procedure, then send Done against that old question.
                if (request['operation'] == 'answer' and str(request.get('answer', '')).strip().lower().strip(' .!')
                        in {'done', 'completed', 'i completed it', 'تم'}
                        and progress.get('stage') not in {'WAIT_STEP', 'WAIT_SUCCESS'}):
                    return {'request': request, 'session': session, 'previous_result': previous_result,
                        'operation': 'restore_error', 'result': {'ticket_id': tid,
                            'outcome': 'INCONCLUSIVE', 'recommended_action': 'ASK_MORE',
                            'completed_actions': [], 'integration_error': 'DIAGNOSTIC_ANSWER_STAGE_MISMATCH',
                            'error': 'No guided procedure is pending at this checkpoint. The completion answer was not processed.',
                            'next_question': session.get('snapshot', {}).get('next_question')}}
            except (BackendConfigurationError, BackendRequestError, ValueError, TypeError, KeyError) as exc:
                result = {'ticket_id': tid, 'outcome': 'INCONCLUSIVE',
                    'recommended_action': 'ASK_MORE', 'completed_actions': [],
                    'integration_error': 'DIAGNOSTIC_RESUME_BLOCKED',
                    'error': redact_secrets(str(exc)),
                    'next_question': 'An operator must inspect the saved diagnostic context; do not blindly resend this answer.'}
                if isinstance(exc, BackendRequestError):
                    result['backend_status'] = exc.status
                return {'request': request, 'session': session, 'previous_result': previous_result,
                    'operation': 'restore_error', 'result': result}
        operation = request['operation']
        progress = session.get('snapshot', {}).get('ticket', {}).get('metadata', {}).get('resolution_progress', {})
        if operation not in {'investigate', 'answer', 'confirm_resolution', 'record_correction', 'resolution_answer'} or not request.get('ticket_id'):
            operation = 'help'
        elif (operation == 'answer' and progress.get('stage') in {'WAIT_STEP', 'WAIT_SUCCESS'}
              and not session.get('snapshot', {}).get('ticket', {}).get('metadata', {}).get('pending_correction_review')):
            operation = 'record_correction' if re.search(r'\b(?:correction|actually|i was wrong)\b', request.get('answer', ''), re.I) else 'resolution_answer'
        elif (operation == 'answer' and request.get('ticket_id') == session.get('ticket_id')
              and (session.get('snapshot', {}).get('status') == 'escalated'
                   or (previous_result.get('recommended_action') in {'ROUTE', 'ESCALATE'}
                       and not previous_result.get('next_question')))):
            correction = re.search(r'\b(?:correction|actually|i was wrong|previous answer was wrong|still not working|still fails)\b|\bnow\b.*\b(?:cannot|can\x27t|affected|fail)\b',
                str(request.get('answer', '')), re.I)
            operation = 'record_correction' if correction else 'handoff_status'
        return {'request': request, 'session': session, 'operation': operation,
                'previous_result': previous_result, 'result': {}}

    def act(state, config: RunnableConfig):
        _ensure_core_resources()
        request = state['request']
        session = dict(state['session'])
        tid = str(request['ticket_id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', tid):
            return {'result': {'recommended_action': 'ASK_MORE', 'error': 'Invalid ticket ID.'}}
        store = MessageSessionStore(session)
        try:
            operation = state['operation']
            if mode == 'backend':
                key = backend_key(factory_config, config)
                if not key:
                    raise BackendConfigurationError(
                        'WXO connection missing: select a team connection with app ID isys_it_backend '
                        'and credential type api_key. Expected injected credential: isys_it_backend_api_key. '
                        'Use the backend service key; do not paste it into chat.')
                client = DiagnosticBackendClient(base_url=base_url, api_key=key)
                if operation == 'investigate':
                    if store.load(tid) is None:
                        restored = latest_checkpoint(client, tid)
                        if restored:
                            session.update(restored['session'])
                    result = investigate_ticket(client, tid, store=store, diagnostic_review_mode=True, **knowledge)
                elif operation == 'answer':
                    answer = request.get('answer')
                    if not isinstance(answer, str) or not answer.strip():
                        raise ValueError('Provide a nonempty answer to the outstanding question.')
                    result = submit_answer_and_continue(client, tid, answer,
                        request.get('evidence_id') or 'answer-' + uuid.uuid4().hex, store, diagnostic_review_mode=True, **knowledge)
                elif operation == 'record_correction':
                    result = submit_correction_for_review(client, tid, request.get('answer'),
                        request.get('evidence_id') or 'correction-' + uuid.uuid4().hex, store)
                elif operation == 'resolution_answer':
                    result = continue_guided_resolution(client, tid, request.get('answer', ''),
                        request.get('evidence_id') or 'resolution-answer-' + uuid.uuid4().hex, store, **knowledge)
                else:
                    # Never infer affirmative confirmation or completed steps from conversational text.
                    if not isinstance(request.get('confirmed_by_user'), bool):
                        raise ValueError('Explicit confirmed_by_user boolean and completed_step_ids are required.')
                    steps = request.get('completed_step_ids', [])
                    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
                        raise ValueError('completed_step_ids must be a list of exact step IDs.')
                    result = confirm_resolution_and_close(client, tid, request['confirmed_by_user'], steps, store, **knowledge)
            elif operation == 'investigate':
                ticket = request.get('ticket')
                if not ticket:
                    existing = store.load(tid)
                    if existing is None:
                        raise ValueError('Local mode needs a synthetic ticket object for the first turn.')
                    ticket = _state_to_dict(existing)['ticket']
                if ticket.get('ticket_id') != tid:
                    raise ValueError('ticket_id must match the supplied local ticket.')
                ticket = dict(ticket)
                ticket['metadata'] = {**ticket.get('metadata', {}), 'diagnostic_review_mode': True}
                result = run_ticket(ticket, store=store, **knowledge)
            elif operation == 'answer':
                current = store.load(tid)
                if current is None:
                    raise ValueError('No active investigation for this ticket in this conversation.')
                answer = request.get('answer')
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError('Provide a nonempty answer.')
                submit_answer(current, redact_secrets(answer), request.get('evidence_id') or 'answer-' + uuid.uuid4().hex)
                store.save(current)
                result = _public_result(current)
            elif operation == 'record_correction':
                current = store.load(tid)
                if current is None:
                    raise ValueError('No saved investigation for this correction.')
                answer = request.get('answer')
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError('Provide a nonempty correction.')
                record_correction_for_review(current, redact_secrets(answer),
                    request.get('evidence_id') or 'correction-' + uuid.uuid4().hex)
                store.save(current)
                result = _public_result(current)
            else:
                raise ValueError('Local mode cannot resolve backend tickets.')
            session['ticket_id'] = tid
            return {'session': session, 'result': sanitize(result)}
        except (BackendConfigurationError, BackendRequestError, ValueError, TypeError) as exc:
            result = {'ticket_id': tid, 'outcome': 'INCONCLUSIVE', 'diagnosis_code': None,
                      'recommended_action': 'ASK_MORE', 'completed_actions': [],
                      'error': redact_secrets(str(exc)), 'next_question': 'Supply the missing configuration or evidence, then retry the request.'}
            if isinstance(exc, BackendRequestError):
                result['backend_status'] = exc.status
            if isinstance(exc, BackendConfigurationError):
                result['missing_configuration'] = {
                    'connection_app_id': 'isys_it_backend', 'credential_type': 'api_key',
                    'credential_scope': 'team', 'expected_credential_name': 'isys_it_backend_api_key'}
                result['next_question'] = 'An operator must bind the isys_it_backend connection to this imported agent. Do not send the key in chat.'
            return {'session': session, 'result': result}

    def help_node(state):
        return {'result': {'outcome': 'INCONCLUSIVE', 'diagnosis_code': None,
            'recommended_action': 'ASK_MORE', 'completed_actions': [],
            'next_question': 'What is the synthetic ticket ID? / ما رقم التذكرة؟',
            'missing_information': ['ticket_id']}}

    def handoff_status(state):
        # Acknowledgements after handoff do not constitute diagnostic answers.
        # Reuse the recorded recommendation without making backend mutations.
        tid = state['session'].get('ticket_id')
        recorded = dict(state.get('previous_result', {}))
        if recorded.get('ticket_id') == tid:
            recorded.update(next_question=None, completed_actions=[], handoff_status='AWAITING_SUPERVISOR',
                message='The recorded investigation requires Supervisor or human review. No additional diagnostic answer is pending.')
            return {'result': recorded}
        return {'result': {'ticket_id': tid, 'recommended_action': 'ESCALATE',
            'outcome': 'HUMAN_REQUIRED', 'next_question': None, 'completed_actions': [],
            'handoff_status': 'AWAITING_SUPERVISOR'}}

    def respond(state, config: RunnableConfig):
        payload = sanitize(dict(state['result']))
        session = sanitize(dict(state.get('session', {'mode': mode})))
        if (mode == 'backend' and session.get('snapshot') and not payload.get('error')
                and state.get('operation') not in {'handoff_status', 'help'}
                and payload.get('status') not in {'RESOLVED', 'CLOSED'}
                and payload.get('outcome') not in {'RESOLVED', 'ALREADY_CLOSED'}):
            try:
                client = DiagnosticBackendClient(base_url=base_url, api_key=backend_key(factory_config, config))
                session['checkpoint_ref'] = save_checkpoint(client, session['ticket_id'], session, payload)
            except (BackendConfigurationError, BackendRequestError) as exc:
                session.pop('checkpoint_ref', None)
                payload['checkpoint_error'] = redact_secrets(str(exc))
        language = session.get('reply_language') or session.get('snapshot', {}).get('ticket', {}).get('language', 'en')
        session['reply_language'] = language
        payload['diagnostic_session'] = session
        payload['framework'] = 'langgraph'
        contract = build_contract(payload, session)
        payload['diagnostic_result'] = contract
        visible = (json.dumps(payload, ensure_ascii=False) if settings.get('response_format') == 'structured'
                   else render_reply(payload, session, language))
        if (payload.get('integration_error') == 'DIAGNOSTIC_RESUME_BLOCKED'
                and settings.get('response_format') != 'structured'):
            # Surface a bounded, redacted integration error instead of blaming a valid ID.
            visible = ('Diagnostic continuation is blocked: ' + payload['error']
                + '\nNo answer was processed by this invocation. An operator must inspect the checkpoint/session.'
                + '\nTicket: ' + str(payload.get('ticket_id', '')))
        if (payload.get('integration_error') == 'DIAGNOSTIC_ANSWER_STAGE_MISMATCH'
                and settings.get('response_format') != 'structured'):
            visible = (payload['error'] + '\nThe actual pending question is: '
                + str(payload.get('next_question') or 'unavailable; an operator must inspect the context.'))
            if session.get('checkpoint_ref'):
                visible += '\n\nTicket: ' + str(payload['ticket_id']) + ' · Ref: ' + session['checkpoint_ref']
        return {'session': session, 'diagnostic_result': contract, 'messages': [AIMessage(content=visible,
            additional_kwargs={'isys_diagnostic': payload})]}

    workflow = StateGraph(AgentState)
    workflow.add_node('read_request', read_request)
    workflow.add_node('investigate', act)
    workflow.add_node('record_answer', act)
    workflow.add_node('record_correction', act)
    workflow.add_node('resolution_answer', act)
    workflow.add_node('confirm_resolution', act)
    workflow.add_node('request_ticket', help_node)
    workflow.add_node('handoff_status', handoff_status)
    workflow.add_node('respond', respond)
    workflow.add_edge(START, 'read_request')
    workflow.add_conditional_edges('read_request', lambda s: s['operation'], {
        'investigate': 'investigate', 'answer': 'record_answer',
        'confirm_resolution': 'confirm_resolution', 'help': 'request_ticket',
        'record_correction': 'record_correction',
        'resolution_answer': 'resolution_answer',
        'handoff_status': 'handoff_status', 'restore_error': 'respond'})
    for node in ('investigate', 'record_answer', 'record_correction', 'resolution_answer', 'confirm_resolution', 'request_ticket', 'handoff_status'):
        workflow.add_edge(node, 'respond')
    workflow.add_edge('respond', END)
    return workflow
