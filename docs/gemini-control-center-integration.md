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
