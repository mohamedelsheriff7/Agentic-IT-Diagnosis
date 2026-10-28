"""Read-only backend credential/connectivity check; never prints credentials."""
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env')
sys.path.insert(0, str(root / 'adk-project' / 'agents'))
from diagnostic_agent.backend_client import DiagnosticBackendClient, BackendRequestError
try:
    ticket = DiagnosticBackendClient().get_ticket_details('TST-0001')
    print(json.dumps({'backend': 'reachable', 'authenticated': True,
        'ticket_id': ticket.get('ticket_id'), 'status': ticket.get('status')}))
except BackendRequestError as exc:
    print(json.dumps({'backend': 'error', 'http_status': exc.status, 'message': str(exc)}))
    raise SystemExit(1)
