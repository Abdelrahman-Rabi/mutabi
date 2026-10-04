param(
    [int]$Port = 8765,
    [string]$Database = 'runtime/advanced-demo.db'
)

$ErrorActionPreference = 'Stop'
$mutabiPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $mutabiPython)) {
    $mutabiPython = (Get-Command python -ErrorAction Stop).Source
}
Push-Location $PSScriptRoot
try {
    Write-Host "Open http://127.0.0.1:$Port/ in your browser. Press Ctrl+C to stop."
    & $mutabiPython -m mutabi.web --db $Database --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Mutabi did not start. Review the output above.' }
}
finally {
    Pop-Location
}
