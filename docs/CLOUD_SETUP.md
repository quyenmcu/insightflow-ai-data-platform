# Google Cloud foundation — November 2, 2026

## Created resources

| Resource | Value |
| --- | --- |
| Project | `insightflow-ai-20261102-fefa` |
| Region | `us-central1` |
| Raw bucket | `gs://insightflow-ai-20261102-fefa-raw` |
| BigQuery datasets | `raw`, `staging`, `analytics` |
| Budget | NT$150 per calendar month, scoped only to this project |
| Alerts | 50%, 80%, and 100% of actual spending, before credits |
| Data | Nine original Olist CSV files plus a checksum manifest |
| Access | Uniform bucket-level access; public access prevention enforced |

The billing account uses TWD. NT$150 was chosen conservatively below the US$5
monthly target at the approximate exchange rate when provisioned. Alerts are
not a hard spending cap; review usage before enabling more services.

Only Cloud Storage, BigQuery, and the budget-management API were explicitly
enabled for this foundation, in addition to Google's project defaults. No
continuously running compute, service-account keys, or public access was created.

The source files use the prefix:

```text
olist/09b5148b3a846d400c6c303505b23439cc111b07321abcf203c84894db512afa/
```

The snapshot has a checksum manifest in both the repository and the same cloud
prefix. Credentials and billing account identifiers are excluded from Git.

Verification passed for all nine CSV file sizes and MD5 checksums, totaling
126,186,995 bytes. The uploaded manifest checksum, bucket access protections,
dataset locations, and project-scoped budget settings were also verified with
`infrastructure/verify_cloud.ps1`.

## Open in Google Cloud

- [Project dashboard](https://console.cloud.google.com/home/dashboard?project=insightflow-ai-20261102-fefa)
- [Raw storage bucket](https://console.cloud.google.com/storage/browser/insightflow-ai-20261102-fefa-raw?project=insightflow-ai-20261102-fefa)
- [BigQuery workspace](https://console.cloud.google.com/bigquery?project=insightflow-ai-20261102-fefa)

## What remains

The nine raw tables are loaded with explicit STRING schemas. Successful load
jobs, zero rejected records, table schemas, and row counts were verified:

| Raw table | Rows |
| --- | ---: |
| customers | 99,441 |
| geolocation | 1,000,163 |
| order_items | 112,650 |
| order_payments | 103,886 |
| order_reviews | 99,224 |
| orders | 99,441 |
| products | 32,951 |
| sellers | 3,095 |
| product_category_name_translation | 71 |
| **Total** | **1,550,922** |

The next milestone is to port typed staging and analytics models to GoogleSQL.
Those two datasets remain empty. PostgreSQL retains the working local models.
Run instructions are in the [cloud foundation guide](../infrastructure/README.md).
