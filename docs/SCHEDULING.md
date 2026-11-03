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

Dashboard publication uses a separate downstream job with a short-lived GitHub job token and `contents: write`. The warehouse job retains `contents: read`; the publication job has no Google Cloud identity. It runs only after the warehouse job supplies its validated snapshot artifact. No personal access token or Site credential is stored for this schedule.

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
reports and validated aggregate snapshots are uploaded; generated authentication files are ignored. The publication job preserves a `dashboard-publication-*` artifact with the data commit, checksum, and readback result.

If tests or authentication fail, the pipeline stage does not run. If ingestion
fails, models are not built. Raw batches can be partially refreshed; rerunning
replaces rather than appends. A failed transactional model build keeps the last
successful analytics publication. Resolve the cause, then rerun the workflow.
Concurrency controls prevent overlapping workflow runs, and the pipeline job
has a 20-minute timeout.

## Dashboard refresh

After a successful model build, the pipeline exports purchase-month/customer-state aggregates from BigQuery in a single read query. It checks the expected build ID and source fingerprint, daily-sales totals, registered headline metrics, and the complete aggregate hash against the bundled PostgreSQL reference. It dry-runs the query and applies a 1 GiB maximum billed-byte cap. Failure prevents downstream publication.

The publication job downloads only the snapshot artifact from that workflow run, validates it again, creates a data-only Git tree, and advances `codex/dashboard-data` without force. The first publication creates an orphan data branch; subsequent commits preserve its history. Readback is pinned to the exact new commit and compared byte-for-byte with the artifact. This uses the job's temporary GitHub token; no authoring-session credentials are needed.

On page open, the private hosted dashboard reads the public repository's aggregate snapshot and displays export/build provenance. The host remains private. A failed/invalid remote read falls back to the bundled snapshot with a warning, and exports older than nine days show a freshness notice. Already open pages need a reload to load newly published data; CDN caching can add a short delay. No extra schedule or routine Site deployment is created.

If only publication fails, rerun the failed dashboard job while the snapshot artifact remains within its 14-day retention period. The artifact name is stable within a workflow run so job-only retries can retrieve it across run attempts. For an expired artifact, rerun the full workflow. Non-fast-forward branch updates fail rather than overwriting concurrent changes. An error after the branch update (for example, readback or report upload failure) may mean the snapshot was published; inspect the branch and publication logs before retrying.

The model query retains its 1 GiB billed-byte limit and the project retains its
NT$150 monthly alert budget. GitHub usage allowances and Google Cloud Free Tier
quotas depend on total account usage.

To pause scheduled runs, disable this cloud workflow in GitHub Actions. The
separate `Pipeline tests` workflow can continue running on code changes.

References: [Google's auth action](https://github.com/google-github-actions/auth),
[federation setup](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines),
[GitHub schedule events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
