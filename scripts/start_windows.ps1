$ErrorActionPreference = 'Stop'
$distribution = Split-Path -Parent $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $distribution 'FashionAILocalizer.exe')) {
    & (Join-Path $distribution 'FashionAILocalizer.exe') @args
} elseif (Test-Path -LiteralPath (Join-Path $distribution '.venv\Scripts\python.exe')) {
    & (Join-Path $distribution '.venv\Scripts\python.exe') -m app.desktop.launcher @args
} else {
    Write-Error 'Open the complete Windows distribution folder and run FashionAILocalizer.exe. Developers: create .venv with requirements-m4.txt.'
}
exit $LASTEXITCODE
