$ErrorActionPreference = 'Stop'
$taskInfoPath = Join-Path $PSScriptRoot 'runtime\server.json'
if (-not (Test-Path -LiteralPath $taskInfoPath)) { Write-Host 'Server is not running.'; exit 0 }
$taskInfo = Get-Content -LiteralPath $taskInfoPath -Raw | ConvertFrom-Json
$taskProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$taskInfo.pid)
if ($null -eq $taskProcess) { Write-Host 'Server already stopped.'; exit 0 }
$taskServer = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'server.py'))
if (-not $taskProcess.CommandLine.Contains($taskServer)) { throw 'Process does not match this homepage. Nothing stopped.' }
Stop-Process -Id $taskProcess.ProcessId
Write-Host 'Homepage server stopped. GPU memory released.'
