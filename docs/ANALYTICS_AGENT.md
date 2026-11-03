# Analytics agent preparation

The read-only calculation layer is implemented in `agent/analytics.mjs`. It is a provider-independent foundation for conversational analytics; it is not yet wired to a model, server endpoint, or the hosted chat panel. The existing guided dashboard remains operational.

## Approved operations

| Tool | Output |
| --- | --- |
| `metric_summary` | A selected metric for an explicit purchase-month range and customer states. |
| `metric_series` | Monthly or state groups with supporting counts. |
| `rank_groups` | Up to ten ranked groups; late-rate rankings require at least 20 labeled deliveries. |
| `compare_scopes` | Two explicit selections, their values, right-minus-left change, and relative change when defined. |
| `metric_definition` | Metric meaning and unit. |

Supported metrics are delivered item GMV, all-status orders, delivered orders, average delivered item order value, late-delivery rate, delivered payments, and delivered freight. Money uses BRL cents; rates use ratios. AOV and delay rates return numerators and denominators and are recomputed from totals. Missing denominators and undefined relative growth produce null rather than invented values.

Every result includes the selection, metric definition, source fingerprint, aggregate checksum, build ID, and export timestamp when applicable. The caller must first load a verified snapshot using the existing feed validator. Scope validation rejects unknown states, reversed dates, dates outside the available history, extra arguments, unsupported metrics, and arbitrary tool names. Tools execute no SQL, network calls, shell commands, or writes. They do not modify the snapshot.

```powershell
node --test agent/tests/*.test.mjs dashboard/tests/*.test.mjs
```

The combined suite passed 27 tests locally, including nine new calculation-tool checks. GitHub's dashboard job now includes these tests.

## API access status

The owner approved secure key creation and the ignored root `.env.local` destination for `OPENAI_API_KEY`. The key was created through OpenAI Developers with the owner's selected 24-hour expiration. No secret values or local environment files are committed or deployed.

The initial bounded API verification request reached OpenAI and returned HTTP 429 with `credit_balance_exhausted` / `insufficient_quota`. The selected account needs API credits before live model verification can succeed. The owner chose to add credits. No further model requests, alternate keys, or billing changes were made automatically after that response. The agent has not been enabled in production.

After credits are available, remaining implementation includes the bounded model/tool loop, server-side authentication and secret configuration, persistent request/spend reservations, conversation handling, hosted chat integration, and live known-answer verification. The 24-hour key lifetime must be respected; a durable deployment needs a separately approved longer-lived or renewed key. Do not claim an application usage counter is an account-wide or Google Cloud billing cap.

The intended interaction is one analytics agent calling approved calculations and answering with evidence. No specialist agents, sandbox execution, unrestricted database queries, causal claims, or production delivery predictions are required.

References: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling), [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk), and [API billing](https://platform.openai.com/settings/organization/billing).
