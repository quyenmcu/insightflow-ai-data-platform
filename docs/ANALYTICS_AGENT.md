# Analytics chat

InsightFlow uses one OpenAI Agents SDK agent with `gpt-6-luna` to interpret historical commerce questions. It compares states or periods, ranks groups, describes trends, and explains approved metrics. It cannot query arbitrary SQL, access customer records, report current activity or profit, infer causes, or make operational delivery predictions.

## Verified calculations

Five read-only tools in `agent/analytics.mjs` operate on the dashboard's validated aggregate snapshot: `metric_summary`, `metric_series`, `rank_groups`, `compare_scopes`, and `metric_definition`. Results record scope, metric definition, supporting counts, source fingerprint, aggregate checksum, warehouse build ID, and export time.

Supported metrics are delivered item GMV, all-status orders, delivered orders, average delivered item order value, late-delivery rate, delivered payments, and delivered freight. Money uses BRL cents. Rates and AOV use summed numerators and denominators. Undefined values remain null. Late-rate rankings require at least 20 labeled deliveries.

Numerical answers are formatted directly from successful calculator results. Model prose cannot replace their amounts or percentage changes. Validation rejects unknown states, reversed/out-of-history dates, unsupported metrics, extra arguments, and arbitrary tools. The model receives aggregates, the question, and bounded conversation history; it receives no raw customer or order records.

## Hosted operation

The root `.openai/hosting.json` retains the existing owner-private Site identity. The Vinext Worker exposes authenticated same-origin `/api/chat` and `/api/chat/health` endpoints. Sites supplies the verified visitor identity. The API key remains server-side as a Sites runtime secret. Guided metrics remain available without model calls. Changing filters or clearing chat discards browser conversation history; D1 stores no conversations.

Each request accepts at most 1,000 message characters, bounded history, two tool calls, three agent turns, and 1,000 output tokens per model response. Responses storage and SDK tracing are disabled, requests time out, and automatic provider retries are disabled.

D1 atomically reserves requests before model use: **10 per UTC day and 100 per UTC month**, shared across this Site. Failed calls consume a reservation. Only reservation ID, UTC day/month, and creation time are stored. Missing accounting blocks model use. A conservative $0.02 reservation per request represents a $2 monthly application allowance; it is not measured billing or an account-wide hard spending cap. OpenAI and Google Cloud charges are separate.

The owner selected a key with a **24-hour expiration**. Credits were added and a live Responses request succeeded. Funding does not extend key expiration. Durable deployment requires a separately approved replacement or longer-lived key. Never commit `.env.local` or include it in deployment archives.

## Development and verification

Use Node 22.13+ and the locked pnpm version from the repository root:

```powershell
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm dev
```

The bundled Sites starter supplies loopback-only mock sign-in for development. Apply the Drizzle migration to local D1 before testing; Sites publication applies production migrations. Local Workers load the ignored root `.env.local`. The optional `agent/server.mjs` is a loopback-only Node preview with an ignored filesystem request ledger.

The 35 automated chat/dashboard checks include weighted metrics, invalid scopes, ungrounded-answer rejection, SDK conversation shapes, financial formatting, and real SQLite execution of the deployed accounting migration. Live smoke cases cover SP/RJ comparison, a February follow-up, and rejection of fabricated 2026 profit. Build artifacts are scanned for the local key and environment files before packaging. Live smoke checks use real API allowance and do not run in CI.

References: [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk), [function calling](https://developers.openai.com/api/docs/guides/function-calling), [model details](https://developers.openai.com/api/docs/models/gpt-6-luna), and [API billing](https://platform.openai.com/settings/organization/billing).
