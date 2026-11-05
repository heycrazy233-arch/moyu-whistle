$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    $Launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Python = $Launcher.Source
        & $Python -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        & $Python -3 start.py --doctor
    } else {
        $Command = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Command) {
            throw 'Python not found. Install Python 3.11 or newer.'
        }
        $Python = $Command.Source
        & $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
        & $Python start.py --doctor
    }
} else {
    & $Python start.py --doctor
}
if ($LASTEXITCODE -ne 0) { throw 'Shared diagnostics failed.' }

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Write-Warning 'OpenSSH Client is missing; local monitoring works, SSH sources do not.'
}
if (-not (Test-Path (Join-Path $env:USERPROFILE '.codex'))) {
    Write-Warning 'CODEX_HOME was not found at the default location.'
}
Write-Host 'Windows diagnostics complete. This does not replace real agent/UI validation.'
