param([switch]$Stop)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$runtimeRoot=Join-Path $projectRoot '.runtime'
$recordPath=Join-Path $runtimeRoot 'tunnel-process.json'
$bridgePath=Join-Path $PSScriptRoot 'pilot.py'
if(Test-Path -LiteralPath $recordPath){
 $record=Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
 $active=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
 if($active){
  $info=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
  $owned=$info.CommandLine.Contains($bridgePath) -and $active.StartTime.ToUniversalTime().ToString('o') -eq $record.started
  if(-not $owned){throw 'El PID guardado pertenece a otro proceso; no se modificará.'}
  if($Stop){Stop-Process -Id $record.pid;Write-Output 'Túneles de PELUQO cerrados.';exit}
  Write-Output 'http://localhost:3000/expedicion';exit
 }
}
if($Stop){Write-Output 'PELUQO no tiene un túnel activo.';exit}
foreach($portNumber in @(3000,54321)){
 if(Get-NetTCPConnection -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue){throw "El puerto $portNumber está ocupado. Cierra la terminal anterior del túnel antes de abrir este acceso."}
}
$pythonPath=(Get-Command python.exe).Source
$forward=Start-Process -FilePath $pythonPath -ArgumentList @('"'+$bridgePath+'"','forward') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'tunnel.log') -RedirectStandardError (Join-Path $runtimeRoot 'tunnel-error.log') -PassThru
@{pid=$forward.Id;started=$forward.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
Write-Output 'http://localhost:3000/expedicion'
