param(
    [ValidateSet('Build', 'Flash', 'Monitor', 'BuildOTA', 'FlashOTA')]
    [string]$Action = 'Build',
    [string]$Port = 'COM3',
    [string]$BackupManifest = ''
)
$ErrorActionPreference = 'Stop'
$installations = Get-Content -LiteralPath 'C:\Espressif\tools\eim_idf.json' -Raw | ConvertFrom-Json
$installation = $installations.idfInstalled | Where-Object { $_.name -eq 'v6.0.1' } | Select-Object -First 1
if (-not $installation) { throw 'ESP-IDF v6.0.1 is not installed.' }
# The EIM-generated profile on this PC contains a malformed quoted PATH entry.
# Activate only this process from the installed tool manifest instead.
$env:IDF_PATH = $installation.path
$env:IDF_TOOLS_PATH = $installation.idfToolsPath
$env:IDF_PYTHON_ENV_PATH = Split-Path (Split-Path $installation.python -Parent) -Parent
$env:ESP_IDF_VERSION = '6.0.1'
$env:IDF_VERSION = '6.0.1'
$env:IDF_CCACHE_ENABLE = '1'
$env:IDF_COMPONENT_LOCAL_STORAGE_URL = "file://$($installation.idfToolsPath)"
$manifest = Get-Content -LiteralPath "$($installation.path)\tools\tools.json" -Raw | ConvertFrom-Json
$toolPaths = @((Split-Path $installation.python -Parent), "$($installation.path)\tools")
foreach ($tool in $manifest.tools) {
    $version = $tool.versions | Where-Object { $_.status -eq 'recommended' } | Select-Object -First 1
    if (-not $version) { continue }
    $toolRoot = Join-Path $installation.idfToolsPath "$($tool.name)\$($version.name)"
    foreach ($segments in $tool.export_paths) {
        $exportPath = Join-Path $toolRoot ($segments -join '\')
        if (Test-Path -LiteralPath $exportPath) { $toolPaths += $exportPath }
    }
    foreach ($property in $tool.export_vars.PSObject.Properties) {
        $value = $property.Value.Replace('${TOOL_PATH}', $toolRoot)
        Set-Item -Path "Env:$($property.Name)" -Value $value
    }
}
$env:PATH = ($toolPaths -join ';') + ';' + $env:PATH
$projectPath = 'C:\esp\mochi-workspace\firmware'
if (-not (Test-Path -LiteralPath $projectPath)) {
    throw 'The workspace junction C:\esp\mochi-workspace is missing. See README.md.'
}
$idfArgs = @('-C', $projectPath)
if ($Action -in @('BuildOTA','FlashOTA')) {
    $idfArgs += @('-B','C:\esp\mochi-workspace\firmware\build-ota',
        '-D','SDKCONFIG=C:\esp\mochi-workspace\.runtime\sdkconfig-ota',
        '-D','SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.ota.defaults')
}
if ($Action -eq 'FlashOTA') {
    if (-not $BackupManifest -or -not (Test-Path -LiteralPath $BackupManifest)) { throw 'OTA migration requires the verified full-flash backup manifest.' }
    $backup = Get-Content -LiteralPath $BackupManifest -Raw | ConvertFrom-Json
    $image = Join-Path (Split-Path -Parent (Resolve-Path -LiteralPath $BackupManifest).Path) $backup.file
    if ($backup.flash_bytes -ne 16777216 -or $backup.port -ne $Port -or
        -not (Test-Path -LiteralPath $image) -or (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash -ne $backup.sha256) {
        throw 'Full-flash backup verification failed; migration cancelled.'
    }
}
switch ($Action) {
    'Build'   { $idfArgs += 'build' }
    'Flash'   { $idfArgs += @('-p', $Port, '-b', '921600', 'flash') }
    'Monitor' { $idfArgs += @('-p', $Port, 'monitor') }
    'BuildOTA' { $idfArgs += 'build' }
    'FlashOTA' { $idfArgs += @('-p',$Port,'-b','921600','flash') }
}
# Windows PowerShell turns redirected native stderr warnings into terminating
# errors under Stop. IDF's exit code is the authoritative build result.
$ErrorActionPreference = 'Continue'
& $installation.python "$($installation.path)\tools\idf.py" @idfArgs
$idfExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
exit $idfExitCode
