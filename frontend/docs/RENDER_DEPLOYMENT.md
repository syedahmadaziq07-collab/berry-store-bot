# BERRY STORE — RENDER & TELEGRAM BOT PRODUCTION INTEGRATION GUIDE

## 1. Overview
This guide provides the exact instructions to deploy the Berry Store Admin Control Center to your Render service `berry-store-bot-1` and link it with `bot.py` and Supabase.

---

## 2. Environment Variables on Render
Configure these in **Render Dashboard → berry-store-bot-1 → Environment**:

| Variable | Recommended Value / Setting | Description |
|---|---|---|
| `ADMIN_PASSWORD` | *(Your Secret Password)* | Single password for dashboard login (e.g. `berrystore2026!`) |
| `SUPABASE_URL` | `https://gtqthdxltczovkiuoyyr.supabase.co` | Supabase project URL |
| `SUPABASE_KEY` | *(Your Supabase anon key)* | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | *(Your Supabase service_role key)* | Required for atomic wallet ledger RPC |
| `TENANT_ID` | `d18e5472-7ba2-40f9-a311-bf3cbe285624` | Tenant ID for Berry Store |
| `BOT_TOKEN` | *(Your Telegram Bot Token)* | Telegram Bot Token from @BotFather |
| `PORT` | `5000` | Port for Flask web server |

---

## 3. Resolving the "q.eq is not a function" Error
The previous error occurred because `dashboard.html` loaded the Supabase JavaScript library into the browser and called:
```js
sb.from(table).eq('tenant_id', TENANT_ID); // ❌ Throws "q.eq is not a function" because .select() was omitted
```
In this modern architecture:
1. **Zero Privileged Keys in the Browser**: The frontend never talks to Supabase directly.
2. **Server-Side API**: All requests go through `/api/admin/v1/*` which are authenticated with a single admin password via secure HttpOnly cookies.
3. **Tenant-Scoped Queries**: All database queries enforce `tenant_id = TENANT_ID` server-side.

---

## 4. Telegram Bot Live Sync Verification
- **Product Editing**: Changes to prices, stock, or status take effect within the cache TTL (60s) or immediately upon cache invalidation.
- **Order Approval**: When an admin clicks "Lulus Bayaran" (Approve Payment), the backend marks the order `completed`, decrements available stock, and dispatches credentials to the user.
- **Bot Control**: Welcome messages, announcement banners, and maintenance mode toggles are read directly from `bot_settings` table by `bot.py`.
