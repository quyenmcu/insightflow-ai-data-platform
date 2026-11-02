param([string]$ConfigPath = (Join-Path $PSScriptRoot '../.cloud.local.json'))
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$manifestPath = Join-Path $PSScriptRoot 'source_manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ($settings.rawDataDirectory -notin @('data/raw', 'data/raw/olist')) {
    throw 'rawDataDirectory must be data/raw or data/raw/olist.'
}
if ($manifest.files.Count -ne 9 -or $settings.sourcePrefix -ne "olist/$($manifest.datasetSha256)/") {
    throw 'Expected the nine-file manifest and its matching content-addressed source prefix.'
}
$sourcePaths = @()
foreach ($file in $manifest.files) {
    if ($file.file -match '[/\\]' -or -not $file.file.EndsWith('.csv')) {
        throw 'Manifest entries must be CSV filenames without directory components.'
    }
    $path = Join-Path $repositoryRoot "$($settings.rawDataDirectory)/$($file.file)"
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Local source does not match the recorded dataset: $($file.file)"
    }
    $sourcePaths += "/workspace/$($settings.rawDataDirectory)/$($file.file)"
}

$cloud = Join-Path $PSScriptRoot 'cloud.ps1'
$projectFlag = "--project=$($settings.projectId)"
$destination = "gs://$($settings.rawBucket)/$($settings.sourcePrefix)"
& $cloud gcloud storage cp --no-clobber --content-type=text/csv @sourcePaths $destination $projectFlag --quiet
& $cloud gcloud storage cp --no-clobber --content-type=application/json /workspace/infrastructure/source_manifest.json "${destination}source_manifest.json" $projectFlag --quiet
& (Join-Path $PSScriptRoot 'verify_cloud.ps1') -ConfigPath $ConfigPath
