param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot '../.cloud.local.json'),
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
# Pass only the resource settings needed for loading, not billing identifiers.
$loadSettings = [ordered]@{
    projectId = $settings.projectId
    location = $settings.location
    rawBucket = $settings.rawBucket
    sourcePrefix = $settings.sourcePrefix
}
$arguments = @('python3', '/workspace/infrastructure/load_bigquery.py')
if ($VerifyOnly) { $arguments += '--verify-only' }
$loadSettings | ConvertTo-Json | & (Join-Path $PSScriptRoot 'cloud.ps1') @arguments
