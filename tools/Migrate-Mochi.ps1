param([string]$Port='COM3',[switch]$BackupOnly)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$backupRoot=Join-Path $projectRoot 'backups'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$stamp=[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$image=Join-Path $backupRoot "mochi-before-integral-$stamp.bin"
$manifestPath=Join-Path $backupRoot "mochi-before-integral-$stamp.json"
$installations=Get-Content -LiteralPath 'C:\Espressif\tools\eim_idf.json' -Raw | ConvertFrom-Json
$installation=$installations.idfInstalled | Where-Object name -eq 'v6.0.1' | Select-Object -First 1
& $installation.python -m esptool --chip esp32s3 --port $Port --baud 921600 read-flash 0 0x1000000 $image
if ($LASTEXITCODE -ne 0 -or (Get-Item -LiteralPath $image).Length -ne 16777216) { throw 'The full-flash backup did not complete; the board was not migrated.' }
$digest=(Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash
@{file=(Split-Path -Leaf $image);sha256=$digest;flash_bytes=16777216;port=$Port;created_utc=[DateTime]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output "Full-flash backup verified: $manifestPath"
if (-not $BackupOnly) {
    & "$PSScriptRoot\Invoke-Mochi.ps1" -Action BuildOTA -Port $Port
    if ($LASTEXITCODE -ne 0) { throw 'OTA build failed; board firmware is unchanged.' }
    & "$PSScriptRoot\Invoke-Mochi.ps1" -Action FlashOTA -Port $Port -BackupManifest $manifestPath
    if ($LASTEXITCODE -ne 0) { throw "Migration did not complete. Recovery image: $image" }
}
