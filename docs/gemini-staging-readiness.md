# Berry Store Gemini — staging readiness report

Date: 11 November 2026 (Malaysia). Decision: **NOT READY FOR PRODUCTION; definition of done is not met.**

## Delivered and deployed

- Original uploaded Gemini React/TypeScript components, layout, styling and four supplied image assets imported. No generic replacement dashboard.
- React production build, TypeScript checks and frontend utility tests pass. Dependencies pinned, npm lockfile committed, prototype Express `server.ts` excluded, unused Supabase/GenAI browser dependencies removed.
- Separate Flask host `admin_app.py` serves the Vite build. It never imports or runs `bot.py`. Docker final image contains only the Python host and compiled frontend.
- Staging: https://berry-gemini-admin-staging.onrender.com/dashboard
- Render service: `srv-dbq2g9mk1f9s73de0u50`, free plan, Oregon, manual deploys only.
- First verified live deploy: `dep-dbq2g9uk1f9s73de0usg`, source `15ececd8dcb3dde3aa389387987c3e6a4409a200`. See later deployment evidence for a superseding revision.
- Draft follow-up PR: https://github.com/syedahmadaziq07-collab/berry-store-bot/pull/25
- PR #24 was already merged before this session started. No merge or production deployment was performed in this session.

## Verification

| Check | Result | Scope and limits |
|---|---|---|
| Clean `npm ci` | PASS | Node 24, pinned dependency lock |
| `npm run lint` | PASS | `tsc --noEmit` |
| `npm run build` | PASS | Original React components compiled to static assets |
| `npm test` | PASS: 5 | Pure frontend business logic; not proof of a live ledger transaction |
| `npm audit --omit=dev` | PASS | Zero reported production dependency advisories at check time |
| `python -m py_compile admin_app.py bot.py` | PASS | Compiles without importing/running the Telegram bot |
| `python -m unittest discover -s tests -v` | PASS: 46 | 19 new runtime security/adapter tests plus 27 existing regression checks |
| GitHub Actions | PASS: 4 workflows | Verified for commit `15ececd8dcb3dde3aa389387987c3e6a4409a200`; includes new frontend/runtime workflow |
| Render Docker build and deploy | PASS | Live state verified through Render; build also runs TypeScript, utility tests and Vite |
| Live HTTPS smoke checks | PASS: 10; BLOCKED: 1 | Details in `staging-smoke-results.json`; no real payment or broadcast |
| Browser rendering | PASS: desktop login page | Actual deployed page opened; screenshot in `evidence/staging-login.jpg` |
| Supabase connected read access | PASS | Schema, policies, grants and aggregate counts read using the connected account |
| Staging-to-Supabase live data | BLOCKED | Service-role credential and production-confirmed `TENANT_ID` not available to staging |
| Post-login browser navigation and mobile E2E | NOT RUN | Stable owner login handover and complete data configuration still required |
| Telegram read integration | NOT RUN | Production bot token/identity unverified; no Telegram API calls from staging |
| Catalog SQL | PARTIAL | Outer SQL parsed with pglast; PL/pgSQL execution, locks, rollback and concurrency not tested on a database |
| Business writes, order approval, wallet changes, delivery | BLOCKED | No test transaction, delivery, payment or broadcast was executed |

Live HTTPS smoke checks verify: HTML 200; Python liveness with polling disabled; anonymous orders 401; successful temporary test login and HttpOnly/Secure/SameSite cookie; session restoration; missing CSRF 403; wallet adjustment 423; broadcast 423; unavailable analytics 503 rather than invented zeroes; logout revocation. Test credentials and cookies are excluded from evidence and source control. Owner credentials are not yet handed over.

## What works in the new host

All admin routes are behind server-side opaque sessions. Logout deletes the session record, preventing replay of that session. Tokens are stored in SQLite by hash; raw session tokens stay in HttpOnly cookies. CSRF values remain in React memory; cross-origin mutations are denied. Rate limits persist across application restarts on the same state file. No passwords or service keys are put in browser storage. The server ignores client tenant and role parameters.

Products with variants, orders, customers, masked credential metadata, wallet/ledger, referrals, allowlisted bot settings and overview have schema-aware authenticated read adapters. DataStore applies the configured tenant to every PostgREST query, requests explicit columns, walks all 500-row pages, and fails if the safety bound is reached. It never labels a truncated dataset as complete. Decimal arithmetic and Malaysia date boundaries are tested. Revenue is gross approved/completed order value, not a reconciled settlement ledger. Cost basis and AI job counts are unavailable and displayed as unavailable.

Catalog create/update/archive/stock has a validated server adapter and draft atomic RPC with a durable idempotency record. It is **not enabled or database-tested**. Other mutations return an explicit locked or unimplemented response. This is a partial integration, not a completed management system.

## Module gaps

