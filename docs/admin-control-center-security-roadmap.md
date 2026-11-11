# Berry Store Admin Control Center — Security Audit & Phased Upgrade

Date: 2026-11-11
Scope: existing `dashboard.html`, Flask routes in `bot.py`, and Supabase-backed shop, orders, wallets and bot settings.
Status: audit + initial hardening **only**. No live deploy, migration, new paid feature or wallet mutation.

## Existing structure (verified in main)
- `dashboard.html`: single-file browser application with navigation for Dashboard, Products, Orders, AI Wallet, Broadcast, Referral, Bot Settings, Notifications and more.
- `bot.py`: Flask serves `/dashboard` and dashboard API routes, Telegram bot runs alongside it.
- Existing API: `/api/dashboard/approve-order`, `reject-order`, `order-receipt/<order_id>`, `ai-wallets` and others.
- Supabase: products, product_variants, orders, credentials, users, bot_settings, tenant tables, AI wallets and ledger.
- Render service `berry-store-bot-1` currently has auto-deploy OFF; this PR must stay draft until reviewed.

## Findings (severity / evidence / required remediation)
1. **CRITICAL — browser-side service-role credential.** `dashboard.html` asks for the Supabase `service_role` key and instantiates `supabase.createClient(url, key)`; it also persists the key in `localStorage` as `bs_key`. Anyone who obtains the key can bypass RLS. The client-side tenant filter is not an authorization boundary. **Fix before opening dashboard to staff or customers**: use server-side Supabase access and authenticated, authorized dashboard sessions; remove key input and localStorage use; rotate exposed credentials after cutover.
2. **HIGH — shared admin secret in browser storage.** `DASHBOARD_ADMIN_SECRET` is entered in the dashboard and stored as `bs_dash_secret` in localStorage, and transmitted in `X-Dashboard-Secret`. Replace with secure HttpOnly/SameSite session cookie + CSRF protection, role-based permissions, short session lifetime, login throttling and audit log. Do not use service-role key as a browser login credential.
3. **HIGH — tenant isolation relies on client-side filters for some UI reads.** `sb.from` is wrapped to append `tenant_id` in JavaScript; this is trivially bypassable when using a privileged key. Enforce tenant identity and ownership **server-side on every read/write**. Recheck existing order approval/rejection for tenant scope.
4. **HIGH — order receipt endpoint** uses a server-side secret but reads an order by ID and downloads Telegram file; verify tenant ownership, validate IDs and authorize receipt scope before returning data.
5. **MEDIUM — no-cache/security response headers** were absent on dashboard endpoints. Phase 1 adds `Cache-Control: no-store, private`, `Pragma: no-cache`, `nosniff`, `Referrer-Policy: no-referrer` and `X-Frame-Options: DENY`. This does **not** remediate credential storage.
6. **MEDIUM — secret comparison** previously used a plain string equality. Phase 1 switches to `hmac.compare_digest`. This is defense-in-depth, not a substitute for login.
7. **HIGH — financial operations.** AI wallet is currently read-only in dashboard; do not introduce top-up, debit or refund until an atomic idempotent ledger, pricing snapshot, provider failure handling, webhook verification, reconciliation, limits and audit trail are tested.
8. **MEDIUM — operational safety.** No automatic deployment; stage backend/auth migration behind a separate draft PR and validate Telegram Browse Shop / order lifecycle regression before production.

## Target control center architecture

```
Admin browser (no privileged keys)
  -> HTTPS Flask admin API
     -> authenticated admin session + CSRF + RBAC + tenant authorization
     -> server-side Supabase service key (Render environment only)
     -> audit log for every sensitive change
Telegram bot
  -> same tenant-scoped services/config
AI workers/provider
  -> async jobs, pricing snapshot, ledger, results and retries
```

## Phased delivery
- **Phase 1 — audit and low-risk hardening (this PR):** document architecture and security gaps; add security response headers, timing-safe secret comparison and a visible warning on legacy key flow. No database writes.
- **Phase 2 — secure dashboard login:** admin identity, server sessions, CSRF, RBAC and tenant-scoped API; migrate read-only dashboard data first, then replace browser Supabase key usage; test and rotate old keys after cutover.
- **Phase 3 — Browse Shop management:** categories, visibility, ordering, product/variant CRUD, pricing, inventory, banners, cache invalidation, publish preview, audit trail. The bot must read the same persisted settings.
- **Phase 4 — Orders and customers:** approval/rejection authorization, receipts, stock/credential delivery, search, filters, refund policies, notifications.
- **Phase 5 — AI Studio:** model catalog, provider credentials stored server-side, feature flags, prompts, generation jobs, output delivery, per-model cost controls.
- **Phase 6 — Wallet and payments:** admin reconciliation, idempotent ledger top-up/debit/refund, provider failure refund, payment webhook verification and alerts; test with fake credits before real money.
- **Phase 7 — marketing and operations:** broadcast, referrals, vouchers, admin roles, analytics, bot maintenance, export, backups, monitoring.

## Acceptance gates before any live deploy
1. Python syntax and dashboard inline JavaScript syntax checks pass.
2. Dashboard must not require or persist Supabase service-role credentials in browser **before production admin rollout**.
3. Every admin read/write checks authenticated role and server-side tenant scope.
4. Regression: /start, Browse Shop, product list, variants, order creation, approval, auto-delivery, wallet read, heartbeat.
5. Wallet write paths remain disabled until reconciliation and failure tests pass.
6. Review draft PR, verify Render source commit, manually deploy only after explicit approval.

## Phase 1 test notes
- Verify `python -m py_compile bot.py`.
- Verify Flask test client returns security headers for `/dashboard` and `/api/dashboard/*` (both successful and failed requests).
- Verify invalid dashboard secret is rejected, valid secret still works, and no privileged keys are logged.
- Verify existing UI remains compatible; browser credential warning is intentional and does not change login behavior.

**IMPORTANT:** Existing privileged-browser credential exposure is not fixed by Phase 1. Do not treat this PR as authorization to expose the dashboard to other admins or accept real-money AI wallet actions.
