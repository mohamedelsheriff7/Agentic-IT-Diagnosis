"""Start a single local API worker; export OpenAPI before starting."""
import argparse
import json
import os
from pathlib import Path
import uvicorn
from server import app, ROOT

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--public-url', help='Actual reachable HTTPS agent URL for the OpenAPI servers field')
    args = parser.parse_args()
    if args.public_url:
        from urllib.parse import urlsplit
        url = urlsplit(args.public_url)
        if url.scheme != 'https' or not url.netloc or url.query or url.fragment:
            parser.error('--public-url must be an HTTPS base URL without query or fragment')
        app.servers = [{'url': args.public_url.rstrip('/')}]
    else:
        app.servers = [{'url': os.getenv('DIAGNOSTIC_PUBLIC_URL', f'http://{args.host}:{args.port}')}]
    if not args.export_only and not os.getenv('DIAGNOSTIC_SERVICE_API_KEY'):
        parser.error('Set DIAGNOSTIC_SERVICE_API_KEY in .env first (see .env.example).')
    app.openapi_version = '3.0.3'
    schema = app.openapi()
    # OpenAPI 3.0 uses nullable instead of the JSON Schema null type.
    def compatible(value):
        if isinstance(value, list):
            return [compatible(v) for v in value]
        if not isinstance(value, dict):
            return value
        value = {k: compatible(v) for k, v in value.items()}
        choices = value.get('anyOf', [])
        if any(c.get('type') == 'null' for c in choices):
            choices = [c for c in choices if c.get('type') != 'null']
            value.pop('anyOf')
            value.update(choices[0] if len(choices) == 1 else {'anyOf': choices})
            value['nullable'] = True
        return value
    schema = compatible(schema)
    app.openapi_schema = schema
    target = ROOT / 'diagnostic-agent.openapi.json'
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'OpenAPI exported to {target}', flush=True)
    if not args.export_only:
        uvicorn.run(app, host=args.host, port=args.port)
