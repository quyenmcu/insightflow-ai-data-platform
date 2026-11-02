# Invoke Google's CLI tools without installing Python or the SDK on Windows.
# Examples:
#   .\infrastructure\cloud.ps1 gcloud version
#   .\infrastructure\cloud.ps1 gcloud auth login --no-launch-browser
#   .\infrastructure\cloud.ps1 bq version
$ErrorActionPreference = 'Stop'

if ($args.Count -eq 0 -or $args[0] -notin @('gcloud', 'bq')) {
    throw 'Usage: .\infrastructure\cloud.ps1 <gcloud|bq> [arguments]'
}

$cloudTool = $args[0]
$cloudToolArguments = @($args | Select-Object -Skip 1)
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$dockerArguments = @('run', '--rm', '-i')
if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
    $dockerArguments += '-t'
}

# This named Docker volume keeps Google login credentials outside Git and the
# repository. Only source data and infrastructure files are mounted, read-only.
$dockerArguments += @(
    '--mount', 'type=volume,source=insightflow-gcloud-config,target=/root/.config/gcloud',
    '--mount', "type=bind,source=$repositoryRoot/data/raw,target=/workspace/data/raw,readonly",
    '--mount', "type=bind,source=$PSScriptRoot,target=/workspace/infrastructure,readonly",
    '--workdir', '/workspace',
    'gcr.io/google.com/cloudsdktool/google-cloud-cli:stable',
    $cloudTool
)

& docker @dockerArguments @cloudToolArguments
if ($LASTEXITCODE -ne 0) {
    throw "Google Cloud command failed with exit code $LASTEXITCODE."
}
