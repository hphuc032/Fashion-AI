$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start_windows.ps1') --check @args
exit $LASTEXITCODE
