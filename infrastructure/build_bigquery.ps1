param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot '../.cloud.local.json'),
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$buildSettings = [ordered]@{
    projectId = $settings.projectId
    location = $settings.location
    rawBucket = $settings.rawBucket
    sourcePrefix = $settings.sourcePrefix
}
$arguments = @('python3', '/workspace/infrastructure/build_bigquery.py')
if ($DryRun) { $arguments += '--dry-run' }
$buildSettings | ConvertTo-Json | & (Join-Path $PSScriptRoot 'cloud.ps1') @arguments
