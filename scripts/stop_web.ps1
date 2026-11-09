param(
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv-web\Scripts\python.exe'),
    [string]$Profile
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'The original isolated Web Python environment is required for ownership checks.'
}
$runtimeArgs = @((Join-Path $PSScriptRoot 'web_runtime.py'), 'stop')
if ($Profile) { $runtimeArgs += @('--profile', $Profile) }
& $PythonPath @runtimeArgs
exit $LASTEXITCODE
