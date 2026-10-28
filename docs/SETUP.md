# Configuration and datasets

Follow the root README from a fresh clone using Python 3.12. Install backend and diagnostic dependencies into separate virtual environments. Copy only `.env.example` templates; configure keys locally.

Backend: `API_KEY` is the service/tool key; `ADMIN_API_KEY` is a different administrative key. `ADMIN_COMMAND_KEY` authorizes explicit fixture import. Set `PUBLIC_BASE_URL` to the backend endpoint reachable from WXO, then run `python -m scripts.export_openapi` from backend/ to regenerate tool definitions and connection configuration. The checked-in endpoint is an example/previous snapshot, not a provisioned service.

Diagnostic HTTP host: set `DIAGNOSTIC_BACKEND_BASE_URL`, `DIAGNOSTIC_BACKEND_API_KEY`, and a separate `DIAGNOSTIC_SERVICE_API_KEY` in diagnostic-agent/.env. The provided template defaults to localhost. Native WXO uses its injected connection credential instead of this .env.

The native v6.8.3 bundle retains the backend URL default from the supplied working artifact. Before deployment to a different endpoint, update the default in diagnostic-agent/wxo_langgraph/agent.py, rebuild, verify, and import the rebuilt package. Do not assume an old tunnel remains available.

`backend/data/workstream_a` is the merged operational dataset. `evaluation/workstream_a` preserves original A submissions; normalized answers are in backend/evaluation/workstream_a. Do not load answer files into the runtime or knowledge base. `knowledge/backend_import` is review/upload material, not an instruction to replace the backend's operational fixtures or activate draft policy.

Component documentation includes historical version notes. The root README and assembly notes identify the assembled entry points. Reproduction of the original A dataset generator/evaluator remains a gap: only the supplied datasets and backend generator are available locally.
