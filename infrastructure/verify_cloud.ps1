param([string]$ConfigPath = (Join-Path $PSScriptRoot '../.cloud.local.json'))
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'source_manifest.json') -Raw | ConvertFrom-Json
$cloud = Join-Path $PSScriptRoot 'cloud.ps1'
$projectFlag = "--project=$($settings.projectId)"

$bucket = ((& $cloud gcloud storage buckets describe "gs://$($settings.rawBucket)" $projectFlag --format=json) | Out-String) | ConvertFrom-Json
if ($bucket.location.ToLowerInvariant() -ne $settings.location -or
    $bucket.default_storage_class -ne 'STANDARD' -or
    $bucket.public_access_prevention -ne 'enforced' -or
    $bucket.uniform_bucket_level_access -ne $true) {
    throw 'Bucket location, storage class, or access protection does not match the intended configuration.'
}

$remoteObjects = @(((& $cloud gcloud storage ls --json "gs://$($settings.rawBucket)/$($settings.sourcePrefix)*.csv" $projectFlag) | Out-String) | ConvertFrom-Json)
if ($remoteObjects.Count -ne $manifest.files.Count -or $remoteObjects.Count -ne 9) {
    throw 'Expected exactly nine uploaded CSV objects.'
}
foreach ($file in $manifest.files) {
    $objectName = "$($settings.sourcePrefix)$($file.file)"
    $matches = @($remoteObjects | Where-Object { $_.metadata.name -eq $objectName })
    if ($matches.Count -ne 1) { throw "Missing or ambiguous cloud object: $($file.file)" }
    $remoteMd5 = [BitConverter]::ToString([Convert]::FromBase64String($matches[0].metadata.md5Hash)).Replace('-', '').ToLowerInvariant()
    if ([long]$matches[0].metadata.size -ne [long]$file.bytes -or $remoteMd5 -ne $file.md5) {
        throw "Cloud size or MD5 differs from the source manifest: $($file.file)"
    }
}

# Verify the manifest itself without downloading any CSV data.
$remoteManifest = ((& $cloud gcloud storage objects describe "gs://$($settings.rawBucket)/$($settings.sourcePrefix)source_manifest.json" $projectFlag --format=json) | Out-String) | ConvertFrom-Json
$localManifestMd5 = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'source_manifest.json') -Algorithm MD5).Hash.ToLowerInvariant()
$remoteManifestMd5 = [BitConverter]::ToString([Convert]::FromBase64String($remoteManifest.md5_hash)).Replace('-', '').ToLowerInvariant()
if ($localManifestMd5 -ne $remoteManifestMd5) { throw 'Uploaded source manifest checksum differs from the local manifest.' }

foreach ($dataset in @('raw', 'staging', 'analytics')) {
    $metadata = ((& $cloud bq "--project_id=$($settings.projectId)" --format=prettyjson show --dataset "$($settings.projectId):$dataset") | Out-String) | ConvertFrom-Json
    if ($metadata.location.ToLowerInvariant() -ne $settings.location) {
        throw "BigQuery dataset location does not match: $dataset"
    }
}

$budget = ((& $cloud gcloud billing budgets describe $settings.budgetId "--billing-account=$($settings.billingAccountId)" $projectFlag --format=json) | Out-String) | ConvertFrom-Json
$thresholds = @($budget.thresholdRules | ForEach-Object { [double]$_.thresholdPercent } | Sort-Object)
if ($budget.amount.specifiedAmount.currencyCode -ne $settings.budgetCurrency -or
    [decimal]$budget.amount.specifiedAmount.units -ne [decimal]$settings.budgetAmount -or
    $budget.budgetFilter.calendarPeriod -ne 'MONTH' -or
    $budget.budgetFilter.projects.Count -ne 1 -or
    $budget.budgetFilter.projects[0] -ne "projects/$($settings.projectNumber)" -or
    ($thresholds -join ',') -ne '0.5,0.8,1') {
    throw 'Budget amount, currency, period, project scope, or alert thresholds do not match.'
}

[ordered]@{
    projectId = $settings.projectId
    location = $settings.location
    verifiedCsvFiles = $remoteObjects.Count
    verifiedCsvBytes = ($manifest.files | Measure-Object -Property bytes -Sum).Sum
    bucketAccess = 'Public access prevented; uniform bucket-level access enabled'
    datasets = @('raw', 'staging', 'analytics')
    monthlyAlertBudget = "$($settings.budgetAmount) $($settings.budgetCurrency)"
    alertThresholds = $thresholds
} | ConvertTo-Json -Depth 4