| Module | Current state | Still required |
|---|---|---|
| Overview | Accurate read aggregation adapter | Live tenant verification and reconciliation; database aggregation/snapshot consistency for scale |
| Products / variants | Reads mapped to real product and variant schema | Isolated write tests; separate variant edit transaction; nested variants currently rejected |
| Categories | Missing table reported as an error | Real category schema, product mapping, tenant policies and audited CRUD |
| Orders | Reads; approval/rejection fail closed | Audited atomic approval/rejection, inventory reservation, durable Telegram outbox and idempotent worker |
| Credential inventory | Masked metadata reads; no passwords returned | Validated import/delete, encryption/secret handling, atomic reservation and delivery |
| Customers | Reads and derived order/referral totals | Durable notes/status fields and audited updates; absent status is `unknown` |
| AI Studio / model catalogue | Missing tables reported; simulated health removed | Actual catalogue persistence, provider credentials and non-billable health verification |
| Wallet / Berry Credits | Read adapter; checkout/adjustment locked | Ledger RPC integration, concurrency/retry tests, payment reconciliation and approval |
| Bot control | Allowlisted settings read | Audited settings writes; owner-confirmed bot identity and safe cache refresh |
| Broadcast | History absent explicitly; sending locked | Durable campaigns, opt-out/audience rules, queued delivery and explicit send authorization |
| Referrals / vouchers | Referral counts from users; fake vouchers removed | Verified reward ledger, anti-abuse tests, real voucher schema and API |
| Monitoring / audit | Actual host status and local session/denial audit | Persistent/shared audit store, retention, shared rate limit/session store for multi-instance production |

## Production database audit findings

Read-only inspection of `pg_policies` and table privileges found permissive public policies and anon grants on products, users and credentials, including write access on some tables. Credential SELECT policies are not tenant restricted. These are **critical pre-existing database exposure risks**; securing the new dashboard alone does not fix them. No inventory credential contents were retrieved for this audit.

Orders currently deny anon table privileges. Broad policy removal must be coordinated with legacy bot reads/writes, which still use `SUPABASE_KEY` in parts of `bot.py`. Blindly revoking grants could break production. Prepare a tenant-scoped least-privilege policy migration, migrate server-only writes, test against an isolated database, then obtain approval for the production change. Review old dashboard gateway access as part of the same release.

The old Gemini implementation in `bot.py` also has replayable signed-cookie sessions until expiry, capped/placeholder analytics and incomplete adapters. New staging uses the separate corrected host; the old production code was not replaced.

The existing bot runs Telegram `close` and `deleteWebhook(drop_pending_updates=true)` during import/startup when a token is present. Running that process on staging can disrupt production; this deployment avoids it entirely.

Database identity is ambiguous: there are five tenants, and recorded Berry tenant bot usernames differ from the supplied `@berrystorrel`, which appears as the required channel in code. The production Render `TENANT_ID` and Telegram `getMe` must establish the authoritative identity. No tenant was selected by guesswork.

Read-only aggregate audit at check time: 19 products, 662 users, 677 orders, 0 wallets and 0 wallet transactions across **all tenants**. These are not Berry-only dashboard totals and are not seeded into staging. Counts may change with production activity.

## Configuration and access blocker

The Render connector can create the staging service and set variables, but does not expose production secret values. Its browser environment was not logged in. Secure Render login was attempted through the user's chosen Google flow; Google currently reports an incorrect password, so configuration access is blocked.

After owner authentication, configure staging with the authoritative `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` and `TENANT_ID` through server settings. Establish an owner-chosen `ADMIN_PASSWORD_HASH` (Werkzeug scrypt) rather than sharing the temporary test credential. Never commit secrets, copy a Telegram polling token into staging, or put keys in a Vite environment variable. Keep `ADMIN_WRITES_ENABLED=false` and `ADMIN_ISOLATED_DATABASE=false` when reading production data.

For write tests, provision an isolated database with compatible schema and reviewed migrations, then enable the two gates only for that isolated database. The flags are configuration safeguards, not independent proof that a database is isolated. Financial, order delivery and broadcast routes remain unavailable even after the catalog gates are enabled.

SQLite state currently lives on Render's ephemeral filesystem. Deploys may revoke sessions, clear local rate limit history and lose local audit history. A persistent disk/shared store and tested retention are required before production. Do not scale this setup to multiple instances.

## Rollback plan

1. Keep production `berry-store-bot-1` on its existing service, branch and live deploy. No production database migrations were applied, so staging rollback requires no database reversal.
2. If staging misbehaves, disable/suspend only `berry-gemini-admin-staging`, or redeploy the last verified compatible admin-host commit. Never run `bot.py` as a fallback staging start command.
3. Leave all mutation gates off. Revoke/rotate staging authentication and remove the staging database credential if access needs to be withdrawn. Rotation of a shared production service key requires a separately coordinated rollout.
4. For a future approved production release, first capture the production live deploy ID, immutable commit, configuration backup and database backup in secure storage. Roll back application artifacts to the captured compatible deploy if required. A Render rollback does not reverse database writes, Telegram messages or payments.
5. Use additive/backward-compatible migrations. Restore data only with explicit approval and a tested recovery plan; never reset the production database.
6. After any rollback, verify HTTPS, owner login, tenant isolation, product/order reads, Telegram production polling and checkout gates. Confirm auto-deploy remains intentionally off.

## Approval gate

Do not merge PR #25 or deploy to production yet. Production approval should be requested only after live data configuration, database exposure remediation, isolated transactional tests, all module gaps, owner login, mobile/post-login E2E and owner staging acceptance are complete.
