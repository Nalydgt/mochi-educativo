param(
    [Parameter(Mandatory=$true)][string]$BackupManifest,
    [string]$Port='COM3'
)
$ErrorActionPreference='Stop'
$manifestPath=(Resolve-Path -LiteralPath $BackupManifest).Path
$backup=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$image=[IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $manifestPath) $backup.file))
if ((Split-Path -Parent $image) -ne (Split-Path -Parent $manifestPath) -or
    $backup.port -ne $Port -or $backup.flash_bytes -ne 16777216 -or
    -not (Test-Path -LiteralPath $image) -or (Get-Item -LiteralPath $image).Length -ne 16777216 -or
    (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash -ne $backup.sha256) {
    throw 'Backup size, location, device port or checksum failed. Nothing written.'
}
$installations=Get-Content -LiteralPath 'C:\Espressif\tools\eim_idf.json' -Raw | ConvertFrom-Json
$installation=$installations.idfInstalled | Where-Object { $_.name -eq 'v6.0.1' } | Select-Object -First 1
if (-not $installation) { throw 'ESP-IDF 6.0.1 Python environment missing.' }
Write-Output 'Restoring the verified complete USB backup, including its saved configuration.'
$ErrorActionPreference='Continue'
& $installation.python -m esptool --chip esp32s3 --port $Port --baud 921600 --before default-reset --after hard-reset write-flash 0x0 $image
exit $LASTEXITCODE
