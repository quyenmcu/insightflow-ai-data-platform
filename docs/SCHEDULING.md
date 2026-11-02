# Scheduled cloud pipeline

The `InsightFlow cloud pipeline` GitHub Actions workflow runs Mondays at 08:00
Asia/Taipei (00:00 UTC). Manual runs are available through **Run workflow** in
Actions. Changes to its workflow file on `main` also trigger a validation run.
GitHub may queue or delay scheduled runs; this is not an exact-time guarantee.

## Run order

1. Run integration and safety tests with a disposable PostgreSQL service.
2. Authenticate to Google Cloud with Workload Identity Federation.
3. Verify the fixed source snapshot and load all nine BigQuery raw tables.
4. Verify row counts and schemas, then dry-run typed source projections.
5. Run synthetic GoogleSQL checks and transactionally publish the models.
6. Compare seven metrics against the PostgreSQL baseline.
7. Save a JSON report and GitHub run summary.

This replays a fixed historical Olist snapshot. It does not fetch new orders
from a live business system or automatically replace the snapshot manifest.
GitHub-hosted runners execute the work, so your PC and Docker Desktop can be off.
No Cloud Scheduler, Cloud Run service, or VM is provisioned.

## Identity and access

The dedicated account is
`insightflow-pipeline@insightflow-ai-20261102-fefa.iam.gserviceaccount.com`.
Federation trusts immutable repository ID `1442527558` under owner ID `129649836`,
only on `refs/heads/main`, and only for `.github/workflows/cloud-pipeline.yml`.
No service-account JSON key is created or stored as a GitHub secret.

| Scope | Granted role |
| --- | --- |
| Dedicated project | BigQuery Job User; Service Usage Consumer |
| Source bucket only | Storage Object Viewer; Storage Bucket Viewer |
| `raw`, `staging`, `analytics` datasets only | Dataset WRITER (BigQuery Data Editor equivalent) |
| Service account only | Workload Identity User for the restricted repository principal |

These grants do not permit project IAM administration, billing administration,
or source object uploads. The owner-run setup command is:

```powershell
.\infrastructure\configure_github_oidc.ps1
```

It enables IAM, IAM Credentials, and Security Token Service APIs and preserves
existing access bindings. It refuses to reuse a provider with a different trust
condition or issuer. Dataset grants use the documented access-list API because
dataset IAM bindings require allowlisting on this account.

## Reports and failures

Open [the cloud workflow](https://github.com/quyenmcu/insightflow-ai-data-platform/actions/workflows/cloud-pipeline.yml)
for summaries, logs, and the `cloud-pipeline-report-*` artifact. Reports include
stage outcomes, row counts, source fingerprints, BigQuery job IDs, metrics,
billed bytes, timestamps, and failure details. They expire after 14 days. Only
the report is uploaded; generated authentication files are ignored.

If tests or authentication fail, the pipeline stage does not run. If ingestion
fails, models are not built. Raw batches can be partially refreshed; rerunning
replaces rather than appends. A failed transactional model build keeps the last
successful analytics publication. Resolve the cause, then rerun the workflow.
Concurrency controls prevent overlapping workflow runs, and the pipeline job
has a 20-minute timeout.

The model query retains its 1 GiB billed-byte limit and the project retains its
NT$150 monthly alert budget. GitHub usage allowances and Google Cloud Free Tier
quotas depend on total account usage.

To pause scheduled runs, disable this cloud workflow in GitHub Actions. The
separate `Pipeline tests` workflow can continue running on code changes.

References: [Google's auth action](https://github.com/google-github-actions/auth),
[federation setup](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines),
[GitHub schedule events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
