"""Export OpenAPI 3.0.3 with actual JSON Schema conversion and validation."""
import copy
import ipaddress
import json
from urllib.parse import urlparse
import yaml
from openapi_spec_validator import validate
from app.config import ROOT, Settings
from app.main import create_app


def public_url(value):
    p = urlparse(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or '{' in value or '}' in value:
        raise ValueError('PUBLIC_BASE_URL must be one non-parameterized HTTPS base URL without credentials/query/fragment')
    host = p.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')) or '.' not in host:
        raise ValueError('Local servers cannot be exported')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError('Private/loopback addresses cannot be exported')
    return value.rstrip('/')


def convert(value):
    if isinstance(value, list):
        return [convert(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: convert(v) for k, v in value.items() if k not in ('$schema', 'jsonSchemaDialect')}
    if 'const' in result:
        result['enum'] = [result.pop('const')]
    if isinstance(result.get('examples'), list):
        examples = result.pop('examples')
        if examples:
            result['example'] = examples[0]
    if 'anyOf' in result:
        choices = result['anyOf']
        non_null = [v for v in choices if v.get('type') != 'null']
        if len(non_null) != len(choices):
            if len(non_null) != 1:
                raise ValueError('Unsupported nullable union')
            result.pop('anyOf')
            inner = non_null[0]
            if '$ref' in inner:
                result['allOf'] = [inner]
            else:
                result.update(inner)
            result['nullable'] = True
    for keyword, bound in (('exclusiveMinimum', 'minimum'), ('exclusiveMaximum', 'maximum')):
        if type(result.get(keyword)) in (int, float):
            result[bound] = result[keyword]
            result[keyword] = True
    for keyword in ('$defs', 'unevaluatedProperties', 'prefixItems', 'dependentSchemas', 'patternProperties'):
        if keyword in result:
            raise ValueError('Unsupported schema construct: ' + keyword)
    return result


def export_specs(app, base_url):
    full = copy.deepcopy(app.openapi())
    agent = copy.deepcopy(full)
    agent['paths'] = {path: {method: op for method, op in item.items() if 'agent-tools' in op.get('tags', [])} for path, item in agent['paths'].items()}
    agent['paths'] = {p: v for p, v in agent['paths'].items() if v}
    agent['servers'] = [{'url': public_url(base_url)}]
    agent['components']['securitySchemes'] = {'ServiceApiKey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'}}
    agent['security'] = [{'ServiceApiKey': []}]
    names = set()

    def collect(value):
        if isinstance(value, dict):
            if '$ref' in value:
                names.add(value['$ref'].split('/')[-1])
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    collect(agent['paths'])
    previous = set()
    while previous != names:
        previous = set(names)
        for name in previous:
            collect(agent['components']['schemas'][name])
    agent['components']['schemas'] = {k: v for k, v in agent['components']['schemas'].items() if k in names}
    for schema in agent['components']['schemas'].values():
        for name, field in schema.get('properties', {}).items():
            field.setdefault('description', name.replace('_', ' ').capitalize() + '. See operation description and integration contract for policy semantics.')
    agent = convert(agent)
    agent['openapi'] = '3.0.3'
    validate(agent)
    ids = [op['operationId'] for item in agent['paths'].values() for op in item.values()]
    assert len(ids) == len(set(ids)) == 17
    return full, agent


def main():
    settings = Settings.from_env()
    app = create_app(Settings(database_url='sqlite:///:memory:'))
    full, agent = export_specs(app, settings.public_base_url)
    dest = ROOT / 'specs'
    dest.mkdir(exist_ok=True)
    for name, value in [('developer.openapi.json', full), ('agent.openapi.json', agent)]:
        (dest / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (dest / 'agent.openapi.yaml').write_text(yaml.safe_dump(agent, allow_unicode=True, sort_keys=False), encoding='utf-8')
    connection = {'spec_version': 'v1', 'kind': 'connection', 'app_id': 'workstream_c', 'environments': {env: {'kind': 'api_key', 'type': 'team', 'server_url': agent['servers'][0]['url'], 'name': 'X-API-Key'} for env in ('draft', 'live')}}
    (dest / 'connection.yaml').write_text(yaml.safe_dump(connection, sort_keys=False), encoding='utf-8')
    print('Validated OpenAPI 3.0.3: 17 tools, one HTTPS server, API-key security; exported JSON/YAML and connection config.')


if __name__ == '__main__':
    main()
