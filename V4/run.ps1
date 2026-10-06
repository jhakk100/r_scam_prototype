param(
 [ValidateSet('infer','evaluate','original-evaluate','test','map')][string]$Mode='test',
 [string]$InputPath,
 [string]$PythonPath
)
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
if ($PythonPath) {
 $taskPython=$PythonPath
} elseif ($env:RSCAM_PYTHON) {
 $taskPython=$env:RSCAM_PYTHON
} elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe')) {
 $taskPython=Join-Path $PSScriptRoot '../.venv/Scripts/python.exe'
} else {
 $taskPython=(Get-Command python -ErrorAction Stop).Source
}
function Invoke-TaskPython([string[]]$TaskArguments) {
 & $taskPython @TaskArguments
 if($LASTEXITCODE -ne 0){throw "V4 $Mode failed (exit $LASTEXITCODE)"}
}
switch($Mode) {
 'test' { Invoke-TaskPython @('-B',(Join-Path $PSScriptRoot 'verify_release.py')) }
 'infer' {
  if(!$InputPath){throw '-InputPath is required'}
  Invoke-TaskPython @('-B','-u',(Join-Path $PSScriptRoot 'pipeline.py'),'--input',(Resolve-Path -LiteralPath $InputPath).Path)
 }
 'evaluate' {
  foreach($taskStage in @('prepare','original','specialized','finalize')) {
   Invoke-TaskPython @('-B','-u',(Join-Path $PSScriptRoot 'evaluate_d03_final.py'),'--stage',$taskStage)
  }
 }
 'original-evaluate' {
  foreach($taskStage in @('prepare','original','specialized','finalize')) {
   Invoke-TaskPython @('-B','-u',(Join-Path $PSScriptRoot 'evaluate_d03_final.py'),'--stage',$taskStage)
  }
 }
 'map' { Invoke-TaskPython @('-B','-u',(Join-Path $PSScriptRoot 'serve_map.py')) }
}
