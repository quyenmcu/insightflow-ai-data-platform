param([string]$ConfigPath = (Join-Path $PSScriptRoot 'cloud_pipeline.json'))
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$cloud = Join-Path $PSScriptRoot 'cloud.ps1'
$projectFlag = "--project=$($settings.projectId)"
$serviceAccount = "$($settings.serviceAccountId)@$($settings.projectId).iam.gserviceaccount.com"
$member = "serviceAccount:$serviceAccount"
$poolName = "projects/$($settings.projectNumber)/locations/global/workloadIdentityPools/$($settings.poolId)"
$workflowRef = "$($settings.repository)/.github/workflows/cloud-pipeline.yml@refs/heads/main"
$condition = "assertion.repository_id == '$($settings.repositoryId)' && assertion.repository_owner_id == '$($settings.repositoryOwnerId)' && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == '$workflowRef'"
$mapping = 'google.subject=assertion.sub,attribute.repository_id=assertion.repository_id'

& $cloud gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com $projectFlag --quiet
$accounts = @(((& $cloud gcloud iam service-accounts list $projectFlag --format=json) | Out-String) | ConvertFrom-Json)
if (-not ($accounts | Where-Object { $_.email -eq $serviceAccount })) {
    & $cloud gcloud iam service-accounts create $settings.serviceAccountId '--display-name=InsightFlow scheduled pipeline' $projectFlag --quiet
}
$pools = @(((& $cloud gcloud iam workload-identity-pools list --location=global $projectFlag --format=json) | Out-String) | ConvertFrom-Json)
if (-not ($pools | Where-Object { $_.name -eq $poolName })) {
    & $cloud gcloud iam workload-identity-pools create $settings.poolId --location=global '--display-name=InsightFlow GitHub Actions' $projectFlag --quiet
}
$providers = @(((& $cloud gcloud iam workload-identity-pools providers list "--workload-identity-pool=$($settings.poolId)" --location=global $projectFlag --format=json) | Out-String) | ConvertFrom-Json)
$existing = $providers | Where-Object { $_.name -eq "$poolName/providers/$($settings.providerId)" }
if (-not $existing) {
    & $cloud gcloud iam workload-identity-pools providers create-oidc $settings.providerId "--workload-identity-pool=$($settings.poolId)" --location=global --issuer-uri=https://token.actions.githubusercontent.com "--attribute-mapping=$mapping" "--attribute-condition=$condition" $projectFlag --quiet
} elseif ($existing.attributeCondition -ne $condition -or $existing.oidc.issuerUri -ne 'https://token.actions.githubusercontent.com') {
    throw 'Existing identity provider differs from the expected repository/branch/workflow trust policy.'
}
$principal = "principalSet://iam.googleapis.com/$poolName/attribute.repository_id/$($settings.repositoryId)"
& $cloud gcloud iam service-accounts add-iam-policy-binding $serviceAccount "--member=$principal" --role=roles/iam.workloadIdentityUser $projectFlag --quiet

foreach ($role in @('roles/bigquery.jobUser', 'roles/serviceusage.serviceUsageConsumer')) {
    & $cloud gcloud projects add-iam-policy-binding $settings.projectId "--member=$member" "--role=$role" --condition=None --quiet
}
foreach ($role in @('roles/storage.objectViewer', 'roles/storage.bucketViewer')) {
    & $cloud gcloud storage buckets add-iam-policy-binding "gs://$($settings.rawBucket)" "--member=$member" "--role=$role" $projectFlag --quiet
}
foreach ($dataset in @('raw', 'staging', 'analytics')) {
    $datasetName = "$($settings.projectId):$dataset"
    $metadata = ((& $cloud bq "--project_id=$($settings.projectId)" --format=json show --dataset=true $datasetName) | Out-String) | ConvertFrom-Json
    $canWrite = $metadata.access | Where-Object { $_.userByEmail -eq $serviceAccount -and $_.role -in @('WRITER', 'OWNER', 'roles/bigquery.dataEditor', 'roles/bigquery.dataOwner') }
    if (-not $canWrite) {
        # Dataset IAM bindings require allowlisting on some accounts. The
        # documented access-list API supports the equivalent dataset WRITER
        # role. Preserve all other existing principals and authorized views.
        $entries = @($metadata.access | Where-Object { $_.userByEmail -ne $serviceAccount })
        $entries += [ordered]@{ role = 'WRITER'; userByEmail = $serviceAccount }
        $patchPath = Join-Path $PSScriptRoot ".dataset-access-$dataset.json"
        try {
            $patchJson = @{ access = $entries } | ConvertTo-Json -Depth 20
            [System.IO.File]::WriteAllText($patchPath, $patchJson, [System.Text.UTF8Encoding]::new($false))
            & $cloud bq "--project_id=$($settings.projectId)" update "--source=/workspace/infrastructure/.dataset-access-$dataset.json" $datasetName
        } finally {
            if (Test-Path -LiteralPath $patchPath) { Remove-Item -LiteralPath $patchPath }
        }
        $verified = ((& $cloud bq "--project_id=$($settings.projectId)" --format=json show --dataset=true $datasetName) | Out-String) | ConvertFrom-Json
        if (-not ($verified.access | Where-Object { $_.userByEmail -eq $serviceAccount -and $_.role -eq 'WRITER' })) {
            throw "Dataset writer grant was not applied: $dataset"
        }
    }
}

[ordered]@{
    serviceAccount = $serviceAccount
    workloadIdentityProvider = "$poolName/providers/$($settings.providerId)"
    trustedWorkflow = $workflowRef
    serviceAccountKeysCreated = $false
} | ConvertTo-Json
