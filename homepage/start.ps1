param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskHomepage = $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $taskHomepage 'payload\manifest.json')) {
    $taskBootstrapPython = Join-Path $taskHomepage 'bootstrap-python\python.exe'
    & $taskBootstrapPython (Join-Path $taskHomepage 'bootstrap.py')
    if ($LASTEXITCODE -ne 0) { throw 'Application restore failed. See the message above.' }
    & (Join-Path $taskHomepage '실행묶음\start.ps1') -NoBrowser:$NoBrowser
    exit $LASTEXITCODE
}
$taskProject = Split-Path $taskHomepage -Parent
$taskRepo = if (Test-Path -LiteralPath (Join-Path $taskProject 'V4\active_runtime.json')) { $taskProject } else { Join-Path $taskProject 'r_scam_prototype' }
$taskPython = if (Test-Path -LiteralPath (Join-Path $taskHomepage 'python\python.exe')) { Join-Path $taskHomepage 'python\python.exe' } else { Join-Path $taskRepo '.venv\Scripts\python.exe' }
$taskRuntime = Join-Path $taskHomepage 'runtime'
$taskInfoPath = Join-Path $taskRuntime 'server.json'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
if (Test-Path -LiteralPath $taskInfoPath) {
    try {
        $taskInfo = Get-Content -LiteralPath $taskInfoPath -Raw | ConvertFrom-Json
        $taskStatus = Invoke-RestMethod ($taskInfo.url + 'api/status') -TimeoutSec 2
        if ($taskStatus.app -eq 'maeum-check-final-v4') {
            if (-not $NoBrowser) { Start-Process $taskInfo.url }
            Write-Host ('Website: ' + $taskInfo.url)
            exit 0
        }
    } catch {}
}
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Model Python environment missing: .venv' }
$taskServer = Join-Path $taskHomepage 'server.py'
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @(('"' + $taskServer + '"'), '--preload') -WorkingDirectory $taskProject -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntime 'server.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'server.stderr.log') -PassThru
for ($taskTry = 0; $taskTry -lt 60; $taskTry++) {
    Start-Sleep -Milliseconds 500
    if ($taskProcess.HasExited) { throw 'Server stopped. See homepage/runtime/server.stderr.log.' }
    if (Test-Path -LiteralPath $taskInfoPath) {
        try {
            $taskInfo = Get-Content -LiteralPath $taskInfoPath -Raw | ConvertFrom-Json
            if ($taskInfo.pid -eq $taskProcess.Id) {
                $taskStatus = Invoke-RestMethod ($taskInfo.url + 'api/status') -TimeoutSec 2
                if ($taskStatus.app -eq 'maeum-check-final-v4') {
                    if (-not $NoBrowser) { Start-Process $taskInfo.url }
                    Write-Host ('Website: ' + $taskInfo.url)
                    exit 0
                }
            }
        } catch {}
    }
}
throw 'Server startup timed out. See homepage/runtime/server.stderr.log.'
