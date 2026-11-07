param(
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-web\Scripts\python.exe'),
    [string]$Profile,
    [switch]$NoBrowser,
    [ValidateRange(1,120)][int]$Timeout = 45
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Install the isolated Python 3.11 Web environment first. Startup never installs dependencies.'
}
$runtimeArgs = @((Join-Path $PSScriptRoot 'web_runtime.py'), 'start', '--timeout', [string]$Timeout)
if ($Profile) { $runtimeArgs += @('--profile', $Profile) }
if ($NoBrowser) { $runtimeArgs += '--no-browser' }
& $PythonPath @runtimeArgs
exit $LASTEXITCODE
