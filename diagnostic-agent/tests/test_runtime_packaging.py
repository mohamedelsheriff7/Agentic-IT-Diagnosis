"""The native factory must survive warm-worker imports and host temp cleanup."""
import json
from pathlib import Path
import subprocess
import sys


def test_built_runtime_recovers_resources_without_cross_version_module_reuse():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, 'scripts/verify_v68_runtime.py'], cwd=root,
        capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report['v67_exact_error_reproduced']
    assert report['warm_version_isolation'] and report['garbage_collection_safe']
    assert report['cleanup_and_repeat_cycles_passed'] == 5
    assert report['corrupt_resource_restored'] and report['concurrent_factories_passed'] == 8
