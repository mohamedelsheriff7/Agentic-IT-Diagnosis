"""Use the packaged DOCX rasterizer with native Word PDF export on Windows."""
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
qa = root / 'docs/reports/.qa_patch_history'
qa.mkdir(parents=True, exist_ok=True)
(qa / 'tmp').mkdir(exist_ok=True)
tempfile.tempdir = str(qa / 'tmp')
runtime = Path(r'C:\Users\dadae\.cache\codex-runtimes\codex-primary-runtime\dependencies')
os.environ['PATH'] = str(runtime / 'native/poppler/Library/bin') + os.pathsep + os.environ['PATH']
renderer_path = Path(r'C:\Users\dadae\.codex\plugins\cache\openai-primary-runtime\documents\26.1024.11018\skills\documents\render_docx.py')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', renderer_path)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def word_pdf(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    pdf = Path(convert_tmp_dir) / (stem + '.pdf')
    command = f"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.AutomationSecurity = 3
$document = $null
try {{
  $document = $word.Documents.Open({ps_quote(doc_path)}, $false, $true)
  $document.Repaginate()
  $document.ExportAsFixedFormat({ps_quote(pdf)}, 17)
}} finally {{
  if ($null -ne $document) {{ $document.Close(0) }}
  $word.Quit()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}}
"""
    shell = runtime / 'native/powershell/pwsh.exe'
    if not shell.exists():
        shell = 'powershell.exe'
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', command],
        capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return str(pdf), 'Rendered with native Word PDF export.'


# The Windows runtime does not bundle LibreOffice. Use Word for the PDF stage;
# retain the packaged renderer and bundled Poppler for page PNGs and QA.
renderer.convert_to_pdf = word_pdf
pages = renderer.rasterize(str(root / 'docs/reports/ISYS_Diagnostic_Agent_Patch_History.docx'),
    str(qa), dpi=120, verbose=False, emit_pdf=True)
print(json.dumps({'pages': len(pages), 'images': list(pages)}))
