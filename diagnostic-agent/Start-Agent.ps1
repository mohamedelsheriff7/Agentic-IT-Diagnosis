param([int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\serve.py" --port $Port
