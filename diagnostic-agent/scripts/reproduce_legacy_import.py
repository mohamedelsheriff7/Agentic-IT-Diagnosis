"""Reproduce the v1 packaging failure when WXO relocates only the entrypoint."""
from pathlib import Path
import tempfile
import subprocess
import sys
import zipfile
root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='legacy-import-', dir=root / 'dist') as directory:
    target = Path(directory) / 'agent.py'
    with zipfile.ZipFile(root / 'dist' / 'isys-diagnostic-langgraph.zip') as archive:
        target.write_bytes(archive.read('agent.py'))
    code = 'import runpy,sys; runpy.run_path(sys.argv[1])'
    result = subprocess.run([sys.executable, '-I', '-c', code, str(target)], cwd=directory,
        capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and "No module named 'diagnostic_agent'" in result.stderr
    print("Reproduced v1 failure: No module named 'diagnostic_agent' when only agent.py is relocated.")
