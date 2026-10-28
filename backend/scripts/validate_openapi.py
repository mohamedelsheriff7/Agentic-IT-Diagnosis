import json
import yaml
from openapi_spec_validator import validate
from app.config import ROOT
from scripts.export_openapi import public_url


def main():
    a = json.loads((ROOT / 'specs/agent.openapi.json').read_text(encoding='utf-8'))
    b = yaml.safe_load((ROOT / 'specs/agent.openapi.yaml').read_text(encoding='utf-8'))
    assert a == b
    validate(a)
    assert a['openapi'] == '3.0.3' and len(a['servers']) == 1
    public_url(a['servers'][0]['url'])
    assert not any(p.startswith('/admin') or p == '/health' for p in a['paths'])
    print('Both exports valid and equivalent')


if __name__ == '__main__':
    main()
