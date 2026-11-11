# Gemini Admin Control Center integration (work in progress)

Source artifact: user-provided `berry-store-admin-control-center.zip`. Do not deploy its `server.ts` to production; it uses prototype/in-memory behavior.

## Initial API bridge

`GET /api/admin/v1/dashboard/overview` is a **read-only** Python backend endpoint. It requires the existing `X-Dashboard-Secret` header, server-side `TENANT_ID`, and `SUPABASE_SERVICE_KEY`. Returns totalRevenue, totalOrders, activeProducts, totalCustomers, pendingOrders, completedOrders, dataLimited. Queries cap at 500 rows, so totals are incomplete when dataLimited is true. This is an integration scaffold, **not yet the final analytics endpoint**.

## Required before replacing /dashboard

- Import and build the Gemini React + TypeScript frontend as static assets served by the existing Python service.
- Replace Gemini's `/api/admin/v1/auth/*` prototype with a server-issued short-lived session, CSRF protection, rate limiting and secure cookie.
- Implement authenticated API adapters for products, categories, orders, customers, credentials, AI Studio, wallet, bot settings, broadcast, referrals and audit logs.
- All sensitive mutations must be allowlisted and tenant scoped. Wallet adjustments require an audited atomic ledger RPC; never direct balance edits.
- Remove mock data, hardcoded password fallbacks and fake successful actions.
- Test API contracts, database writes, approvals, inventory, and Telegram integration in staging.
- Only then swap the `/dashboard` route. Rotate any previously exposed service-role key.
- Do not enable checkout or process real payments.

This branch is intentionally safe to review but **not production ready**.

## Added read-only adapters (draft)

- `GET /api/admin/v1/shop/products` — product summary (up to 500)
- `GET /api/admin/v1/orders` — order summary without receipt file IDs (up to 500)
- `GET /api/admin/v1/customers` — customer summary (up to 500)
- Overview now returns the `kpis`, `revenueTrend`, `categoryRevenue` keys expected by Gemini React. Time-based revenue and wallet liability are placeholders and **must not be presented as verified zeroes**. Fix before production.

These endpoints currently require `X-Dashboard-Secret`. The original Gemini frontend does not send that header; a secure session layer and frontend API integration are still required.

## Authentication work (current branch)

Python now exposes `POST /api/admin/v1/auth/login`, `GET /api/admin/v1/auth/me`, and `POST /api/admin/v1/auth/logout`. Login requires the existing `DASHBOARD_ADMIN_SECRET` (minimum 24 characters), issues a signed 1-hour HttpOnly Secure SameSite=Strict cookie, and returns a CSRF token. Mutating requests must include `X-CSRF-Token`. Login attempts are limited in-memory per remote address; replace with shared Redis/store before multi-instance production. This is **not** yet a full session revocation model. Logout clears the cookie, but a stolen signed cookie remains valid until expiry.

**Frontend integration required:** Remove Gemini's hardcoded demo-password button. Save the CSRF token in React memory on login or `auth/me`; send it on all mutating fetches including logout. Use relative URLs and same-origin cookies. Do not persist token or password in localStorage. The current Gemini frontend has not yet been committed to this branch or built into Flask static assets.

**Known blockers:** The current list endpoints and overview still have 500-row caps; time-based KPIs are placeholders. Additional read-only and write endpoints are unimplemented. Do not merge/deploy.
