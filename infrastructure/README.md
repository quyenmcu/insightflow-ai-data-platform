# Google Cloud foundation

Status: the dedicated development project, private Cloud Storage landing area,
three BigQuery datasets, and monthly alert budget are created. The nine Olist
CSV files and their checksum manifest are uploaded. The nine BigQuery raw tables
are loaded and verified. Typed staging and analytics models remain to be ported.

See [the setup record](../docs/CLOUD_SETUP.md) for the deployed resource names.

## First sign-in

Start Docker Desktop and open PowerShell in the repository directory:

```powershell
.\infrastructure\cloud.ps1 gcloud auth login --no-launch-browser
```

Follow the command's instructions: open the Google sign-in link in your browser
and finish the authorization in your own terminal. Do not paste login codes,
tokens, or credentials into chat or GitHub. The login is stored in the named
Docker volume `insightflow-gcloud-config`, outside the repository.

Verify authentication and list available billing accounts:

```powershell
.\infrastructure\cloud.ps1 gcloud auth list
.\infrastructure\cloud.ps1 gcloud billing accounts list
```

If your account has no billing account, create or choose one in the Google Cloud
console yourself. An account with a currency other than USD requires the budget
amount to be expressed in that billing account's currency.

## Foundation configuration

| Setting | Initial choice |
| --- | --- |
| Project | `insightflow-ai-20261102-fefa` |
| Region | `us-central1` for both storage and BigQuery datasets. |
| Cloud Storage | One Standard bucket for the nine original Olist CSV files. |
| Bucket access | Uniform bucket-level access and public access prevention. |
| BigQuery | Raw, staging, and analytics datasets in the same region. |
| Spending target | US$5 target; the TWD billing account has an NT$150 monthly alert budget. |
| Compute | Run ingestion locally; no continuously running cloud compute. |

`us-central1` is one of the regions eligible for Cloud Storage's Free Tier.
Eligibility and quotas are shared with other usage on your billing account;
they do not guarantee a zero bill. Keep the bucket and BigQuery datasets in the
same location to meet load-job location requirements.

Configure an alerts-only budget before uploading data, with thresholds at 50%,
80%, and 100% of the monthly target. Budget alerts do not enforce a hard cap.
Use BigQuery query dry runs and an explicit maximum-bytes-billed limit. A data
upload, storage, or query can still incur charges depending on account usage.

## Verify and repeat the upload

Environment identifiers, including the billing account ID, are in the ignored
root `.cloud.local.json`. `cloud.example.json` documents its structure for another
authorized checkout. Google credentials remain in the named Docker volume.

```powershell
.\infrastructure\verify_cloud.ps1
```

Verification checks the nine cloud CSV objects against manifest sizes and MD5
checksums, verifies the uploaded manifest itself, checks private bucket settings
and dataset locations, and validates the budget amount, scope, and thresholds.
It reads resource metadata without running BigQuery data queries.

The original dataset is described by `source_manifest.json`, which records its
source URL and per-file SHA-256 and MD5 hashes. Its dataset fingerprint is the
SHA-256 of the UTF-8 compact JSON representation of the sorted file records used
when the snapshot was prepared. Treat this fingerprint as the snapshot ID rather
than recomputing it with a different JSON serializer.

To upload the exact same dataset again:

```powershell
.\infrastructure\upload_raw.ps1
```

The command verifies each local SHA-256 before uploading, uses a content-addressed
prefix, skips existing objects, and then verifies the cloud copy. The local CSVs
can be in `data/raw` or `data/raw/olist`, as configured in `.cloud.local.json`.
An existing object with unexpected content causes verification to fail. No
service-account keys or public access are needed.

## Load BigQuery raw tables

```powershell
.\infrastructure\load_bigquery.ps1
```

The load script checks Cloud Storage object sizes and checksums against the
validated source contract, then loads all nine tables into `raw`. The explicit
schemas in `bigquery_tables.json` use nullable STRING columns to preserve IDs,
ZIP prefixes, and raw source values. CSV headers are skipped; UTF-8, quoted
newlines, and embedded ASCII control characters are supported. Malformed records
and unknown fields are rejected rather than skipped.

After each table, the script verifies the load job succeeded, accepted the
expected row count with zero rejected records, and produced the expected schema
and table row count. It prints job IDs and source SHA-256 digests for provenance.
Row counts and schemas are read through metadata APIs; verification does not
submit data-scanning SQL queries.

Each successful load replaces one table atomically. **The nine-table batch is
not a single transaction.** A failure stops the batch; rerunning refreshes the
tables without appending duplicates. Do not run downstream transformations until
the entire load has succeeded. BigQuery CSV empty-field handling can differ from
PostgreSQL's handling of quoted empty strings; normalize blanks in staging.

Verify the existing tables without reloading:

```powershell
.\infrastructure\load_bigquery.ps1 -VerifyOnly
```

`ingestion.batch.prepare_bigquery` generates the load contract by checking exact
CSV headers and record widths, counting records with a CSV parser, and requiring
SHA-256 agreement with the recorded uploaded snapshot. When preparing a new
snapshot, regenerate the contract after updating the source manifest; do not
hand-edit expected counts to bypass a load mismatch.

The Cloud CLI wrapper can run the SDK's bundled Python through its `python3`
tool option. The loader receives only project, location, bucket, and source-prefix
settings over stdin. Billing identifiers and repository credentials are not
mounted in that container.

## References

- [Official Google Cloud CLI Docker image](https://docs.cloud.google.com/sdk/docs/downloads-docker)
- [Cloud Storage Free Tier](https://cloud.google.com/storage/pricing#cloud-storage-always-free)
- [BigQuery load-job location considerations](https://docs.cloud.google.com/bigquery/docs/locations#load-cloud-storage)
- [Google Cloud budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets)
