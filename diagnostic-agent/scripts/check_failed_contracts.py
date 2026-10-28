import sys
from pathlib import Path
from dotenv import load_dotenv
root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env')
sys.path.insert(0, str(root / 'adk-project' / 'agents'))
from diagnostic_agent.backend_client import DiagnosticBackendClient, BackendRequestError
from diagnostic_agent.integrated import investigate_ticket
for tid in ('INC-614375aeb07a49a7','INC-7f7806c44a194c55','INC-9cb6c744d5e44bd8'):
    try:
        investigate_ticket(DiagnosticBackendClient(), tid, articles_path=root/'adk-project/knowledge/reviewed/diagnostic_articles.json')
    except BackendRequestError as exc:
        print(tid, exc.detail)
