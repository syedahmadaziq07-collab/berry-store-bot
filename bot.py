"""
Telegram Store Bot — Stable Version for Replit
Run: python bot.py
"""

BOT_BUILD = "coistr-start-fix-v3"

import os
import sys
import time
import random
import logging
import threading
import asyncio
import json
import re
import urllib.error
import urllib.request
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone, time as dt_time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# ─── Kill Any Other Running Bot Instance ──────────────────────────────────────
# Runs BEFORE polling starts. Forces Telegram to drop any existing session
# (other Replit tab, old Render deploy, etc.) so this instance takes over cleanly.

import httpx as _httpx_early
import os as _os_early

_EARLY_TOKEN = (
    (_os_early.getenv("BOT_TOKEN") or "").strip() or
    (_os_early.getenv("TOKEN") or "").strip() or
    (_os_early.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
)

if _EARLY_TOKEN:
    try:
        _httpx_early.get(
            f"https://api.telegram.org/bot{_EARLY_TOKEN}/close",
            timeout=10,
        )
        print("✅ Old sessions closed")
    except Exception as _e:
        print(f"⚠️ Could not close old session: {_e}")

    try:
        _httpx_early.get(
            f"https://api.telegram.org/bot{_EARLY_TOKEN}/deleteWebhook?drop_pending_updates=true",
            timeout=10,
        )
        print("✅ Webhook cleared, pending updates dropped")
    except Exception as _e:
        print(f"⚠️ Could not clear webhook: {_e}")

    print("🚀 This instance is now the ONLY running bot!")

    # Log current webhook info for diagnostics
    try:
        _wh_resp = _httpx_early.get(
            f"https://api.telegram.org/bot{_EARLY_TOKEN}/getWebhookInfo",
            timeout=10,
        )
        _wh_data = _wh_resp.json()
        _wh_result = _wh_data.get("result") or {}
        print(f"[WEBHOOK_INFO] url={_wh_result.get('url','')!r} "
              f"has_custom_certificate={_wh_result.get('has_custom_certificate')} "
              f"pending_update_count={_wh_result.get('pending_update_count')} "
              f"last_error_date={_wh_result.get('last_error_date')} "
              f"last_error_message={_wh_result.get('last_error_message','')!r}")
    except Exception as _e:
        print(f"[WEBHOOK_INFO] Could not fetch: {_e}")

# ─── Logging Setup ────────────────────────────────────────────────────────────
# Logs to console AND to bot.log file for debugging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ─── Load Environment Variables ───────────────────────────────────────────────

def _get_env(key: str, fallback: str = "") -> str:
    """Get env var, strip whitespace, return fallback if empty."""
    return (os.getenv(key) or fallback).strip()

BOT_TOKEN    = _get_env("BOT_TOKEN") or _get_env("TOKEN") or _get_env("TELEGRAM_BOT_TOKEN")
SUPABASE_URL         = _get_env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY         = _get_env("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = _get_env("SUPABASE_SERVICE_KEY")
ADMIN_ID     = 0
MASTER_ADMIN_ID = int(_get_env("MASTER_ADMIN_ID", "0"))
REQUIRED_CHANNEL     = "@berrystorrel"
REQUIRED_CHANNEL_URL = "https://t.me/berrystorrel"
PORT         = int(_get_env("PORT", "5000"))
DASHBOARD_ADMIN_SECRET = _get_env("DASHBOARD_ADMIN_SECRET")
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_CACHE_FILE = os.path.join(BASE_DIR, "products_cache.json")
TENANT_ID           = _get_env("TENANT_ID")

TENANT_TABLES = {"products", "product_variants", "orders", "credentials", "users", "bot_settings", "push_subscriptions", "rental_payments", "points"}

def _ensure_tenant_filter(table: str, params: str = "") -> str:
    if TENANT_ID and table in TENANT_TABLES:
        tenant_param = f"tenant_id=eq.{TENANT_ID}"
        if params:
            if not re.search(r'(^|&)tenant_id=', params):
                return f"{tenant_param}&{params}"
        else:
            return tenant_param
    return params

def _ensure_tenant_data(data: dict) -> dict:
    if TENANT_ID and not data.get("tenant_id"):
        d = dict(data)
        d["tenant_id"] = TENANT_ID
        return d
    return data

def require_tenant_id() -> bool:
    return bool(TENANT_ID)

def is_admin_user(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_tenant_active() -> bool:
    if not TENANT_ID:
        return False
    try:
        rows = sb_get("tenants", f"select=id,status,rent_end&id=eq.{TENANT_ID}&limit=1")
        if not rows:
            return False
        t = rows[0]
        if t.get("status") != "active":
            return False
        rent_end = t.get("rent_end")
        if rent_end:
            from datetime import datetime, timezone
            end = datetime.fromisoformat(rent_end.replace("Z", "+00:00"))
            if end < datetime.now(timezone.utc):
                return False
        return True
    except Exception as exc:
        log.warning(f"Tenant check failed: {_safe_error(exc)}")
        return True

async def _block_if_expired(update, context) -> bool:
    user = update.effective_user
    if not is_tenant_active():
        if user.id == ADMIN_ID:
            msg = "⚠️ Your bot rental has expired. Please renew to continue using the bot."
        else:
            msg = "⚠️ Shop is currently unavailable. The store owner's bot rental has expired."
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(msg)
            elif update.message:
                await update.message.reply_text(msg)
        except Exception:
            pass
        return True
    return False

def _redact(text: object) -> str:
    value = str(text)
    for secret in (BOT_TOKEN, SUPABASE_KEY, SUPABASE_SERVICE_KEY, DASHBOARD_ADMIN_SECRET):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value[:500]

def _safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {_redact(exc)}"

try:
    ADMIN_ID = int(_get_env("ADMIN_ID", "0"))
except ValueError:
    log.warning("ADMIN_ID bukan nombor — ditetapkan kepada 0")

TESTIMONIALS_CHANNEL_ID   = -1003850553745
TESTIMONIALS_CHANNEL_ID_2 = -1003831715755
_bot_settings:   dict         = {}

# ─── Startup Check ────────────────────────────────────────────────────────────

log.info("=" * 50)
log.info(f"BOT_TOKEN    : {'✅ set' if BOT_TOKEN else '❌ MISSING'}")
log.info(f"SUPABASE_URL : {'✅ ' + SUPABASE_URL[:35] if SUPABASE_URL else '❌ MISSING'}")
log.info(f"SUPABASE_KEY : {'✅ set (len=' + str(len(SUPABASE_KEY)) + ')' if SUPABASE_KEY else '❌ MISSING'}")
log.info(f"SUPABASE_SERVICE_KEY : {'✅ set (len=' + str(len(SUPABASE_SERVICE_KEY)) + ')' if SUPABASE_SERVICE_KEY else '⚠️ NOT SET — admin writes will use anon key'}")
log.info(f"ADMIN_ID     : {ADMIN_ID if ADMIN_ID else '❌ MISSING'}")
log.info(f"MASTER_ADMIN_ID: {MASTER_ADMIN_ID if MASTER_ADMIN_ID else '❌ NOT SET'}")
log.info(f"TENANT_ID    : {'✅ ' + TENANT_ID[:20] if TENANT_ID else '❌ MISSING'}")
log.info(f"REQUIRED_CHANNEL: {REQUIRED_CHANNEL if REQUIRED_CHANNEL else '❌ NOT SET'}")
log.info(f"[BOT_BUILD] {BOT_BUILD}")
# NOTE: Tenant validity check moved into _log_tenant_info() called from
# build_app() — do NOT call sb_get here, it's not defined yet.
log.info("=" * 50)

if not BOT_TOKEN:
    log.warning("BOT_TOKEN tidak ditetapkan. Flask server akan berjalan, tetapi bot Telegram tidak aktif.")
    log.warning("Set BOT_TOKEN dalam Replit Secrets untuk mengaktifkan bot.")

def _validate_telegram_token() -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        bot = payload.get("result") or {}
        username = bot.get("username") or "unknown"
        log.info(f"Telegram token ✅ valid for @{username}")
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            log.critical("Telegram token rejected by Telegram API. Update the TELEGRAM_BOT_TOKEN secret, then restart the workflow.")
            return False
        log.warning(f"Telegram token precheck HTTP error code={exc.code}; polling will still try to start.")
        return True
    except Exception as exc:
        log.warning(f"Telegram token precheck skipped due to network/error: {_safe_error(exc)}")
        return True

# Validate Supabase config
_supabase_ready = False
log.info(f"[SUPABASE] SUPABASE_URL set={bool(SUPABASE_URL)} value_prefix={SUPABASE_URL[:30]!r}")
log.info(f"[SUPABASE] SUPABASE_KEY set={bool(SUPABASE_KEY)} len={len(SUPABASE_KEY)} starts_with_eyJ={SUPABASE_KEY.startswith('eyJ')}")
if SUPABASE_URL and SUPABASE_KEY:
    if not SUPABASE_URL.startswith("https://"):
        log.warning(f"[SUPABASE] ❌ SUPABASE_URL mesti bermula 'https://' — got: {SUPABASE_URL[:40]!r}")
        SUPABASE_URL = ""
    elif not SUPABASE_KEY.startswith("eyJ"):
        log.warning(f"[SUPABASE] ❌ SUPABASE_KEY tidak bermula 'eyJ' (len={len(SUPABASE_KEY)}) — guna anon/public key dari Supabase dashboard")
        SUPABASE_KEY = ""
    elif len(SUPABASE_KEY) <= 100:
        log.warning(f"[SUPABASE] ❌ SUPABASE_KEY terlalu pendek len={len(SUPABASE_KEY)} — pastikan key penuh disalin")
        SUPABASE_KEY = ""
    else:
        _supabase_ready = True
        log.info("[SUPABASE] ✅ URL dan KEY lulus semakan format")
else:
    missing = []
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_KEY: missing.append("SUPABASE_KEY")
    log.warning(f"[SUPABASE] ❌ Supabase tidak dikonfigurasi — pemboleh ubah hilang: {', '.join(missing)}")
log.info(f"[SUPABASE] _supabase_ready={_supabase_ready}")

# ─── Supabase REST Helpers (direct httpx, no library) ────────────────────────

import httpx as _httpx

_products_cache      = {"data": [], "updated_at": 0.0}
_products_cache_data = {"products": [], "variants": [], "timestamp": 0}
CACHE_TTL            = 60  # seconds
_supabase_ok         = False


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _sb_admin_headers() -> dict:
    """Use service role key for write operations that bypass RLS."""
    key = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def sb_get(table: str, params: str = "") -> list:
    """SELECT rows. Returns list of dicts."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    effective_params = _ensure_tenant_filter(table, params)
    if effective_params:
        url += "?" + effective_params
    r = _httpx.get(url, headers=_sb_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    log.debug(f"[SB GET] {table}?{effective_params} → {len(data) if isinstance(data, list) else data}")
    return data


def sb_post(table: str, data: dict) -> list:
    """INSERT a row. Returns list of inserted rows."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json=_ensure_tenant_data(data), timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_upsert(table: str, data: dict) -> list:
    """UPSERT (insert or update). Returns list of rows."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_headers(), "Prefer": "return=representation,resolution=merge-duplicates"},
        json=_ensure_tenant_data(data), timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_patch(table: str, params: str, data: dict) -> list:
    """UPDATE rows matching params. Returns list of updated rows."""
    effective_params = _ensure_tenant_filter(table, params)
    r = _httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{effective_params}",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_admin_get(table: str, params: str = "") -> list:
    """SELECT rows using service role key (bypasses RLS)."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    effective_params = _ensure_tenant_filter(table, params)
    if effective_params:
        url += "?" + effective_params
    r = _httpx.get(url, headers=_sb_admin_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def sb_admin_post(table: str, data: dict) -> list:
    """INSERT a row using service role key (bypasses RLS)."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_admin_headers(), "Prefer": "return=representation"},
        json=_ensure_tenant_data(data), timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_admin_patch(table: str, params: str, data: dict) -> list:
    """UPDATE rows using service role key (bypasses RLS)."""
    effective_params = _ensure_tenant_filter(table, params)
    r = _httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{effective_params}",
        headers={**_sb_admin_headers(), "Prefer": "return=representation"},
        json=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()

def sb_admin_upsert(table: str, data: dict) -> list:
    """UPSERT using service role key (bypasses RLS)."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_admin_headers(), "Prefer": "return=representation,resolution=merge-duplicates"},
        json=_ensure_tenant_data(data), timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _test_supabase() -> tuple:
    """Quick connectivity check. Returns (ok: bool, detail: str)."""
    try:
        rows = sb_get("products", "select=id&limit=1")
        return True, f"test data={rows}"
    except _httpx.HTTPStatusError as exc:
        return False, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _log_tenant_info():
    """Log tenant configuration. Call only after sb_get is defined (i.e. from build_app)."""
    if not TENANT_ID:
        log.info("[TENANT] No TENANT_ID configured — skipping tenant lookup")
        return
    try:
        t_rows = sb_get("tenants", f"select=id,status,rent_end,name,bot_username&id=eq.{TENANT_ID}&limit=1")
        if t_rows:
            t = t_rows[0]
            log.info(f"[TENANT] name   : {t.get('name', 'N/A')}")
            log.info(f"[TENANT] bot    : @{t.get('bot_username', 'N/A')}")
            log.info(f"[TENANT] status : {t.get('status')}")
            log.info(f"[TENANT] rent_end: {t.get('rent_end')}")
            log.info(f"[TENANT] active : {is_tenant_active()}")
            qr_fid = sb_get("bot_settings", "select=value&key=eq.payment_qr_file_id&limit=1")
            qr_url = sb_get("bot_settings", "select=value&key=eq.payment_qr_url&limit=1")
            b_fid  = sb_get("bot_settings", "select=value&key=eq.banner_file_id&limit=1")
            b_url  = sb_get("bot_settings", "select=value&key=eq.banner_url&limit=1")
            log.info(f"[TENANT] QR file_id: {'✅' if qr_fid and qr_fid[0].get('value') else '❌'}")
            log.info(f"[TENANT] QR URL   : {'✅' if qr_url and qr_url[0].get('value') else '❌'}")
            log.info(f"[TENANT] banner   : {'✅' if (b_fid and b_fid[0].get('value')) or (b_url and b_url[0].get('value')) else '❌'}")
        else:
            log.warning(f"[TENANT] ID {TENANT_ID} not found in tenants table — setup incomplete")
    except Exception as exc:
        log.warning(f"[TENANT] lookup failed (will retry at runtime): {_safe_error(exc)}")


# ── Startup connectivity test — 3 attempts ────────────────────────────────────
for _attempt in range(1, 4):
    log.info(f"[SUPABASE] Startup test attempt {_attempt}/3 — URL={SUPABASE_URL[:40]!r} KEY_len={len(SUPABASE_KEY)}")
    _ok, _detail = _test_supabase()
    if _ok:
        log.info(f"[SUPABASE] ✅ Sambungan berjaya — {_detail}")
        _supabase_ok = True
        break
    log.warning(f"[SUPABASE] ❌ Attempt {_attempt} gagal — {_detail}")
    if _attempt < 3:
        log.info("[SUPABASE] Retry dalam 2 saat...")
        time.sleep(2)
else:
    log.error("[SUPABASE] ❌ Semua 3 percubaan gagal. Bot akan cuba semula apabila diperlukan.")


async def _run_supabase(label: str, operation, attempts: int = 3, timeout: int = 12):
    """Run a zero-arg callable in a thread with retry logic."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(operation),
                timeout=timeout,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.info(f"Supabase {label} ok attempt={attempt} duration_ms={elapsed_ms}")
            return result
        except Exception as exc:
            last_exc = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                f"Supabase {label} failed attempt={attempt}/{attempts} duration_ms={elapsed_ms} "
                f"error={_safe_error(exc)}"
            )
            if attempt < attempts:
                await asyncio.sleep(min(0.4 * (2 ** (attempt - 1)) + random.uniform(0, 0.3), 3))
    raise last_exc

async def _get_cached_products_and_variants(force: bool = False):
    """Return (active_products, variants_with_stock) from cache, refreshing if stale."""
    now = time.time()
    if not force and _products_cache_data["products"] and (now - _products_cache_data["timestamp"]) < CACHE_TTL:
        return _products_cache_data["products"], _products_cache_data["variants"]

    # Fetch ALL products (including inactive/deleted) for counting
    all_products = await _run_supabase(
        "products.list",
        lambda: sb_get("products", "select=id,name,stock,price,duration,description,auto_delivery,is_active,status&order=id"),
    ) or []

    # Count products by status
    inactive_count = sum(1 for p in all_products if p.get("is_active") is False)
    deleted_count = sum(1 for p in all_products if str(p.get("status", "")).lower() == "deleted")
    active_products = [
        p for p in all_products
        if p.get("is_active") is not False
        and str(p.get("status", "active")).lower() not in ("inactive", "deleted")
    ]

    # Fetch variants with stock > 0
    all_variants = await _run_supabase(
        "product_variants.all",
        lambda: sb_get("product_variants", "select=id,product_id,variant_name,stock,price,description&stock=gt.0"),
    ) or []

    log.info(f"[SHOP] tenant_id={TENANT_ID} "
             f"active_products_count={len(active_products)} "
             f"inactive_products_count={inactive_count} "
             f"deleted_products_count={deleted_count} "
             f"shown_products_count={len(active_products)}")

    _products_cache_data["products"]  = active_products
    _products_cache_data["variants"]  = all_variants
    _products_cache_data["timestamp"] = now
    return active_products, all_variants


def _cache_products(products):
    _products_cache["data"] = products or []
    _products_cache["updated_at"] = time.time()
    try:
        with open(PRODUCTS_CACHE_FILE, "w", encoding="utf-8") as cache_file:
            json.dump(_products_cache, cache_file, ensure_ascii=False)
    except Exception as exc:
        log.warning(f"Product cache write failed: {_safe_error(exc)}")

def _load_products_cache_from_disk():
    try:
        if not os.path.exists(PRODUCTS_CACHE_FILE):
            return
        with open(PRODUCTS_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            cached = json.load(cache_file)
        if isinstance(cached, dict) and isinstance(cached.get("data"), list):
            _products_cache["data"] = cached.get("data") or []
            _products_cache["updated_at"] = float(cached.get("updated_at") or 0)
            log.info(f"Product cache loaded from disk count={len(_products_cache['data'])}")
    except Exception as exc:
        log.warning(f"Product cache load failed: {_safe_error(exc)}")

def _cached_products(max_age: int | None = 300):
    products = _products_cache.get("data") or []
    updated_at = float(_products_cache.get("updated_at") or 0)
    age = time.time() - updated_at if updated_at else 999999
    if products and (max_age is None or age <= max_age):
        return products, int(age)
    return [], int(age)

_load_products_cache_from_disk()

# ─── Bot Settings (loaded from Supabase bot_settings table) ───────────────────

async def _load_bot_settings():
    global _bot_settings
    try:
        rows = await asyncio.to_thread(
            lambda: sb_get("bot_settings", "select=key,value")
        )
        _bot_settings = {r["key"]: r["value"] for r in rows}
        log.info(f"[SETTINGS] Loaded {len(_bot_settings)} settings from Supabase for tenant={TENANT_ID}")
    except Exception as exc:
        log.warning(f"[SETTINGS] Failed to load settings: {exc}")

async def _setting(key: str, fallback: str = "") -> str:
    """Return a bot setting. Checks in-memory cache first — no Supabase call if already loaded."""
    # Fast path: already loaded by _load_bot_settings() at startup
    if key in _bot_settings:
        return _bot_settings.get(key) or fallback
    # Key not yet cached — fetch from Supabase and store for next time
    try:
        rows = await asyncio.to_thread(
            lambda: sb_get("bot_settings", f"select=value&key=eq.{key}&limit=1")
        )
        if rows and rows[0].get("value"):
            val = rows[0]["value"]
            _bot_settings[key] = val  # cache so subsequent calls are instant
            return val
    except Exception:
        pass
    return fallback

# ─── Flask Keep-Alive Server ──────────────────────────────────────────────────

from flask import Flask, jsonify, request, Response

_app = Flask(__name__)
_telegram_app: object | None = None
_telegram_loop: asyncio.AbstractEventLoop | None = None

def _check_dashboard_secret() -> tuple[bool, str]:
    provided = (
        (request.headers.get("X-Dashboard-Secret") or "").strip()
        or str((request.get_json(silent=True) or {}).get("secret") or "").strip()
    )
    if not DASHBOARD_ADMIN_SECRET:
        return False, "DASHBOARD_ADMIN_SECRET is not configured on server"
    if not provided or provided != DASHBOARD_ADMIN_SECRET:
        return False, "Invalid dashboard admin secret"
    return True, ""

def _run_bot_coro(coro, timeout: int = 45):
    if _telegram_loop is None or _telegram_app is None:
        raise RuntimeError("Telegram app is not running")
    fut = asyncio.run_coroutine_threadsafe(coro, _telegram_loop)
    return fut.result(timeout=timeout)


def _dashboard_admin_ids() -> list[int]:
    ids: list[int] = []
    if ADMIN_ID:
        ids.append(int(ADMIN_ID))
    raw = _get_env("ADMIN_IDS")
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                aid = int(part)
            except ValueError:
                continue
            if aid and aid not in ids:
                ids.append(aid)
    return ids

@_app.route("/")
def _index():
    return f"OK {BOT_BUILD}", 200

@_app.route("/health")
def _health():
    cached, age = _cached_products()
    return jsonify(
        status="ok",
        supabase=_supabase_ok,
        cached_products=len(cached),
        products_cache_age_seconds=age if cached else None,
    ), 200

@_app.route("/dashboard")
def dashboard():
    import os
    dashboard_paths = [
        "dashboard.html",
        "telegram-bot/dashboard.html",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html"),
    ]
    for path in dashboard_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            tenant_script = f'<script>const TENANT_ID = {json.dumps(TENANT_ID or "")};</script>\n'
            html = html.replace("</head>", tenant_script + "</head>")
            return html, 200, {"Content-Type": "text/html"}
    return "Dashboard not found", 404

@_app.route("/api/dashboard/approve-order", methods=["POST"])
def dashboard_approve_order():
    ok, err = _check_dashboard_secret()
    if not ok:
        return jsonify(error=err), 401
    payload = request.get_json(silent=True) or {}
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        return jsonify(error="order_id is required"), 400
    try:
        ctx = SimpleNamespace(bot=_telegram_app.bot)
        _run_bot_coro(_approve_order_core(ctx, order_id), timeout=60)
        return jsonify(ok=True, order_id=order_id, action="approved"), 200
    except Exception as exc:
        return jsonify(error=_safe_error(exc)), 500

@_app.route("/api/dashboard/reject-order", methods=["POST"])
def dashboard_reject_order():
    ok, err = _check_dashboard_secret()
    if not ok:
        return jsonify(error=err), 401
    payload = request.get_json(silent=True) or {}
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        return jsonify(error="order_id is required"), 400
    try:
        ctx = SimpleNamespace(bot=_telegram_app.bot)
        _run_bot_coro(_reject_order_core(ctx, order_id), timeout=30)
        return jsonify(ok=True, order_id=order_id, action="rejected"), 200
    except Exception as exc:
        return jsonify(error=_safe_error(exc)), 500

@_app.route("/api/dashboard/order-receipt/<order_id>", methods=["GET"])
def dashboard_order_receipt(order_id: str):
    ok, err = _check_dashboard_secret()
    if not ok:
        return jsonify(error=err), 401
    order_id = str(order_id or "").strip()
    if not order_id:
        return jsonify(error="order_id is required"), 400
    try:
        rows = sb_get("orders", f"select=id,receipt_file_id,status&id=eq.{order_id}&limit=1")
        order = rows[0] if rows else None
        if not order:
            return jsonify(error="Order not found"), 404
        file_id = (order.get("receipt_file_id") or "").strip()
        if not file_id:
            return jsonify(error="No receipt uploaded for this order"), 404

        async def _download_receipt():
            f = await _telegram_app.bot.get_file(file_id)
            b = await f.download_as_bytearray()
            return bytes(b)

        data = _run_bot_coro(_download_receipt(), timeout=45)
        return Response(data, mimetype="image/jpeg")
    except Exception as exc:
        return jsonify(error=_safe_error(exc)), 500


@_app.route("/api/dashboard/admins", methods=["GET"])
def dashboard_admins():
    ok, err = _check_dashboard_secret()
    if not ok:
        return jsonify(error=err), 401
    try:
        admin_ids = _dashboard_admin_ids()
        if not admin_ids:
            return jsonify(ok=True, admins=[]), 200

        in_ids = ",".join(str(i) for i in admin_ids)
        users = []
        try:
            users = sb_admin_get(
                "users",
                f"select=id,username,first_name,last_name&id=in.({in_ids})",
            ) or []
        except Exception as exc:
            log.warning(f"[DASHBOARD] admins users lookup failed: {_safe_error(exc)}")

        user_map = {str(u.get("id")): u for u in users if u.get("id") is not None}
        admins = []
        for idx, aid in enumerate(admin_ids):
            info = user_map.get(str(aid), {})
            first_name = (info.get("first_name") or "").strip()
            last_name = (info.get("last_name") or "").strip()
            full_name = " ".join(x for x in (first_name, last_name) if x).strip()
            admins.append(
                {
                    "telegram_id": aid,
                    "role": "Main Admin" if idx == 0 else "Admin",
                    "status": "Active",
                    "username": info.get("username") or "",
                    "name": full_name,
                }
            )
        return jsonify(ok=True, admins=admins), 200
    except Exception as exc:
        return jsonify(error=_safe_error(exc)), 500


@_app.route("/api/dashboard/referrals", methods=["GET"])
def dashboard_referrals():
    ok, err = _check_dashboard_secret()
    if not ok:
        return jsonify(error=err), 401
    try:
        points_rows = []
        try:
            points_rows = sb_admin_get(
                "points",
                "select=user_id,username,points,total_orders,updated_at&order=points.desc&limit=1000",
            ) or []
        except Exception as exc:
            log.warning(f"[DASHBOARD] points lookup failed: {_safe_error(exc)}")
            points_rows = []

        if not points_rows:
            return jsonify(ok=True, rows=[]), 200

        user_ids = []
        for row in points_rows:
            uid = row.get("user_id")
            if uid is None:
                continue
            sid = str(uid)
            if sid not in user_ids:
                user_ids.append(sid)

        in_ids = ",".join(user_ids)
        users = []
        orders = []
        referral_summary_rows = []
        if in_ids:
            try:
                users = sb_admin_get(
                    "users",
                    f"select=id,username,first_name,last_name&id=in.({in_ids})",
                ) or []
            except Exception as exc:
                log.warning(f"[DASHBOARD] users lookup failed: {_safe_error(exc)}")
            try:
                orders = sb_admin_get(
                    "orders",
                    f"select=id,user_id,created_at,status&user_id=in.({in_ids})&order=created_at.desc&limit=5000",
                ) or []
            except Exception as exc:
                log.warning(f"[DASHBOARD] last-order lookup failed: {_safe_error(exc)}")
            try:
                referral_summary_rows = sb_admin_get(
                    "referral_summary",
                    f"select=user_id,referrer_id,referral_count&or=(user_id.in.({in_ids}),referrer_id.in.({in_ids}))&limit=5000",
                ) or []
            except Exception:
                referral_summary_rows = []

        user_map = {str(u.get("id")): u for u in users if u.get("id") is not None}
        last_order_map = {}
        for row in orders:
            sid = str(row.get("user_id") or "")
            if sid and sid not in last_order_map:
                last_order_map[sid] = row

        referral_count_map = {}
        for row in referral_summary_rows:
            sid = row.get("user_id") if row.get("user_id") is not None else row.get("referrer_id")
            if sid is None:
                continue
            referral_count_map[str(sid)] = int(row.get("referral_count") or 0)

        merged_rows = []
        for p in points_rows:
            sid = str(p.get("user_id") or "")
            if not sid:
                continue
            u = user_map.get(sid, {})
            first_name = (u.get("first_name") or "").strip()
            last_name = (u.get("last_name") or "").strip()
            full_name = " ".join(x for x in (first_name, last_name) if x).strip()
            points = int(p.get("points") or 0)
            latest = last_order_map.get(sid, {})
            merged_rows.append(
                {
                    "telegram_id": sid,
                    "username": p.get("username") or u.get("username") or "",
                    "name": full_name,
                    "points": points,
                    "eligible": points >= 50,
                    "total_referrals": referral_count_map.get(sid, int(p.get("total_orders") or 0)),
                    "last_activity": latest.get("created_at") or p.get("updated_at"),
                    "last_order_id": latest.get("id"),
                    "last_order_status": latest.get("status"),
                }
            )

        merged_rows.sort(
            key=lambda r: (int(r.get("points") or 0), str(r.get("last_activity") or "")),
            reverse=True,
        )
        return jsonify(ok=True, rows=merged_rows), 200
    except Exception as exc:
        return jsonify(error=_safe_error(exc)), 500

def _start_flask():
    log.info(f"Flask keep-alive berjalan di port {PORT}")
    _app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)

threading.Thread(target=_start_flask, daemon=True).start()

# ─── Telegram Imports ─────────────────────────────────────────────────────────

from telegram import (
    Update,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from telegram.error import Conflict, InvalidToken
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─── UI Helpers ───────────────────────────────────────────────────────────────

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Browse Shop", callback_data="shop"),
         InlineKeyboardButton("📦 My Orders",   callback_data="myorders")],
        [InlineKeyboardButton("👥 Referral",    callback_data="referral"),
         InlineKeyboardButton("💬 Support",     callback_data="support")],
    ])

def back_home():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])

def back_shop():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")]])

async def _safe_edit_or_send(query, text: str, reply_markup=None):
    """Edit callback message; fallback to sending a new message if edit fails."""
    try:
        return await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as exc:
        log.warning(f"[TELEGRAM] edit_message_text fallback: {_safe_error(exc)}")
        return await query.message.reply_text(text, reply_markup=reply_markup)

def build_product_keyboard(products: list) -> ReplyKeyboardMarkup:
    """Number buttons in the keyboard tray, 3 per row, plus a Home button."""
    buttons = []
    row = []
    for i, _ in enumerate(products, 1):
        row.append(KeyboardButton(str(i)))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🏠 Home")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

# ─── Membership gate ──────────────────────────────────────────────────────────

async def _check_membership(bot, user_id: int) -> bool:
    """Check if user is a member of REQUIRED_CHANNEL. Returns True if user can proceed."""
    if not REQUIRED_CHANNEL or REQUIRED_CHANNEL.lower() in ("none", "null", ""):
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        if "Member list is inaccessible" in str(exc):
            log.warning("[MEMBERSHIP] Channel inaccessible. Bot may not be admin/member of REQUIRED_CHANNEL.")
        else:
            log.warning(f"[MEMBERSHIP] Check failed for user {user_id}: {exc}")
        return True

async def _send_join_message(update: Update):
    text = (
        "🔒 To continue, please join our channel first:\n"
        f"• {REQUIRED_CHANNEL}\n\n"
        "After joining, send /start again."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=REQUIRED_CHANNEL_URL)],
    ])
    if update.message:
        await update.message.reply_text(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)

# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"[START] received /start")
    log.info(f"[START] user_id={user.id}")
    log.info(f"[START] chat_id={update.effective_chat.id}")
    log.info(f"[START] tenant_id={TENANT_ID}")
    log.info(f"[START] admin_id={ADMIN_ID}")
    log.info(f"[START] required_channel={REQUIRED_CHANNEL}")

    # ── Force-join membership check ────────────────────────────────────────
    enable_fj = (await _setting("enable_force_join", "false")).lower() == "true"
    log.info(f"[FORCE_JOIN] tenant_id={TENANT_ID} enable_force_join={enable_fj} channel={REQUIRED_CHANNEL}")

    membership_ok = True
    if not enable_fj:
        log.info(f"[FORCE_JOIN] action=skipped")
    else:
        channel_empty = not REQUIRED_CHANNEL or REQUIRED_CHANNEL.lower() in ("none", "null", "")
        if channel_empty:
            log.info(f"[FORCE_JOIN] action=skipped channel_empty")
        else:
            try:
                member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user.id)
                membership_ok = member.status in ("member", "administrator", "creator")
                log.info(f"[FORCE_JOIN] action={'checked_passed' if membership_ok else 'checked_failed'}")
            except Exception as exc:
                if "Member list is inaccessible" in str(exc):
                    log.warning(f"[FORCE_JOIN] action=inaccessible_log_only")
                else:
                    log.warning(f"[FORCE_JOIN] action=failed error={_safe_error(exc)}")

    if not membership_ok:
        await _send_join_message(update)
        return

    # ── Proceed with /start ────────────────────────────────────────────────
    try:
        log.info(f"/start from {user.id} (@{user.username})")

        # Clean up old flow messages before sending new ones
        chat_id = update.effective_chat.id
        await delete_flow_messages(context, context.bot, chat_id, user.id)

        # Instant reply so user knows bot is alive
        await update.message.reply_text("Bot hidup ✅")

        total_users = total_sold = 0
        is_new_user = False
        try:
            def start_stats():
                # STEP 1: Check if user is new BEFORE saving to database
                try:
                    existing = sb_get("users", f"select=id&id=eq.{user.id}")
                    is_new = len(existing) == 0
                except Exception:
                    is_new = False
                # STEP 2: Save user to database as usual (existing code)
                sb_upsert("users", {
                    "id": user.id,
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                })
                users = sb_get("users", "select=id")
                sold  = sb_get("orders", "select=id&status=eq.completed")
                return len(users), len(sold), is_new
            total_users, total_sold, is_new_user = await _run_supabase("start.stats", start_stats)
        except Exception as exc:
            log.warning(f"Supabase /start: {_safe_error(exc)}")

        now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%A, %d %B %Y %H:%M:%S")
        _welcome = await _setting('welcome_message', 'Welcome to Berry Store.')
        await update.message.reply_text(
            f"{_welcome}\n"
            f"Updated: {now}\n\n"
            f"👋 Hi {user.first_name}!\n\n"
            f"👤 Account\n"
            f"• ID: {user.id}\n"
            f"• Username: @{user.username or 'tiada'}\n\n"
            f"📊 Store Stats\n"
            f"• Total Users: {total_users}\n"
            f"• Total Sold: {total_sold} pcs\n\n"
            f"Tekan butang di bawah untuk mula!",
            reply_markup=main_kb(),
        )
        log.info(f"[START] welcome_sent=true")

        # STEP 3: Send notification to admin after saving
        try:
            now_str = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%d/%m/%Y %H:%M")
            if is_new_user:
                notif_text = (
                    "👤 PELANGGAN BARU MASUK!\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"• Nama: {user.first_name}\n"
                    f"• Username: @{user.username or 'tiada'}\n"
                    f"• ID: {user.id}\n"
                    f"• Masa: {now_str}\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🆕 Pengguna baru!"
                )
            else:
                notif_text = (
                    "👤 PELANGGAN AKTIF!\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"• Nama: {user.first_name}\n"
                    f"• Username: @{user.username or 'tiada'}\n"
                    f"• ID: {user.id}\n"
                    f"• Masa: {now_str}\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🔄 Pengguna lama"
                )
            await context.bot.send_message(chat_id=ADMIN_ID, text=notif_text)
        except Exception as e:
            log.warning(f"Admin start notify failed: {e}")

        # STEP 4: Promo message (always sent, never configurable)
        try:
            await update.message.reply_text(
                "Want an auto-order bot for your own shop? PM @berryrc to rent one 🚀"
            )
        except Exception as e:
            log.warning(f"Promo message failed: {e}")
    except Exception as exc:
        log.exception(f"[START_ERROR] user_id={user.id} tenant_id={TENANT_ID}: {_safe_error(exc)}")
        try:
            await update.message.reply_text("⚠️ Bot is starting up. Please try again in a few seconds.")
        except Exception:
            pass

# ─── Shop ─────────────────────────────────────────────────────────────────────

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _check_membership(context.bot, update.effective_user.id):
        await _send_join_message(update)
        return
    if await _block_if_expired(update, context):
        return

    # Clean up old flow messages before showing shop
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await delete_flow_messages(context, context.bot, chat_id, user_id)
    if update.callback_query:
        await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)

    _t_shop = time.monotonic()
    try:
        products, all_variants = await _get_cached_products_and_variants(force=True)
        _cache_products(products)
        log.info(f"[SHOP] tenant={TENANT_ID} user={user_id} products={len(products)} variants={len(all_variants)} "
                 f"load_ms={int((time.monotonic()-_t_shop)*1000)} source=cache_or_supabase")
    except Exception as exc:
        products, age = _cached_products(max_age=None)
        all_variants = []
        if products:
            log.error(f"[SHOP] cache fallback age_s={age}: {_safe_error(exc)}", exc_info=True)
        else:
            log.error(f"[SHOP] no cache: {_safe_error(exc)}", exc_info=True)
            msg = "⚠️ Gagal muatkan produk. Sila cuba lagi atau hubungi @berryrc"
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=back_home())
            else:
                await update.message.reply_text(msg, reply_markup=back_home())
            return

    if not products:
        log.info(f"[SHOP] tenant={TENANT_ID} user={user_id} no products — showing empty message")
        text = "🛍️ Shop is not ready yet. Please contact the store owner."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=back_home())
        else:
            await update.message.reply_text(text, reply_markup=back_home())
        return

    # Save product list so handle_message can resolve number → product
    context.user_data["shop_products"] = products

    try:
        all_creds = await _run_supabase(
            "credentials.stock_check",
            lambda: sb_get("credentials", "select=product_id,variant_id,is_used"),
        ) or []
    except Exception:
        all_creds = []

    # Build variant map: product_id -> list of {id, stock}
    product_variants_map: dict = {}
    for v in all_variants:
        pid = v.get("product_id")
        if pid:
            product_variants_map.setdefault(pid, []).append(v)

    # Build credential maps from all credential rows
    has_creds_for_variant: set = set()   # variant_ids that have ANY credential row
    unused_for_variant: dict  = {}       # variant_id -> count of unused creds
    has_creds_for_product: set = set()   # product_ids with cred rows where variant_id is null
    unused_for_product: dict  = {}       # product_id -> count of unused creds (no variant)
    for c in all_creds:
        vid = c.get("variant_id")
        pid = c.get("product_id")
        if vid:
            has_creds_for_variant.add(vid)
            if not c.get("is_used"):
                unused_for_variant[vid] = unused_for_variant.get(vid, 0) + 1
        elif pid:
            has_creds_for_product.add(pid)
            if not c.get("is_used"):
                unused_for_product[pid] = unused_for_product.get(pid, 0) + 1

    _shop_title = await _setting('shop_title', 'LIST PRODUCT')
    _shop_footer = await _setting('shop_footer', 'Taip nombor atau tekan butang di bawah 👇')
    text = f"╭─────────────────────╮\n┊  {_shop_title}\n┊─────────────────────\n"
    for i, p in enumerate(products, 1):
        pid = p.get("id")
        variants = product_variants_map.get(pid, [])
        if variants:
            # Product has variants — sum up each variant's real available stock
            total = 0
            for v in variants:
                vid = v.get("id")
                if vid in has_creds_for_variant:
                    avail   = unused_for_variant.get(vid, 0)
                    v_src   = "credentials"
                    v_mode  = "auto"
                else:
                    avail   = int(v.get("stock") or 0)
                    v_src   = "variant_stock"
                    v_mode  = "manual"
                log.info(f"[SHOP STOCK] product_id={pid} variant_id={vid} delivery_mode={v_mode} source={v_src} available={avail}")
                total += avail
            log.info(f"[SHOP STOCK] product_id={pid} displayed_total={total}")
            stock = total
        else:
            # No variants — use credential count if credentials exist, else products.stock
            if pid in has_creds_for_product:
                stock  = unused_for_product.get(pid, 0)
                p_src  = "credentials"
                p_mode = "auto"
            else:
                stock  = int(p.get("stock") or 0)
                p_src  = "product_stock"
                p_mode = "manual"
            log.info(f"[SHOP STOCK] product_id={pid} delivery_mode={p_mode} source={p_src} available={stock} displayed_total={stock}")
        text += f"┊ {i}. {p['name']} ( {stock} )\n"
    text += f"╰─────────────────────╯\n\n{_shop_footer}"

    chat_id = update.callback_query.message.chat_id if update.callback_query else update.message.chat_id

    # ── Banner send with tenant-scoped bot_settings ─────────────────────────
    banner_sent = False
    _t_banner = time.monotonic()
    _banner_file_id = await _setting("banner_file_id", "")
    _banner_url = await _setting("banner_url", "")
    _photo = None

    if _banner_file_id:
        _photo = _banner_file_id
    elif _banner_url:
        _photo = _banner_url

    if _photo:
        try:
            banner_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=_photo,
                caption=text,
                reply_markup=build_product_keyboard(products),
            )
            banner_sent = True
            track_flow_message(context, banner_msg, "shop_list")
            log.info(f"[BANNER] Sent via tenant banner ms={int((time.monotonic()-_t_banner)*1000)}")
        except Exception as exc:
            log.warning(f"[BANNER] tenant banner failed, falling back to text: {_safe_error(exc)}")

    if banner_sent:
        return

    log.info(f"[BANNER] Sending text-only (banner_file_id={'yes' if _banner_file_id else 'no'} banner_url={'yes' if _banner_url else 'no'})")
    if update.callback_query:
        shop_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=build_product_keyboard(products),
        )
    else:
        shop_msg = await update.message.reply_text(text, reply_markup=build_product_keyboard(products))
    track_flow_message(context, shop_msg, "shop_list")

# ─── Variant Helpers (product_variants table) ─────────────────────────────────

async def _fetch_db_variants(product_id: int) -> list:
    """Fetch variants for a product from the product_variants table.
    Returns a list of row dicts (id, variant_name, stock, price) or [] on error."""
    try:
        _pid = product_id
        rows = await _run_supabase(
            f"product_variants.list pid={product_id}",
            lambda: sb_get(
                "product_variants",
                f"select=id,variant_name,stock,price,description&product_id=eq.{_pid}&order=id",
            ),
        )
        return rows or []
    except Exception as exc:
        log.warning(f"_fetch_db_variants pid={product_id}: {_safe_error(exc)}")
        return []

# ─── Variant Picker ───────────────────────────────────────────────────────────

async def show_variants(update: Update, context: ContextTypes.DEFAULT_TYPE, product: dict, variants: list):
    """Show inline variant buttons for a product. `variants` is a list of product_variants rows."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        product_id   = product.get("id")
        product_name = product.get("name", "Product")

        if not variants:
            log.warning(f"show_variants: product id={product_id} has no variants, falling back")
            await show_product(update, context, product_id)
            return

        # Store selected product so we have context if needed
        context.user_data["variant_product_id"] = product_id

        # Check if every variant is out of stock
        all_out_of_stock = all(int(v.get("stock", 0)) == 0 for v in variants)
        if all_out_of_stock:
            text = (
                f"📦 {product_name}\n"
                f"⚠️ Stok habis. Semua varian tidak tersedia pada masa ini."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")]
            ])
            await delete_flow_messages(context, context.bot, chat_id, user_id,
                                       ["shop_list", "product_detail", "variant_select", "error_message"])
            if update.callback_query:
                await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)
            oos_msg = await context.bot.send_message(chat_id, text, reply_markup=kb)
            track_flow_message(context, oos_msg, "variant_select")
            return

        prod_desc = product.get("description") or ""
        text = (
            f"📦 {product_name}\n"
            f"─────────────────────\n"
        )
        if prod_desc:
            text += f"{prod_desc}\n─────────────────────\n"
        text += "Pilih varian di bawah 👇"

        # Build inline buttons — 1 per row, callback_data: "variant_{variant_db_id}"
        rows = []
        for v in variants:
            stock     = int(v.get("stock", 0))
            name      = v.get("variant_name", "Variant")
            price     = v.get("price", 0)
            vid       = v.get("id")
            v_desc    = v.get("description") or ""
            btn_label = f"{name}  ( {stock} )  — RM {price}"
            rows.append([InlineKeyboardButton(btn_label, callback_data=f"variant_{vid}")])
        rows.append([InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")])

        kb = InlineKeyboardMarkup(rows)
        await delete_flow_messages(context, context.bot, chat_id, user_id,
                                   ["shop_list", "product_detail", "variant_select", "error_message"])
        if update.callback_query:
            await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)
        var_msg = await context.bot.send_message(chat_id, text, reply_markup=kb)
        track_flow_message(context, var_msg, "variant_select")

    except Exception as exc:
        log.error(f"show_variants error: {_safe_error(exc)}", exc_info=True)
        err = "⚠️ Gagal muatkan variants. Sila cuba lagi."
        await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
        try:
            if update.callback_query:
                err_msg = await update.callback_query.edit_message_text(err, reply_markup=back_shop())
            else:
                err_msg = await update.message.reply_text(err, reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
        except Exception:
            pass

# ─── Product Detail ───────────────────────────────────────────────────────────

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int = 1):
    """Show product detail with live quantity and total price."""
    _t_prod = time.monotonic()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    qty = max(1, min(qty, 10))   # clamp between 1–10
    cached_products, cached_variants = await _get_cached_products_and_variants()
    log.info(f"[TIMING] show_product cache_ms={int((time.monotonic()-_t_prod)*1000)} product_id={product_id}")
    p = next((x for x in cached_products if x["id"] == product_id), None)
    if not p:
        try:
            rows = await _run_supabase(
                f"products.detail id={product_id}",
                lambda: sb_get("products", f"select=id,name,stock,price,duration,description,auto_delivery,delivery_mode,is_active,status&id=eq.{product_id}&limit=1"),
            )
            p = rows[0] if rows else None
        except Exception as exc:
            cached, age = _cached_products(max_age=None)
            p = next((item for item in cached if str(item.get("id")) == str(product_id)), None)
            if p:
                log.warning(f"Supabase product detail fallback id={product_id} cache_age_s={age}: {_safe_error(exc)}")
            else:
                log.warning(f"Supabase product detail failed id={product_id}: {_safe_error(exc)}", exc_info=True)
                err_msg = "⚠️ Gagal muatkan produk. Cuba lagi."
                if update.callback_query:
                    await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
                    err_msg_obj = await update.callback_query.edit_message_text(err_msg, reply_markup=back_shop())
                else:
                    err_msg_obj = await update.message.reply_text(err_msg, reply_markup=back_shop())
                track_flow_message(context, err_msg_obj, "error_message")
                return

    # Reject inactive/deleted products regardless of source
    if p.get("is_active") is False or str(p.get("status", "active")).lower() in ("inactive", "deleted"):
        err_msg = "⚠️ Product ini tidak lagi tersedia."
        if update.callback_query:
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg_obj = await update.callback_query.edit_message_text(err_msg, reply_markup=back_shop())
        else:
            err_msg_obj = await update.message.reply_text(err_msg, reply_markup=back_shop())
        track_flow_message(context, err_msg_obj, "error_message")
        return

    # ── Variant check: use cached variants first, fallback to DB only if needed ──
    db_variants = [v for v in (cached_variants or []) if str(v.get("product_id")) == str(product_id)]
    if not db_variants:
        db_variants = await _fetch_db_variants(product_id)
    log.info(f"[VARIANT DEBUG] product_id={product_id} db_variants count={len(db_variants)} data={db_variants}")
    if db_variants:
        await show_variants(update, context, p, db_variants)
        log.info(f"[TIMING] show_product total_ms={int((time.monotonic()-_t_prod)*1000)} product_id={product_id} mode=variants")
        return

    total = round(p["price"] * qty, 2)
    stock = p.get("stock", 0)

    _delivery_note = "• Akaun diberikan selepas bayar.\n• Akaun peribadi, tidak dikongsi."
    _delivery_setting = await _setting('product_delivery_note', _delivery_note)
    product_text = (
        f"📦 {p['name']}\n"
        f"├─ Stock   : {stock} units\n"
        f"├─ Price   : RM {p['price']}\n"
        f"├─ Duration: {p.get('duration', '-')}\n"
        f"└─ Total   : RM {total}\n\n"
        f"{_delivery_setting}"
    )
    if p.get("description"):
        product_text += f"\n\n{p['description']}"
    product_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"qty_minus_{product_id}_{qty}"),
            InlineKeyboardButton(f"  {qty}  ",  callback_data="qty_display"),
            InlineKeyboardButton("➕", callback_data=f"qty_plus_{product_id}_{qty}"),
        ],
        [InlineKeyboardButton(f"🛒 Buy Now  x{qty}  (RM {total})", callback_data=f"buy_{product_id}_{qty}")],
        [InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")],
    ])

    # Clean up old messages before showing product detail
    await delete_flow_messages(context, context.bot, chat_id, user_id,
                               ["shop_list", "product_detail", "variant_select", "error_message"])
    if update.callback_query:
        await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)
    prod_msg = await context.bot.send_message(chat_id, product_text, reply_markup=product_kb)
    track_flow_message(context, prod_msg, "product_detail")
    log.info(f"[TIMING] show_product total_ms={int((time.monotonic()-_t_prod)*1000)} product_id={product_id} mode=detail")

# ─── Quantity ─────────────────────────────────────────────────────────────────

async def qty_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, current_qty: int, delta: int):
    """Recalculate qty and refresh product detail. Qty is embedded in callback_data, not user_data."""
    new_qty = max(1, min(current_qty + delta, 10))
    await show_product(update, context, product_id, new_qty)

# ─── Create Order ─────────────────────────────────────────────────────────────

async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int, *, variant_label: str = None, variant_price: float = None):
    _t_create = time.monotonic()
    user = update.effective_user
    chat_id = update.effective_chat.id
    log.info(f"[CREATE_ORDER] product_id={product_id} qty={qty} variant={variant_label!r} user={user.id}")

    # Duplicate order creation lock
    lock_user = f"create_order:{user.id}"
    if context.user_data.get(lock_user):
        log.info(f"[CREATE_ORDER] blocked duplicate click user={user.id}")
        return
    context.user_data[lock_user] = True
    p = next((item for item in (context.user_data.get("shop_products") or []) if str(item.get("id")) == str(product_id)), None)
    if not p:
        cached, _age = _cached_products(max_age=None)
        p = next((item for item in cached if str(item.get("id")) == str(product_id)), None)

    # Live revalidation to avoid stale stock/price risks before insert
    try:
        rows = await _run_supabase(
            f"products.order_fetch id={product_id}",
            lambda: sb_get(
                "products",
                f"select=id,name,stock,price,auto_delivery,delivery_mode&id=eq.{product_id}&limit=1",
            ),
        )
        live_p = rows[0] if rows else None
        if live_p:
            p = {**(p or {}), **live_p}
    except Exception as exc:
        if p:
            log.warning(f"Supabase create_order product live-check fallback id={product_id}: {_safe_error(exc)}")
        else:
            context.user_data.pop(lock_user, None)
            log.warning(f"Supabase create_order fetch product_id={product_id}: {_safe_error(exc)}", exc_info=True)
            await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return

    if not p:
        context.user_data.pop(lock_user, None)
        await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return

    # For variant orders the stock was already validated in on_button; only
    # check product-level stock for non-variant orders.
    if variant_price is None and p["stock"] < qty:
        context.user_data.pop(lock_user, None)
        await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Stok tidak mencukupi!", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return

    if variant_price is not None:
        _variant_id = context.user_data.get("selected_variant_id") or None
        if _variant_id:
            try:
                var_rows = await _run_supabase(
                    f"product_variants.revalidate id={_variant_id}",
                    lambda: sb_get(
                        "product_variants",
                        f"select=id,variant_name,stock,price,description,product_id&id=eq.{_variant_id}&limit=1",
                    ),
                )
                live_v = var_rows[0] if var_rows else None
                if not live_v:
                    context.user_data.pop(lock_user, None)
                    await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
                    err_msg = await context.bot.send_message(chat_id, "⚠️ Varian ini telah habis stok.", reply_markup=back_shop())
                    track_flow_message(context, err_msg, "error_message")
                    return
                live_stock = int(live_v.get("stock") or 0)
                if live_stock < qty:
                    context.user_data.pop(lock_user, None)
                    await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
                    err_msg = await context.bot.send_message(chat_id, "⚠️ Stok varian tidak mencukupi!", reply_markup=back_shop())
                    track_flow_message(context, err_msg, "error_message")
                    return
                if str(live_v.get("product_id")) != str(product_id):
                    context.user_data.pop(lock_user, None)
                    await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
                    err_msg = await context.bot.send_message(chat_id, "⚠️ Variant tidak ditemui.", reply_markup=back_shop())
                    track_flow_message(context, err_msg, "error_message")
                    return
                variant_price = float(live_v.get("price"))
                variant_label = str(live_v.get("variant_name") or variant_label or "")
                context.user_data["selected_variant_desc"] = live_v.get("description") or context.user_data.get("selected_variant_desc") or ""
            except Exception as exc:
                context.user_data.pop(lock_user, None)
                log.warning(f"[VARIANT] live revalidate failed id={_variant_id}: {_safe_error(exc)}")
                await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
                err_msg = await context.bot.send_message(chat_id, "⚠️ Ralat variant. Sila cuba lagi.", reply_markup=back_shop())
                track_flow_message(context, err_msg, "error_message")
                return

    # ── Duplicate order protection ─────────────────────────────────────────────
    try:
        existing = await _run_supabase(
            f"orders.dup_check user={user.id}",
            lambda: sb_get("orders",
                f"select=id,product_name,amount,status"
                f"&user_id=eq.{user.id}"
                f"&status=in.(pending,waiting)"
                f"&limit=1"),
        )
        if existing:
            context.user_data.pop(lock_user, None)
            o = existing[0]
            oid = o.get("id", "")
            await delete_flow_messages(context, context.bot, chat_id, user.id,
                                       ["order_summary", "active_order", "product_detail", "variant_select", "error_message"])
            if update.callback_query:
                await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)
            active_msg = await context.bot.send_message(
                chat_id,
                f"⚠️ Anda sudah mempunyai order aktif:\n"
                f"• Order  : {oid}\n"
                f"• Produk : {o.get('product_name','')}\n"
                f"• Jumlah : RM {o.get('amount','')}\n"
                f"• Status : {o.get('status','')}\n\n"
                f"Sila teruskan pembayaran atau batalkan order semasa.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Continue Payment", callback_data=f"pay:{oid}")],
                    [InlineKeyboardButton("❌ Cancel Order",      callback_data=f"cancel_order:{oid}")],
                ]),
            )
            track_flow_message(context, active_msg, "active_order")
            return
    except Exception as exc:
        log.warning(f"Duplicate order check failed, proceeding: {_safe_error(exc)}")
        # Non-blocking — if check fails, allow order creation to continue

    order_id      = f"ORD{random.randint(10000, 99999)}{user.id}"
    price_to_use  = variant_price if variant_price is not None else p["price"]
    product_name  = f"{p['name']} — {variant_label}" if variant_label else p["name"]
    total         = round(price_to_use * qty, 2)
    print(f"[CREATE_ORDER] Inserting order {order_id} total=RM{total} product_name={product_name!r}")
    _variant_id = context.user_data.get("selected_variant_id") or None
    try:
        inserted_rows = await _run_supabase(
            f"orders.insert id={order_id}",
            lambda: sb_post("orders", {
                "id": order_id, "user_id": user.id, "username": user.username or "",
                "product_id": product_id, "product_name": product_name,
                "quantity": qty, "amount": total, "status": "pending",
                "variant_id": _variant_id,
            }),
            attempts=1,
        )
        # Use the real database row id returned from Supabase
        if inserted_rows and inserted_rows[0].get("id"):
            order_id = inserted_rows[0]["id"]
    except Exception as exc:
        context.user_data.pop(lock_user, None)
        log.warning(f"Supabase create_order insert: {_safe_error(exc)}")
        await delete_flow_messages(context, context.bot, chat_id, user.id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return

    log.info(f"Order created: {order_id} by {user.id}")
    context.user_data[f"qty_{product_id}"] = 1
    _order_title = await _setting('order_summary_title', '🧾 ORDER SUMMARY')
    _order_proceed = await _setting('order_proceed_msg', 'Sila teruskan ke pembayaran.')
    _variant_desc = context.user_data.get("selected_variant_desc") or ""
    summary_text = (
        f"{_order_title}\n─────────────────────\n"
        f"• Produk  : {product_name}\n"
        f"• Quantity: {qty}\n"
        f"• Harga   : RM {price_to_use}\n"
        f"• Total   : RM {total}\n"
    )
    if _variant_desc:
        summary_text += f"\n{_variant_desc}\n"
    summary_text += f"\n{_order_proceed}"
    await delete_flow_messages(context, context.bot, chat_id, user.id,
                               ["order_summary", "active_order", "product_detail", "variant_select", "error_message"])
    if update.callback_query:
        await safe_delete_message(context.bot, chat_id, update.callback_query.message.message_id)
    summary_msg = await context.bot.send_message(
        chat_id,
        summary_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Proceed to Payment", callback_data=f"pay:{order_id}")],
            [InlineKeyboardButton("❌ Cancel Order",        callback_data=f"cancel_order:{order_id}")],
        ]),
    )
    track_flow_message(context, summary_msg, "order_summary")
    context.user_data.pop(lock_user, None)
    log.info(f"[TIMING] create_order total_ms={int((time.monotonic()-_t_create)*1000)} product_id={product_id} order_id={order_id}")

# ─── Payment ──────────────────────────────────────────────────────────────────

async def _refresh_payment_settings():
    """Force-refresh payment/banner settings from Supabase, bypassing cache."""
    global _bot_settings
    keys = ["payment_qr_file_id", "payment_qr_url", "banner_file_id", "banner_url",
            "payment_title", "payment_instruction", "payment_button_instruction"]
    # Remove stale cached values so _setting() re-fetches from Supabase
    for k in keys:
        _bot_settings.pop(k, None)
    # Fetch fresh values and update cache
    try:
        rows = await asyncio.to_thread(
            lambda: sb_get("bot_settings", "select=key,value")
        )
        if rows:
            for r in rows:
                rk = r.get("key")
                if rk in keys:
                    _bot_settings[rk] = r.get("value") or ""
        _qr_url_val = _bot_settings.get("payment_qr_url", "")
        _qr_file_val = _bot_settings.get("payment_qr_file_id", "")
        log.info(f"[PAYMENT_SETTINGS] refreshed for tenant_id={TENANT_ID}")
        log.info(f"[PAYMENT_SETTINGS] payment_qr_file_id present={'yes' if _qr_file_val else 'no'}")
        log.info(f"[PAYMENT_SETTINGS] payment_qr_url present={'yes' if _qr_url_val else 'no'}")
        if _qr_url_val:
            log.info(f"[PAYMENT_SETTINGS] payment_qr_url value prefix={_qr_url_val[:60]!r}")
    except Exception as exc:
        log.warning(f"[PAYMENT_SETTINGS] refresh failed: {_safe_error(exc)}")


async def _get_tenant_qr() -> tuple[str, str]:
    """Get tenant-specific QR as (file_id, url). Always fetches fresh from Supabase."""
    file_id = ""
    url = ""
    try:
        rows = await asyncio.to_thread(
            lambda: sb_get("bot_settings", "select=key,value&key=in.(payment_qr_file_id,payment_qr_url)")
        )
        if rows:
            for r in rows:
                rk = r.get("key")
                rv = r.get("value") or ""
                if rk == "payment_qr_file_id":
                    file_id = rv
                elif rk == "payment_qr_url":
                    url = rv
        log.info(f"[QR_FETCH] tenant_id={TENANT_ID} file_id={'yes' if file_id else 'no'} url={'yes' if url else 'no'}")
        if url:
            log.info(f"[QR_FETCH] url prefix={url[:60]!r}")
    except Exception as exc:
        log.warning(f"[QR_FETCH] failed: {_safe_error(exc)}")
    return file_id, url


async def send_payment_page(context, chat_id: int, user_id: int, order: dict, order_id: str):
    """Shared payment page: sends QR + action buttons.
    Used by both new orders (Proceed to Payment) and active pending orders (Continue Payment).
    Does NOT send admin notification — caller decides."""
    # Force-fresh settings so QR changes appear immediately (not stale cache)
    await _refresh_payment_settings()
    _qr_file_id, _qr_url = await _get_tenant_qr()
    # Sync fresh QR values into cache so _setting() calls below use latest
    _bot_settings["payment_qr_file_id"] = _qr_file_id
    _bot_settings["payment_qr_url"] = _qr_url
    qr_sent = False
    _pay_title = await _setting('payment_title', '💳 PAYMENT DETAILS')
    _pay_instruction = await _setting('payment_instruction', 'Scan QR code below to pay 👇')

    log.info(f"[PAYMENT] send_payment_page order_id={order_id} user_id={user_id} "
             f"tenant_id={TENANT_ID} qr_file_id={'yes' if _qr_file_id else 'no'} "
             f"qr_url={'yes' if _qr_url else 'no'} order_status={order.get('status')}")

    caption = (
        f"{_pay_title}\n\n"
        f"Order ID: {order_id}\n"
        f"Amount: RM {order['amount']}\n\n"
        f"{_pay_instruction}"
    )

    if _qr_file_id:
        try:
            qr_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=_qr_file_id,
                caption=caption,
            )
            qr_sent = True
            track_flow_message(context, qr_msg, "payment_qr")
            log.info(f"[PAYMENT] QR sent via file_id order_id={order_id}")
        except Exception as exc:
            log.warning(f"[PAYMENT] file_id failed: {_safe_error(exc)}")
    if not qr_sent and _qr_url:
        try:
            qr_msg = await context.bot.send_photo(
                chat_id=chat_id,
                photo=_qr_url,
                caption=caption,
            )
            qr_sent = True
            track_flow_message(context, qr_msg, "payment_qr")
            log.info(f"[PAYMENT] QR sent via URL order_id={order_id}")
        except Exception as exc:
            log.warning(f"[PAYMENT] URL failed: {_safe_error(exc)}")
    if not qr_sent:
        try:
            qr_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"{_pay_title}\n\n"
                    f"Order ID: {order_id}\n"
                    f"Amount: RM {order['amount']}\n\n"
                    f"⚠️ Payment QR is not configured yet. Please contact the store owner."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_order:{order_id}")],
                ]),
            )
            track_flow_message(context, qr_msg, "payment_qr")
            log.warning(f"[PAYMENT] QR not configured for tenant")
        except Exception as exc:
            log.warning(f"[PAYMENT] text fallback failed: {_safe_error(exc)}", exc_info=True)
    else:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=await _setting("payment_button_instruction", "After payment, click the button below:"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ I Have Paid",  callback_data=f"paid:{order_id}")],
                    [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_order:{order_id}")],
                ]),
            )
        except Exception as exc:
            log.error(f"[PAYMENT] send action buttons failed: {_safe_error(exc)}")


async def show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    """Validate order and delegate to send_payment_page. Called for new and active orders."""
    _t_pay = time.monotonic()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        rows = await _run_supabase(
            f"orders.payment id={order_id}",
            lambda: sb_get("orders", f"select=id,user_id,amount,status,username,product_name&id=eq.{order_id}&limit=1"),
        )
        order = rows[0] if rows else None
        if not order:
            log.warning(f"[PAYMENT] order not found order_id={order_id} user_id={user_id}")
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⚠️ Order tidak dijumpai.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        if str(order.get("user_id")) != str(user_id) and user_id != ADMIN_ID:
            log.warning(f"[SECURITY] Blocked payment view non-owner user_id={user_id} order_id={order_id}")
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⛔ Order ini bukan milik anda.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        log.info(f"[PAYMENT] order validated order_id={order_id} user_id={user_id} status={order.get('status')} amount={order.get('amount')}")
    except Exception as exc:
        log.exception(f"[PAYMENT] Supabase fetch failed order_id={order_id} user_id={user_id}")
        await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Gagal muatkan maklumat pembayaran.", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return

    await send_payment_page(context, chat_id, user_id, order, order_id)
    log.info(f"[TIMING] show_payment total_ms={int((time.monotonic()-_t_pay)*1000)} order_id={order_id}")

# ─── Paid / Receipt ───────────────────────────────────────────────────────────

async def handle_paid(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        rows = await _run_supabase(
            f"orders.paid_validate id={order_id}",
            lambda: sb_get("orders", f"select=id,user_id,status&id=eq.{order_id}&limit=1"),
        )
        order = rows[0] if rows else None
        if not order:
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⚠️ Order tidak dijumpai.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        if str(order.get("user_id")) != str(user_id):
            log.warning(f"[SECURITY] Blocked paid action non-owner user_id={user_id} order_id={order_id}")
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⛔ Order ini bukan milik anda.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        status = str(order.get("status") or "")
        if status != "pending":
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(
                chat_id,
                f"⚠️ Order ini tidak boleh ditandakan sebagai dibayar kerana status semasa ialah: {status or '-'}",
                reply_markup=back_shop(),
            )
            track_flow_message(context, err_msg, "error_message")
            return
    except Exception as exc:
        log.exception(f"[PAID] Validation failed order_id={order_id} user_id={user_id}")
        await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Gagal semak order. Sila cuba lagi.", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return
    context.user_data["pending_receipt"] = order_id
    await delete_flow_messages(context, context.bot, chat_id, user_id, ["receipt_instruction", "error_message"])
    receipt_msg = await context.bot.send_message(
        chat_id,
        f"📸 Upload screenshot resit pembayaran untuk:\nOrder ID: {order_id}\n\nHantar gambar sekarang:"
    )
    track_flow_message(context, receipt_msg, "receipt_instruction")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _block_if_expired(update, context):
        return
    order_id = context.user_data.get("pending_receipt")
    if not order_id:
        return

    user    = update.effective_user
    file_id = update.message.photo[-1].file_id
    try:
        rows = await _run_supabase(
            f"orders.receipt_validate id={order_id}",
            lambda: sb_get("orders", f"select=*&id=eq.{order_id}&limit=1"),
        )
        order = rows[0] if rows else None
        if not order:
            context.user_data.pop("pending_receipt", None)
            await update.message.reply_text("⚠️ Order tidak dijumpai.")
            return
        if str(order.get("user_id")) != str(user.id):
            context.user_data.pop("pending_receipt", None)
            log.warning(f"[SECURITY] Blocked receipt upload non-owner user_id={user.id} order_id={order_id}")
            await update.message.reply_text("⛔ Order ini bukan milik anda.")
            return
        status = str(order.get("status") or "")
        if status != "pending":
            context.user_data.pop("pending_receipt", None)
            await update.message.reply_text(
                f"⚠️ Order ini tidak boleh dihantar resit kerana status semasa ialah: {status or '-'}"
            )
            return

        def save_receipt():
            sb_patch(
                "orders",
                f"id=eq.{order_id}&user_id=eq.{user.id}&status=eq.pending",
                {"receipt_file_id": file_id, "status": "waiting_approval"},
            )
            updated = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            return updated[0] if updated else {}

        order = await _run_supabase(f"orders.receipt id={order_id}", save_receipt)
    except Exception as exc:
        log.warning(f"Supabase receipt: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal simpan resit. Cuba lagi.")
        return

    context.user_data.pop("pending_receipt", None)
    _receipt_msg = await _setting('receipt_received_msg', '✅ Resit diterima!')
    await update.message.reply_text(
        f"{_receipt_msg}\nOrder ID: {order_id}\nAdmin akan sahkan pembayaran anda.",
        reply_markup=main_kb(),
    )
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID, photo=file_id,
            caption=(
                f"📸 RESIT BARU\n• Order: {order_id}\n"
                f"• User: @{user.username or user.id}\n"
                f"• Produk: {order.get('product_name','')}\n• RM {order['amount']}"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{order_id}"),
            ]]),
        )
    except Exception as exc:
        log.warning(f"Admin photo notify: {_safe_error(exc)}")

# ─── Cancel Order ─────────────────────────────────────────────────────────────

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not order_id:
        log.warning(f"[CANCEL] no order_id provided user_id={user_id}")
        return
    try:
        rows = await _run_supabase(
            f"orders.cancel_fetch id={order_id}",
            lambda: sb_get("orders", f"select=id,user_id,status&id=eq.{order_id}&limit=1"),
        )
        order = rows[0] if rows else None
        if not order:
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⚠️ Order tidak dijumpai.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        if str(order.get("user_id")) != str(user_id):
            log.warning(f"[SECURITY] Blocked cancel non-owner user_id={user_id} order_id={order_id}")
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⛔ Order ini bukan milik anda.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
        status = str(order.get("status") or "")
        if status != "pending":
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            info_msg = await context.bot.send_message(
                chat_id,
                f"✅ Order ini sudah {status}. Tiada tindakan diperlukan.",
                reply_markup=back_shop(),
            )
            track_flow_message(context, info_msg, "error_message")
            return

        # Acquire cancel lock to prevent double-cancel (5s window)
        if not _acquire_lock(context, user_id, order_id, "cancel"):
            log.info(f"[CANCEL] double-click blocked user_id={user_id} order_id={order_id}")
            return

        cancelled = False
        try:
            await _run_supabase(
                f"orders.cancel id={order_id}",
                lambda: sb_patch("orders", f"id=eq.{order_id}&user_id=eq.{user_id}&status=eq.pending", {"status": "cancelled"}),
            )
            cancelled = True
        except Exception as exc:
            log.exception(f"[CANCEL] Supabase patch failed order_id={order_id} user_id={user_id}")
        finally:
            _release_lock(context, user_id, order_id, "cancel")
        if not cancelled:
            await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
            err_msg = await context.bot.send_message(chat_id, "⚠️ Gagal batalkan order. Sila cuba lagi.", reply_markup=back_shop())
            track_flow_message(context, err_msg, "error_message")
            return
    except Exception as exc:
        log.exception(f"[CANCEL] unexpected error order_id={order_id} user_id={user_id}")
        await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
        err_msg = await context.bot.send_message(chat_id, "⚠️ Gagal batalkan order. Sila cuba lagi.", reply_markup=back_shop())
        track_flow_message(context, err_msg, "error_message")
        return

    await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
    cancel_msg = await context.bot.send_message(
        chat_id,
        f"✅ Order cancelled. You can place a new order now.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 Back to Shop", callback_data="shop")],
        ]),
    )
    track_flow_message(context, cancel_msg, "error_message")

# ─── My Orders ────────────────────────────────────────────────────────────────

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _block_if_expired(update, context):
        return
    user = update.effective_user

    try:
        orders = await _run_supabase(
            f"orders.user user={user.id}",
            lambda: sb_get("orders", f"select=*&user_id=eq.{user.id}&order=id.desc"),
        ) or []
    except Exception as exc:
        log.warning(f"Supabase my_orders: {_safe_error(exc)}", exc_info=True)
        msg = "⚠️ Gagal muatkan orders. Cuba lagi."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=back_home())
        else:
            await update.message.reply_text(msg, reply_markup=back_home())
        return

    EMOJI = {"pending": "⏳", "waiting_approval": "🔍", "completed": "✅", "cancelled": "❌", "rejected": "🚫"}
    if not orders:
        text = "📦 Anda belum ada sebarang order."
    else:
        text = "📦 MY ORDERS\n" + "─" * 25 + "\n"
        for o in orders[:10]:
            text += f"{EMOJI.get(o['status'],'❓')} {o['id']}\n   {o.get('product_name','')}\n   RM {o['amount']} — {o['status']}\n\n"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=back_home())
    else:
        await update.message.reply_text(text, reply_markup=back_home())

# ─── Admin: Approve / Reject ──────────────────────────────────────────────────

async def _approve_order_core(context: ContextTypes.DEFAULT_TYPE, order_id: str):
    try:
        def approve_tx():
            rows = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            order_data = rows[0] if rows else {}
            sb_patch("orders", f"id=eq.{order_id}", {"status": "completed"})
            product_data = {}
            cred = None
            if order_data.get("product_id"):
                prod_rows = sb_get("products", f"select=*&id=eq.{order_data['product_id']}&limit=1")
                if prod_rows:
                    product_data = prod_rows[0]
                    variant_id = order_data.get("variant_id") or None
                    qty = order_data.get("quantity", 1)
                    if variant_id:
                        # Variant order: reduce product_variants.stock only, not products.stock
                        var_rows = sb_get("product_variants", f"select=id,stock&id=eq.{variant_id}&limit=1")
                        if var_rows:
                            old_var_stock = var_rows[0].get("stock", 0)
                            new_var_stock = max(0, old_var_stock - qty)
                            sb_patch("product_variants", f"id=eq.{variant_id}", {"stock": new_var_stock})
                            log.info(f"[VARIANT STOCK] variant_id={variant_id}")
                            log.info(f"[VARIANT STOCK] old_stock={old_var_stock}")
                            log.info(f"[VARIANT STOCK] new_stock={new_var_stock}")
                    else:
                        # Normal product: reduce products.stock
                        new_stock = max(0, product_data.get("stock", 0) - qty)
                        sb_patch("products", f"id=eq.{order_data['product_id']}", {"stock": new_stock})
                    _products_cache_data["timestamp"] = 0  # force cache refresh after stock change
                    # Resolve delivery mode: prefer explicit delivery_mode field, fallback to auto_delivery bool
                    delivery_mode = product_data.get("delivery_mode") or ("auto" if product_data.get("auto_delivery") else "manual")
                    log.info(f"[AUTO DELIVERY] order_id={order_id}")
                    log.info(f"[AUTO DELIVERY] delivery_mode={delivery_mode}")
                    log.info(f"[AUTO DELIVERY] product_id={order_data.get('product_id')}")
                    log.info(f"[AUTO DELIVERY] variant_id={variant_id}")
                    if delivery_mode == "auto":
                        log.info(f"[AUTO DELIVERY] using column is_used")
                        if variant_id:
                            cred_rows = sb_admin_get(
                                "credentials",
                                f"select=id,email,password&variant_id=eq.{variant_id}&is_used=eq.false&order=id&limit=1",
                            )
                        else:
                            cred_rows = sb_admin_get(
                                "credentials",
                                f"select=id,email,password&product_id=eq.{order_data['product_id']}&variant_id=is.null&is_used=eq.false&order=id&limit=1",
                            )
                        log.info(f"[CREDENTIAL_DELIVERY] tenant_id={TENANT_ID} order_id={order_id} product_id={order_data.get('product_id')} variant_id={variant_id} credential_found={bool(cred_rows)}")
                        if cred_rows:
                            cred = cred_rows[0]
                        else:
                            log.warning(f"[AUTO DELIVERY] no unused credential found — falling back to manual delivery message")
            return order_data, product_data, cred

        result = await _run_supabase(f"orders.approve id={order_id}", approve_tx, attempts=1, timeout=15)
        order, product, cred = result if isinstance(result, tuple) else (result, {}, None)
    except Exception as exc:
        log.warning(f"Supabase approve: {_safe_error(exc)}", exc_info=True)
        raise

    _delivery_mode = product.get("delivery_mode") or ("auto" if product.get("auto_delivery") else "manual")
    log.info(f"Order {order_id} approved by admin (delivery_mode={_delivery_mode})")

    # ── Testimonial channel post ───────────────────────────────────────────────
    await _post_testimonial(context, order)

    # ── Loyalty points award ───────────────────────────────────────────────────
    try:
        _user_id   = order.get("user_id")
        _username  = order.get("username") or ""
        await _run_supabase(
            f"points.award user={_user_id}",
            lambda uid=_user_id, uname=_username: _award_points_sync(uid, uname),
        )
        log.info(f"[POINTS] 10 points awarded to user {_user_id} for order {order_id}")
    except Exception as exc:
        log.warning(f"[POINTS] Award failed (non-fatal): {_safe_error(exc)}")

    # ── Tenant-level feature flags ──────────────────────────────────────────────
    send_approved_msg = (await _setting("send_payment_approved_message", "true")).lower() == "true"
    enable_pts_msg = (await _setting("enable_points_message", "true")).lower() == "true"
    log.info(f"[APPROVAL_MESSAGE] tenant_id={TENANT_ID} send_payment_approved_message={send_approved_msg}")
    log.info(f"[POINTS_MESSAGE] tenant_id={TENANT_ID} enable_points_message={enable_pts_msg}")

    # ── AUTO DELIVERY path ─────────────────────────────────────────────────────
    if _delivery_mode == "auto":
        cred_sent = False
        if cred:
            log.info(f"[AUTO DELIVERY] credential selected id={cred['id']}")
            log.info(f"[AUTO DELIVERY] sending credential to user_id={order['user_id']}")
            try:
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=(
                        "✅ Pembayaran anda telah disahkan!\n\n"
                        "🎉 Berikut adalah maklumat akaun anda:\n\n"
                        f"📦 Produk: {order.get('product_name', '-')}\n"
                        f"📧 Email: {cred['email']}\n"
                        f"🔑 Password: {cred['password']}\n\n"
                        "⚠️ Simpan maklumat ini. Jangan kongsi dengan sesiapa.\n"
                        "💬 Ada masalah? Hubungi admin: @berryrc"
                    ),
                )
                cred_sent = True
                log.info(f"[AUTO DELIVERY] credential send success=True")
                # Mark is_used ONLY after successful send
                try:
                    await _run_supabase(
                        f"credentials.mark_used id={cred['id']}",
                        lambda cid=cred["id"]: sb_admin_patch("credentials", f"id=eq.{cid}", {"is_used": True}),
                    )
                    log.info(f"[AUTO DELIVERY] marked is_used=True")
                except Exception as exc:
                    log.warning(f"[AUTO DELIVERY] failed to mark is_used=True: {_safe_error(exc)}")
                # Mark order credentials_sent
                try:
                    await _run_supabase(
                        f"orders.mark_sent id={order_id}",
                        lambda oid=order_id: sb_patch("orders", f"id=eq.{oid}", {"credentials_sent": True}),
                    )
                except Exception as exc:
                    log.warning(f"[UNSENT] auto mark sent failed: {_safe_error(exc)}")
            except Exception as exc:
                log.warning(f"[AUTO DELIVERY] credential send success=False — {_safe_error(exc)}", exc_info=True)

        if cred_sent:
            # Credential delivered — skip manual message
            log.info(f"[AUTO DELIVERY] manual fallback sent=False")
            if enable_pts_msg:
                await _send_points_notification(context, order["user_id"])
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"✅ Auto delivery berjaya!\n"
                        f"• Order: {order_id}\n"
                        f"• Customer: @{order.get('username', '-')}\n"
                        f"• Produk: {order.get('product_name', '-')}\n"
                        f"• Credentials dihantar automatik ✅"
                    ),
                )
            except Exception as exc:
                log.warning(f"Auto delivery admin notify: {_safe_error(exc)}")
            return

        # Fallback: no cred found OR send failed
        log.info(f"[AUTO DELIVERY] manual fallback sent=True")
        fallback_variant_id = order.get("variant_id")
        if fallback_variant_id:
            log.warning(f"[CREDENTIAL_DELIVERY] No credentials assigned for variant_id={fallback_variant_id}")
        else:
            log.warning(f"[CREDENTIAL_DELIVERY] No credentials assigned for product_id={order.get('product_id')} with variant_id=null")
        if send_approved_msg:
            try:
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=(
                        "✅ Pembayaran anda telah disahkan!\n\n"
                        "Akaun akan dihantar secepat mungkin 🚀\n"
                        "(biasanya dalam masa 1 jam)\n\n"
                        "Ada masalah? DM admin: @berryrc 🙌"
                    ),
                )
            except Exception as exc:
                log.warning(f"Auto delivery fallback user notify: {_safe_error(exc)}")
        if enable_pts_msg:
            await _send_points_notification(context, order["user_id"])
        # Extra message for private/semi/crumbs slot products
        try:
            _pname = (order.get("product_name") or "").lower()
            if any(kw in _pname for kw in ("private", "semi", "crumbs")):
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=(
                        "📋 Untuk slot ini, sila PM admin @berryrc dengan maklumat berikut:\n\n"
                        "✦ 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗦𝗟𝗢𝗧 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗢𝗡𝗟𝗬 ✦\n"
                        "┆𑣲 name : \n"
                        "┆𑣲 pin 4 digit : \n"
                        "> pin for netflix only"
                    ),
                )
        except Exception as exc:
            log.warning(f"Extra slot message failed: {_safe_error(exc)}")
        try:
            variant_info = f"Variant: {fallback_variant_id} | " if fallback_variant_id else ""
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ STOK CREDENTIALS HABIS!\n"
                    f"Produk: {order.get('product_name', '-')} (ID: {order.get('product_id', '')})\n"
                    f"{variant_info}"
                    f"Tiada credentials tersedia.\n"
                    f"Tambah: /addcred {product.get('id', '')}\n"
                    f"Atau hantar manual: /send {order_id}"
                ),
            )
        except Exception as exc:
            log.warning(f"Auto delivery no-cred admin alert: {_safe_error(exc)}")
        return

    # ── MANUAL DELIVERY path (existing flow, unchanged) ────────────────────────
    if send_approved_msg:
        # Message 1 → Customer
        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=await _setting(
                    "delivery_msg",
                    "✅ Pembayaran anda telah disahkan!\n\n"
                    "✅ Payment dah confirm!\n\n"
                    "Akaun akan dihantar secepat mungkin 🚀\n"
                    "(biasanya laju je, tak lebih dari 1 jam 😉)\n\n"
                    "Kalau lebih 1 jam tak dapat apa-apa, jangan segan terus DM admin: @berryrc ya 🙌"
                ),
            )
        except Exception as exc:
            log.warning(f"Notify user approve: {_safe_error(exc)}")

    # Message 2 → Admin (copy-paste /send command)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"/send {order_id}",
        )
    except Exception as exc:
        log.warning(f"Notify admin send command: {_safe_error(exc)}")

    # Message 3 → Admin (account template to fill in)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"Order: {order_id}\n"
                f"Produk: {order.get('product_name', '-')}\n"
                f"Customer: @{order.get('username', '-')}\n\n"
                f"Email: \n"
                f"Password: "
            ),
        )
    except Exception as exc:
        log.warning(f"Notify admin template: {_safe_error(exc)}")

    return {"order": order, "delivery_mode": _delivery_mode}


async def _reject_order_core(context: ContextTypes.DEFAULT_TYPE, order_id: str):
    try:
        def reject_tx():
            rows = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            order_data = rows[0] if rows else {}
            sb_patch("orders", f"id=eq.{order_id}", {"status": "rejected"})
            return order_data
        order = await _run_supabase(f"orders.reject id={order_id}", reject_tx, attempts=1)
    except Exception as exc:
        log.warning(f"Supabase reject: {_safe_error(exc)}", exc_info=True)
        raise

    log.info(f"Order {order_id} rejected by admin")
    try:
        await context.bot.send_message(chat_id=order["user_id"],
            text=await _setting("reject_msg", "⚠️ Bayaran ditolak.\nHubungi support untuk bantuan."))
    except Exception as exc:
        log.warning(f"Notify user reject: {_safe_error(exc)}")
    return {"order": order}


async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.edit_message_caption(
            caption="⛔ Bukan admin.", reply_markup=None)
        return

    # ── Instant loading feedback ───────────────────────────────────────────────
    try:
        await update.callback_query.edit_message_caption(
            caption="⏳ Memproses...", reply_markup=None)
    except Exception:
        pass

    try:
        await _approve_order_core(context, order_id)
    except Exception:
        await update.callback_query.edit_message_caption(
            caption="⚠️ Ralat approve. Sila cuba lagi.", reply_markup=None)
        return
    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n✅ APPROVED", reply_markup=None)


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.edit_message_caption(
            caption="⛔ Bukan admin.", reply_markup=None)
        return

    # ── Instant loading feedback ───────────────────────────────────────────────
    try:
        await update.callback_query.edit_message_caption(
            caption="⏳ Memproses...", reply_markup=None)
    except Exception:
        pass

    try:
        await _reject_order_core(context, order_id)
    except Exception:
        await update.callback_query.edit_message_caption(
            caption="⚠️ Ralat reject. Sila cuba lagi.", reply_markup=None)
        return

    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n❌ REJECTED", reply_markup=None)

# ─── Referral / Support / Home ────────────────────────────────────────────────

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        me  = await context.bot.get_me()
        ref = f"https://t.me/{me.username}?start=ref_{user.id}"
        await update.callback_query.edit_message_text(
            f"👥 REFERRAL\n─────────────────────\nLink referral anda:\n{ref}\n\nKongsi dan dapatkan reward!",
            reply_markup=back_home())
    except Exception as exc:
        log.warning(f"show_referral error: {_safe_error(exc)}")
        try:
            await update.callback_query.edit_message_text(
                "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc",
                reply_markup=back_home())
        except Exception:
            pass


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _support_username = await _setting('support_username', '@berryrc')
    _support_hours = await _setting('support_hours', '9am – 11pm')
    await update.callback_query.edit_message_text(
        f"💬 SUPPORT\n─────────────────────\nHubungi admin:\n• Telegram: {_support_username}\n\nMasa operasi: {_support_hours}",
        reply_markup=back_home())


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    total_users = total_sold = 0

    try:
        def home_stats():
            users = sb_get("users", "select=id")
            sold  = sb_get("orders", "select=id&status=eq.completed")
            return len(users), len(sold)
        total_users, total_sold = await _run_supabase("home.stats", home_stats)
    except Exception as exc:
        log.warning(f"Supabase home: {_safe_error(exc)}")
    await update.callback_query.edit_message_text(
        f"👋 Hi {user.first_name}!\nWelcome to My Store.\n\n"
        f"👤 Account\n• ID: {user.id}\n• Username: @{user.username or 'tiada'}\n\n"
        f"📊 Store Stats\n• Total Users: {total_users}\n• Total Sold: {total_sold} pcs\n\n"
        f"Tekan butang di bawah untuk mula!",
        reply_markup=main_kb())

# ─── Admin Helper ─────────────────────────────────────────────────────────────

async def _admin_notify(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not ADMIN_ID:
        return
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as exc:
        log.warning(f"Admin notify: {_safe_error(exc)}")


def _censor_username(username: str | None) -> str:
    """Return censored username: first 2 chars + ****** + last char."""
    if not username:
        return "Customer"
    u = username.lstrip("@")
    if not u:
        return "Customer"
    if len(u) == 1:
        return u + "******"
    if len(u) == 2:
        return u[0] + "******" + u[1]
    return u[:2] + "******" + u[-1]


async def _post_testimonial(context, order: dict):
    """Auto-post a delivery testimonial to the Telegram channel when an order is completed."""
    order_id = order.get("id", "?")
    log.info(f"[TESTIMONIAL] Attempting to post for order {order_id}")
    try:
        censored     = _censor_username(order.get("username"))
        product_name = order.get("product_name") or "—"
        quantity     = order.get("quantity") or 1

        try:
            total_completed = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: len(sb_get("orders", "select=id&status=eq.completed"))
                ),
                timeout=10,
            )
        except Exception as exc:
            log.warning(f"Testimonial: could not fetch total completed count: {_safe_error(exc)}")
            total_completed = "?"

        text = (await _setting(
            "testimonial_template",
            "🎉 New successful order delivered!\n"
            "👤 Buyer: {buyer}\n"
            "📦 Product: {product}\n"
            "📋 Quantity: {qty}\n"
            "__________________\n"
            "🔥 Total sold: {total} units"
        )).format(
            buyer=censored,
            product=product_name,
            qty=quantity,
            total=total_completed,
        )

        await context.bot.send_message(chat_id=TESTIMONIALS_CHANNEL_ID, text=text)
        log.info(f"[TESTIMONIAL] Posted to channel 1 successfully")
        try:
            await context.bot.send_message(chat_id=TESTIMONIALS_CHANNEL_ID_2, text=text)
            log.info(f"[TESTIMONIAL] Posted to channel 2 successfully")
        except Exception as exc:
            log.warning(f"[TESTIMONIAL] Failed to post to channel 2: {_safe_error(exc)}")
    except Exception as exc:
        log.error(f"[TESTIMONIAL] Failed: {_safe_error(exc)}")


# ─── Loyalty Points ───────────────────────────────────────────────────────────

def _award_points_sync(user_id: int, username: str):
    """Add 10 points to user in the 'points' table (read-then-write)."""
    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).isoformat()
    rows = sb_admin_get("points", f"select=*&user_id=eq.{user_id}&limit=1")
    if rows:
        current = rows[0]
        new_points = (current.get("points") or 0) + 10
        if new_points >= 50:
            new_points = 0  # reset after redeem threshold reached
        sb_admin_patch("points", f"user_id=eq.{user_id}", {
            "username":     username or current.get("username", ""),
            "points":       new_points,
            "total_orders": (current.get("total_orders") or 0) + 1,
            "updated_at":   now,
        })
    else:
        sb_admin_post("points", {
            "user_id":      user_id,
            "username":     username or "",
            "points":       10,
            "total_orders": 1,
            "updated_at":   now,
        })


async def _send_points_notification(context, user_id: int):
    """Send a loyalty points summary to the customer right after delivery."""
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: sb_get("points", f"select=points&user_id=eq.{user_id}&limit=1")
            ),
            timeout=10,
        )
        pts = (rows[0].get("points") or 0) if rows else 0
    except Exception as exc:
        log.warning(f"[POINTS] Notification fetch failed for user {user_id}: {_safe_error(exc)}")
        return

    try:
        if pts >= 50:
            text = (
                f"⭐ You earned 10 points!\n"
                f"🎉 You have {pts} pts — enough for a FREE product!\n"
                f"💬 Contact admin to redeem your free product!"
            )
        else:
            filled = round(pts / 50 * 10)
            empty  = 10 - filled
            bar    = "█" * filled + "░" * empty
            text   = (
                f"⭐ You earned 10 points for this purchase!\n"
                f"📊 Total points: {pts} pts\n"
                f"🎁 Collect 50 points to redeem a FREE product!\n"
                f"Progress: [{bar}] {pts}/50 pts"
            )
        await context.bot.send_message(chat_id=user_id, text=text)
        log.info(f"[POINTS] Notification sent to user {user_id} ({pts} pts)")
    except Exception as exc:
        log.warning(f"[POINTS] Notification send failed for user {user_id}: {_safe_error(exc)}")


async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Customer checks their loyalty points balance."""
    user = update.effective_user
    try:
        rows = await _run_supabase(
            f"points.check user={user.id}",
            lambda: sb_get("points", f"select=*&user_id=eq.{user.id}&limit=1"),
        )
        if rows:
            pts   = rows[0].get("points") or 0
            total = rows[0].get("total_orders") or 0
        else:
            pts   = 0
            total = 0
    except Exception as exc:
        log.warning(f"[POINTS] Check failed for user {user.id}: {_safe_error(exc)}")
        await update.message.reply_text("⚠️ Could not fetch points. Try again later.")
        return

    free        = pts // 50
    remainder   = pts % 50
    next_reward = 50 - remainder if remainder else 0

    await update.message.reply_text(
        f"⭐ Your Points: {pts} pts\n"
        f"🛒 Total Orders: {total}\n"
        f"🎁 Free products available: {free} (every 50pts)\n"
        f"📊 Next reward in: {next_reward} pts"
    )

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
# Max 5 button presses per 3 seconds per user.

_rate_data: dict[int, list] = {}
_RATE_WINDOW = 3.0
_RATE_MAX    = 5

def _is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    stamps = [t for t in _rate_data.get(user_id, []) if now - t < _RATE_WINDOW]
    if len(stamps) >= _RATE_MAX:
        _rate_data[user_id] = stamps
        return True
    stamps.append(now)
    _rate_data[user_id] = stamps
    return False

# ─── Flow Message Cleanup ──────────────────────────────────────────────────
# Track and delete bot messages so the chat stays clean.
# Tags: shop_list, product_detail, variant_select, order_summary,
#        active_order, payment_qr, receipt_instruction, error_message

FLOW_TAGS = ["shop_list", "product_detail", "variant_select", "order_summary",
             "active_order", "payment_qr", "receipt_instruction", "error_message"]

def _flow_key():
    return "flow_messages"

async def safe_delete_message(bot, chat_id: int, message_id: int) -> bool:
    """Delete a message silently. Return True if deleted. Never crash."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as exc:
        log.info(f"[CLEANUP] delete_failed chat={chat_id} msg={message_id}: {_safe_error(exc)}")
        return False

def track_flow_message(context, message, tag: str):
    """Store message_id under tag in context.user_data for later cleanup."""
    if tag not in FLOW_TAGS:
        log.warning(f"[FLOW] unknown tag={tag}")
        return
    context.user_data.setdefault(_flow_key(), {})[tag] = message.message_id

async def delete_flow_messages(context, bot, chat_id: int, user_id: int = None, tags: list = None):
    """Delete tracked flow messages. If tags is None, delete all tracked."""
    flow = context.user_data.get(_flow_key(), {})
    if tags is None:
        tags = list(flow.keys())
    for tag in tags:
        msg_id = flow.pop(tag, None)
        if msg_id:
            ok = await safe_delete_message(bot, chat_id, msg_id)
            log.info(f"[CLEANUP] tag={tag} msg_id={msg_id} user_id={user_id or '?'} deleted={'yes' if ok else 'no'}")

def _lock_key(user_id, order_id, action):
    return f"lock:{user_id}:{order_id}:{action}"

def _acquire_lock(context, user_id, order_id, action, ttl=5.0):
    """Acquire a per-(user,order,action) lock. Returns True if acquired."""
    key = _lock_key(user_id, order_id, action)
    now = time.monotonic()
    existing = context.bot_data.get(key)
    if existing and now - existing < ttl:
        return False
    context.bot_data[key] = now
    return True

def _release_lock(context, user_id, order_id, action):
    """Release a per-(user,order,action) lock."""
    context.bot_data.pop(_lock_key(user_id, order_id, action), None)

# ─── Button Router ────────────────────────────────────────────────────────────

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    log.info(f"Button: {data} from {update.effective_user.id}")

    # ═══ Answer immediately to dismiss Telegram loading BEFORE any slow logic ═══
    try:
        await q.answer()
    except Exception:
        log.exception(f"[BUTTON] Failed to answer callback query data={data!r}")

    # ── Rate limit check — edit message since answer() already consumed alert ──
    if _is_rate_limited(update.effective_user.id):
        try:
            await q.edit_message_text("⏳ Terlalu laju! Sila tunggu sebentar.")
        except Exception:
            pass
        return

    # ── Expired check (does Supabase query — already answered above) ───────────
    if await _block_if_expired(update, context):
        return

    # ── Backward compatibility for old callback data patterns ────────────────
    # Normalize old formats to new colon-separated format
    if data == "continue_payment" or data.startswith("continue_payment:"):
        suffix = data.split(":", 1)[1] if ":" in data else ""
        data = f"pay:{suffix}"
        log.info(f"[COMPAT] normalized continue_payment → pay: order_id={suffix!r}")
    elif data.startswith("pay:"):
        pass  # already new format
    elif data.startswith("payment_"):
        suffix = data[len("payment_"):]
        data = f"pay:{suffix}"
        log.info(f"[COMPAT] normalized payment_ → pay: order_id={suffix!r}")
    elif data.startswith("cancel_order:"):
        pass  # already new format
    elif data == "cancel_order":
        data = "cancel_order:"
        log.info("[COMPAT] normalized cancel_order → cancel_order:")
    elif data.startswith("cancel:"):
        suffix = data.split(":", 1)[1] if ":" in data else ""
        data = f"cancel_order:{suffix}"
        log.info(f"[COMPAT] normalized cancel: → cancel_order: order_id={suffix!r}")
    elif data.startswith("cancel_"):
        suffix = data[len("cancel_"):]
        data = f"cancel_order:{suffix}"
        log.info(f"[COMPAT] normalized cancel_ → cancel_order: order_id={suffix!r}")
    elif data.startswith("paid_"):
        suffix = data[len("paid_"):]
        data = f"paid:{suffix}"
        log.info(f"[COMPAT] normalized paid_ → paid: order_id={suffix!r}")

    try:
        if   data == "home":               await show_home(update, context)
        elif data == "shop":               await show_shop(update, context)
        elif data == "myorders":           await my_orders(update, context)
        elif data == "referral":           await show_referral(update, context)
        elif data == "support":            await show_support(update, context)
        elif data == "qty_display":        pass

        elif data.startswith("product_"):
            await show_product(update, context, int(data.split("_")[1]))

        elif data.startswith("variant_"):
            _t_variant = time.monotonic()
            try:
                # callback_data format: "variant_{variant_db_id}"
                vid = int(data.split("_", 1)[1])

                # Cache-first read for responsiveness; create_order will live-revalidate before insert.
                _, cached_variants = await _get_cached_products_and_variants()
                v = next((item for item in (cached_variants or []) if str(item.get("id")) == str(vid)), None)
                if not v:
                    _vid = vid
                    v_rows = await _run_supabase(
                        f"product_variants.fetch id={vid}",
                        lambda: sb_get(
                            "product_variants",
                            f"select=id,product_id,variant_name,stock,price,description&id=eq.{_vid}&limit=1",
                        ),
                    )
                    v = v_rows[0] if v_rows else None
                if not v:
                    await q.edit_message_text("⚠️ Variant tidak ditemui.", reply_markup=back_shop())
                    return

                v_label = v.get("variant_name")
                v_price = v.get("price")
                pid     = int(v.get("product_id"))

                if not v_label or v_price is None:
                    log.warning(f"Variant id={vid} missing name or price: {v!r}")
                    await q.edit_message_text("⚠️ Ralat variant. Sila cuba lagi.", reply_markup=back_shop())
                    return

                # Store selected variant_id in user_data for any downstream use
                context.user_data["selected_variant_id"] = vid
                context.user_data["selected_variant_desc"] = v.get("description") or ""

                await create_order(update, context, pid, 1,
                                   variant_label=str(v_label), variant_price=float(v_price))
                log.info(f"[TIMING] variant_callback total_ms={int((time.monotonic()-_t_variant)*1000)} variant_id={vid} product_id={pid}")

            except (ValueError, IndexError) as exc:
                log.warning(f"variant callback parse error data={data!r}: {_safe_error(exc)}")
                await q.edit_message_text("⚠️ Ralat. Sila mulakan semula.", reply_markup=back_shop())
            except Exception as exc:
                log.error(f"variant handler error data={data!r}: {_safe_error(exc)}", exc_info=True)
                try:
                    await q.edit_message_text("⚠️ Ralat. Sila cuba lagi.", reply_markup=back_shop())
                except Exception:
                    pass

        elif data.startswith("qty_minus_"):
            parts = data.split("_")          # ['qty', 'minus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), -1)

        elif data.startswith("qty_plus_"):
            parts = data.split("_")          # ['qty', 'plus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), +1)

        elif data.startswith("buy_"):
            parts = data.split("_")
            await create_order(update, context, int(parts[1]), int(parts[2]))

        elif data.startswith("pay:"):
            order_id = data.split(":", 1)[1] if ":" in data else ""
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            log.info(f"[PAYMENT] callback data={data!r} user_id={user_id} tenant_id={TENANT_ID}")
            # If callback data has no order_id, look up user's active pending order
            if not order_id:
                log.info(f"[PAYMENT] no order_id in callback, looking up active pending for user={user_id}")
                try:
                    rows = await _run_supabase(
                        f"orders.active user={user_id}",
                        lambda: sb_get("orders", f"select=id&user_id=eq.{user_id}&status=eq.pending&limit=1"),
                    )
                    if rows and rows[0].get("id"):
                        order_id = rows[0]["id"]
                        log.info(f"[PAYMENT] found active order_id={order_id} for user={user_id}")
                    else:
                        await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
                        err_msg = await context.bot.send_message(chat_id, "⚠️ Tiada order aktif dijumpai.", reply_markup=back_shop())
                        track_flow_message(context, err_msg, "error_message")
                        return
                except Exception as exc:
                    log.exception(f"[PAYMENT] active order lookup failed user_id={user_id}")
                    await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
                    err_msg = await context.bot.send_message(chat_id, "⚠️ Gagal cari order aktif.", reply_markup=back_shop())
                    track_flow_message(context, err_msg, "error_message")
                    return
            # Duplicate click protection
            opened = context.user_data.setdefault('payment_opened', set())
            if order_id in opened:
                log.info(f"[PAYMENT] duplicate click blocked order_id={order_id} user_id={user_id}")
                try:
                    await context.bot.send_message(chat_id, "💳 Payment page already opened. Please check the messages above.")
                except Exception:
                    pass
                return
            opened.add(order_id)
            # Show payment page FIRST, then clean up old messages (so failure doesn't lose old content)
            log.info(f"[PAYMENT] calling show_payment order_id={order_id} user_id={user_id}")
            await show_payment(update, context, order_id)
            try:
                await delete_flow_messages(context, context.bot, chat_id, user_id,
                                           ["order_summary", "active_order", "error_message"])
                await safe_delete_message(context.bot, chat_id, q.message.message_id)
            except Exception as exc:
                log.warning(f"[PAYMENT] cleanup after show_payment: {_safe_error(exc)}")

        elif data.startswith("paid:"):
            order_id = data.split(":", 1)[1] if ":" in data else ""
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            log.info(f"[PAID] callback data={data!r} user_id={user_id} tenant_id={TENANT_ID}")
            # handle_paid validates & sends receipt instruction FIRST, then cleanup
            await handle_paid(update, context, order_id)
            try:
                await delete_flow_messages(context, context.bot, chat_id, user_id,
                                           ["payment_qr", "error_message"])
                await safe_delete_message(context.bot, chat_id, q.message.message_id)
            except Exception as exc:
                log.warning(f"[PAID] cleanup after handle_paid: {_safe_error(exc)}")

        elif data.startswith("cancel_order:"):
            order_id = data.split(":", 1)[1] if ":" in data else ""
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            log.info(f"[CANCEL] callback data={data!r} user_id={user_id} order_id={order_id!r}")
            # Fallback: if no order_id in callback, look up user's active pending order
            if not order_id:
                try:
                    rows = await _run_supabase(
                        f"orders.active_cancel user={user_id}",
                        lambda: sb_get("orders", f"select=id&user_id=eq.{user_id}&status=eq.pending&limit=1"),
                    )
                    if rows and rows[0].get("id"):
                        order_id = rows[0]["id"]
                        log.info(f"[CANCEL] found active order_id={order_id} for user={user_id}")
                except Exception as exc:
                    log.exception(f"[CANCEL] active order lookup failed user_id={user_id}")
            if not order_id:
                await delete_flow_messages(context, context.bot, chat_id, user_id, ["error_message"])
                err_msg = await context.bot.send_message(chat_id, "⚠️ Tiada order aktif untuk dibatalkan.", reply_markup=back_shop())
                track_flow_message(context, err_msg, "error_message")
                return
            # Cancel order FIRST, then clean up old messages (so failure doesn't lose old content)
            await cancel_order(update, context, order_id)
            try:
                await delete_flow_messages(context, context.bot, chat_id, user_id,
                                           ["order_summary", "active_order", "payment_qr",
                                            "receipt_instruction", "error_message"])
                await safe_delete_message(context.bot, chat_id, q.message.message_id)
            except Exception as exc:
                log.warning(f"[CANCEL] cleanup after cancel_order: {_safe_error(exc)}")

        elif data.startswith("approve_"):
            await approve_order(update, context, data[len("approve_"):])

        elif data.startswith("reject_"):
            await reject_order(update, context, data[len("reject_"):])

        else:
            log.warning(f"Unknown callback_data: {data!r}")
            try:
                await q.edit_message_text(
                    "⚠️ Butang tidak dikenali. Sila mulakan semula.",
                    reply_markup=back_home(),
                )
            except Exception:
                pass

    except Exception as exc:
        log.error(f"Button handler error [{data}]: {_safe_error(exc)}", exc_info=True)
        try:
            await delete_flow_messages(context, context.bot, update.effective_chat.id, update.effective_user.id, ["error_message"])
            err_msg = await q.message.reply_text(
                "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc"
            )
            track_flow_message(context, err_msg, "error_message")
        except Exception:
            pass

# ─── Admin: Send Account Details ─────────────────────────────────────────────

pending_send: dict[int, str] = {}        # {admin_user_id: order_id}
pending_addcred: dict[int, dict] = {}   # {admin_user_id: {product_id, product_name}}

async def send_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uses /send ORDER_ID then types account details to forward to buyer."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not allowed")
        return

    if not context.args:
        await update.message.reply_text("Usage: /send ORDER_ID")
        return

    order_id = context.args[0]
    try:
        rows = await _run_supabase(
            f"orders.send_fetch id={order_id}",
            lambda: sb_get("orders", f"select=user_id,product_name,status&id=eq.{order_id}&limit=1"),
        )
        if not rows:
            await update.message.reply_text(f"⚠️ Order {order_id} tidak dijumpai.")
            return
        order = rows[0]
    except Exception as exc:
        log.warning(f"Supabase /send fetch: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text(f"⚠️ Ralat ambil order. Cuba lagi.")
        return

    pending_send[ADMIN_ID] = {"order_id": order_id, "user_id": order["user_id"]}
    log.info(f"Admin /send initiated for order {order_id} → user {order['user_id']}")
    await update.message.reply_text(
        f"📦 Order: {order_id}\n"
        f"🛍 Product: {order.get('product_name', '')}\n\n"
        f"Send account details now (email & password):"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages: reply keyboard numbers, Home button, and admin account delivery."""
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    text    = (update.message.text or "").strip()
    log.info(f"[MESSAGE] received")
    log.info(f"[MESSAGE] text={text!r}")
    log.info(f"[MESSAGE] user_id={user_id}")
    log.info(f"[MESSAGE] chat_id={update.effective_chat.id}")

    # ── Reply keyboard: "🏠 Home" button ──────────────────────────────────────
    if text == "🏠 Home":
        await update.message.reply_text(
            f"👋 Hi {update.effective_user.first_name}!\nWelcome to Berry Store.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "Pilih menu di bawah:",
            reply_markup=main_kb(),
        )
        return

    # ── Reply keyboard: number selects a product ───────────────────────────────
    if text.isdigit():
        _t_num = time.monotonic()
        products = context.user_data.get("shop_products") or []
        if products:
            idx = int(text) - 1
            if 0 <= idx < len(products):
                product_id = products[idx]["id"]
                log.info(f"Keyboard product select: user={user_id} number={text} product_id={product_id}")
                if not await _check_membership(context.bot, user_id):
                    await update.message.reply_text(
                        "🔒 To continue, please join our channel first:\n"
                        f"• {REQUIRED_CHANNEL}\n\n"
                        "After joining, send /start again.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📢 Join Channel", url=REQUIRED_CHANNEL_URL)],
                        ]),
                    )
                    return
                await show_product(update, context, product_id)
                log.info(f"[TIMING] handle_message number_select_ms={int((time.monotonic()-_t_num)*1000)} user_id={user_id} product_id={product_id}")
                return
            else:
                await update.message.reply_text(
                    f"⚠️ Nombor '{text}' tidak wujud. Pilih 1–{len(products)}.",
                )
                return

    # ── Admin: pending_receipt (customer uploading receipt text — not used but kept) ─

    # ── Admin: addcred flow — receive credential lines ─────────────────────────
    if user_id == ADMIN_ID and ADMIN_ID in pending_addcred:
        info = pending_addcred[ADMIN_ID]

        # Step 1: Admin picking a variant
        if info.get("step") == "pick_variant":
            try:
                chosen_id = int(text.strip())
            except ValueError:
                await update.message.reply_text("⚠️ Sila balas dengan nombor ID variant sahaja.")
                return
            variant_rows = info.get("variants") or []
            chosen = next((v for v in variant_rows if v["id"] == chosen_id), None)
            if not chosen:
                await update.message.reply_text("⚠️ ID variant tidak dijumpai. Cuba semula.")
                return
            pending_addcred[ADMIN_ID] = {
                "product_id": info["product_id"],
                "product_name": info["product_name"],
                "variant_id": chosen_id,
                "variant_name": chosen["variant_name"],
                "step": "enter_creds",
            }
            await update.message.reply_text(
                f"✅ Variant: {chosen['variant_name']}\n\n"
                f"Hantar credentials sekarang, satu per baris:\n"
                f"email:password\n\n"
                f"Contoh:\nuser@gmail.com:pass123",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        # Step 2: Admin entering credentials
        pending_addcred.pop(ADMIN_ID)
        product_id   = info["product_id"]
        product_name = info["product_name"]
        variant_id   = info.get("variant_id") or None
        variant_name = info.get("variant_name") or ""

        lines = [l.strip() for l in text.split("\n") if ":" in l.strip()]
        if not lines:
            await update.message.reply_text("⚠️ Format salah. Guna email:password")
            return
        items = []
        for line in lines:
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                items.append({
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "email":      parts[0].strip(),
                    "password":   parts[1].strip(),
                    "is_used":    False,
                })
        if not items:
            await update.message.reply_text("⚠️ Tiada credentials valid.")
            return
        try:
            def insert_creds(items=items):
                for item in items:
                    sb_admin_post("credentials", item)
            await _run_supabase(f"credentials.insert product={product_id}", insert_creds)
            label = f"{product_name} — {variant_name}" if variant_name else product_name
            await update.message.reply_text(
                f"✅ {len(items)} credentials berjaya ditambah untuk {label}"
            )
        except Exception as exc:
            await update.message.reply_text(f"❌ Gagal simpan: {_safe_error(exc)}")
        return

    # ── Admin: account delivery flow ──────────────────────────────────────────
    if user_id != ADMIN_ID or ADMIN_ID not in pending_send:
        return

    info     = pending_send.pop(ADMIN_ID)
    order_id = info["order_id"]
    buyer_id = info["user_id"]
    details  = update.message.text

    # Fetch product duration from order → product
    duration = "-"
    try:
        def duration_lookup():
            o_rows = sb_get("orders", f"select=product_id&id=eq.{order_id}&limit=1")
            if not o_rows or not o_rows[0].get("product_id"):
                return "-"
            p_rows = sb_get("products", f"select=duration&id=eq.{o_rows[0]['product_id']}&limit=1")
            return p_rows[0].get("duration") or "-" if p_rows else "-"
        duration = await _run_supabase(f"orders.duration id={order_id}", duration_lookup)
    except Exception as exc:
        log.warning(f"Could not fetch duration for order {order_id}: {_safe_error(exc)}")

    try:
        await context.bot.send_message(
            chat_id=buyer_id,
            text=(
                f"🎉 Akaun anda sudah sedia!\n"
                f"Order ID: {order_id}\n\n"
                f"{details}\n\n"
                f"⚠️ Simpan maklumat ini. Jangan kongsi dengan sesiapa.\n"
                f"📌 Tempoh: {duration}\n"
                f"💬 Ada masalah? Hubungi: @berryrc"
            ),
        )
        await update.message.reply_text(f"✅ Maklumat akaun berjaya dihantar kepada pembeli (Order: {order_id})")
        try:
            await _run_supabase(
                f"orders.mark_sent id={order_id}",
                lambda: sb_patch("orders", f"id=eq.{order_id}", {"credentials_sent": True}),
            )
        except Exception as exc:
            log.warning(f"[UNSENT] mark sent failed: {_safe_error(exc)}")
        log.info(f"Account details sent for order {order_id} → buyer {buyer_id}")
        # Points notification → customer
        await _send_points_notification(context, buyer_id)
    except Exception as exc:
        log.warning(f"Send account details error: {_safe_error(exc)}")
        await update.message.reply_text(f"⚠️ Gagal hantar kepada pembeli: {_safe_error(exc)}")


# ─── /stock ───────────────────────────────────────────────────────────────────

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    try:
        products = await _run_supabase(
            "products.stock_list",
            lambda: sb_get("products", "select=id,name,stock&order=id"),
        ) or []
    except Exception as exc:
        log.warning(f"stock fetch error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal muatkan produk. Cuba lagi.")
        return

    # No args → show product list with IDs
    if not context.args:
        if not products:
            await update.message.reply_text("⚠️ Tiada produk dalam database.")
            return
        lines = ["📦 SENARAI PRODUK & STOK", "─────────────────────"]
        for p in products:
            lines.append(f"ID {p['id']}  |  {p['name']}  |  Stok: {p['stock']}")
        lines.append("─────────────────────")
        lines.append("Guna: /stock <id> <kuantiti>")
        lines.append("Contoh: /stock 1 50")
        await update.message.reply_text("\n".join(lines))
        return

    # Validate args: /stock <product_id> <quantity>
    if len(context.args) != 2:
        await update.message.reply_text("⚠️ Format salah.\nGuna: /stock <id> <kuantiti>\nContoh: /stock 1 50")
        return

    try:
        product_id = int(context.args[0])
        new_stock  = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ ID dan kuantiti mesti nombor.\nContoh: /stock 1 50")
        return

    if new_stock < 0:
        await update.message.reply_text("⚠️ Stok tidak boleh negatif.")
        return

    # Find product name for confirmation message
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        await update.message.reply_text(f"⚠️ Produk ID {product_id} tidak dijumpai.\nGuna /stock untuk tengok senarai.")
        return

    try:
        await _run_supabase(
            f"products.stock_update id={product_id}",
            lambda: sb_patch("products", f"id=eq.{product_id}", {"stock": new_stock}),
        )
        refreshed = [{**p, "stock": new_stock} if p["id"] == product_id else p for p in products]
        _cache_products(refreshed)
        _products_cache_data["timestamp"] = 0  # force cache refresh after stock change
    except Exception as exc:
        log.warning(f"stock update error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal update stok. Cuba lagi.")
        return

    log.info(f"Stock updated: product {product_id} → {new_stock} by admin")
    await update.message.reply_text(
        f"✅ Stok berjaya dikemaskini!\n\n"
        f"Produk : {product['name']}\n"
        f"Stok lama: {product['stock']}\n"
        f"Stok baru: {new_stock}"
    )

# ─── /broadcast ───────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    message = " ".join(context.args).strip() if context.args else ""
    if not message:
        await update.message.reply_text(
            "⚠️ Sila masukkan mesej.\n\nContoh:\n/broadcast Produk baru dah ada! Check /start sekarang 🔥"
        )
        return

    try:
        users = await _run_supabase(
            "broadcast.users",
            lambda: sb_get("users", "select=id"),
        ) or []
    except Exception as exc:
        log.warning(f"broadcast fetch users error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal ambil senarai pengguna. Cuba lagi.")
        return

    if not users:
        await update.message.reply_text("⚠️ Tiada pengguna dalam database.")
        return

    sent = failed = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["id"], text=message)
            sent += 1
        except Exception as exc:
            log.warning(f"broadcast failed for user {u['id']}: {_safe_error(exc)}")
            failed += 1

    log.info(f"Broadcast done: {sent} sent, {failed} failed")
    await update.message.reply_text(
        f"📢 Broadcast selesai!\n\n"
        f"✅ Berjaya dihantar : {sent} pengguna\n"
        f"❌ Gagal            : {failed} pengguna"
    )

# ─── /testchannel ─────────────────────────────────────────────────────────────

async def cmd_testchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    try:
        await context.bot.send_message(
            chat_id=TESTIMONIALS_CHANNEL_ID,
            text="✅ Test message from Berry Store Bot",
        )
        log.info(f"[TESTCHANNEL] Success — message posted to {TESTIMONIALS_CHANNEL_ID}")
        await update.message.reply_text(f"✅ Test message sent to channel {TESTIMONIALS_CHANNEL_ID}")
    except Exception as exc:
        log.error(f"[TESTCHANNEL] Failed — {_safe_error(exc)}")
        await update.message.reply_text(f"❌ Failed to post to channel:\n{_safe_error(exc)}")

# ─── /adminorders ─────────────────────────────────────────────────────────────

async def cmd_adminorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    try:
        orders = await _run_supabase(
            "admin.orders_pending",
            lambda: sb_get("orders", "select=id,user_id,username,product_name,amount,status&status=in.(pending,waiting_approval)&order=id.desc&limit=10"),
        ) or []
    except Exception as exc:
        log.warning(f"adminorders error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal muatkan orders. Cuba lagi.")
        return

    if not orders:
        await update.message.reply_text("✅ Tiada order yang menunggu tindakan.")
        return

    STATUS_LABEL = {
        "pending":          "⏳ Belum bayar",
        "waiting_approval": "🔍 Tunggu approve",
    }

    lines = ["📋 PENDING ORDERS", "─────────────────────"]
    for o in orders:
        label = STATUS_LABEL.get(o["status"], o["status"])
        lines.append(
            f"{label}\n"
            f"  Order  : {o['id']}\n"
            f"  Produk : {o.get('product_name', '-')}\n"
            f"  Customer: @{o.get('username', '-')}\n"
            f"  RM {o['amount']}\n"
        )

    lines.append("─────────────────────")
    lines.append(f"Total: {len(orders)} order")

    await update.message.reply_text("\n".join(lines))

# ─── /ping ────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.info(f"[PING] received")
    log.info(f"[PING] user_id={update.effective_user.id}")
    log.info(f"[PING] chat_id={update.effective_chat.id}")
    await update.message.reply_text("pong")

# ─── /admin Dashboard ─────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    try:
        all_orders_result = await _run_supabase(
            "admin.orders_summary",
            lambda: sb_get("orders", "select=status,amount"),
        )
        products_result = await _run_supabase(
            "admin.products_summary",
            lambda: sb_get("products", "select=name,stock,price"),
        )
        users_result = await _run_supabase(
            "admin.users_summary",
            lambda: sb_get("users", "select=id"),
        )

        all_orders     = all_orders_result or []
        products       = products_result or []
        total_users    = len(users_result or [])

        pending        = [o for o in all_orders if o["status"] == "pending"]
        waiting        = [o for o in all_orders if o["status"] == "waiting_approval"]
        completed      = [o for o in all_orders if o["status"] == "completed"]
        total_revenue  = sum(float(o["amount"]) for o in completed)
        low_stock      = [p for p in products if p.get("stock", 0) <= 3]

    except Exception as exc:
        log.warning(f"Admin dashboard error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text(f"⚠️ Gagal muatkan data: {_safe_error(exc)}")
        return

    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%d/%m/%Y %H:%M")

    lines = [
        f"🛠 ADMIN DASHBOARD",
        f"📅 {now}",
        f"─────────────────────",
        f"👤 Total Users   : {total_users}",
        f"📦 Total Orders  : {len(all_orders)}",
        f"✅ Completed     : {len(completed)}",
        f"🔍 Pending Resit : {len(waiting)}",
        f"⏳ Pending Pay   : {len(pending)}",
        f"💰 Total Revenue : RM {total_revenue:.2f}",
        f"─────────────────────",
    ]

    if low_stock:
        lines.append("⚠️ LOW STOCK (≤3 unit):")
        for p in low_stock:
            lines.append(f"  • {p['name']} — {p['stock']} unit")
    else:
        lines.append("✅ Semua stok mencukupi")

    await update.message.reply_text("\n".join(lines))

# ─── Global Error Handler ─────────────────────────────────────────────────────

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("[TELEGRAM_ERROR] update=%s error=%s", update, context.error)
    if isinstance(context.error, Conflict):
        log.error("[POLLING_ERROR] Conflict: Another bot instance is using the same token.")
        return
    if isinstance(context.error, InvalidToken):
        log.error("[POLLING_ERROR] InvalidToken: Telegram token rejected by API.")
        return

# ─── /addcred ─────────────────────────────────────────────────────────────────

async def cmd_addcred(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /addcred PRODUCT_ID — then send email:password lines."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not allowed")
        return
    if await _block_if_expired(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /addcred PRODUCT_ID\n"
            "Example: /addcred 3\n\n"
            "Then send credentials one per line:\n"
            "email@example.com:mypassword"
        )
        return
    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Product ID mestilah nombor.")
        return
    try:
        rows = await _run_supabase(
            f"products.addcred id={product_id}",
            lambda: sb_get("products", f"select=id,name&id=eq.{product_id}&limit=1"),
        )
        if not rows:
            await update.message.reply_text(f"⚠️ Produk ID {product_id} tidak dijumpai.")
            return
        product_name = rows[0]["name"]
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Ralat: {_safe_error(exc)}")
        return
    # Fetch variants for this product
    try:
        variant_rows = await _run_supabase(
            f"variants.addcred pid={product_id}",
            lambda: sb_get("product_variants", f"select=id,variant_name&product_id=eq.{product_id}&order=id"),
        ) or []
    except Exception:
        variant_rows = []

    if variant_rows:
        # Store variants in pending and ask admin to pick one
        pending_addcred[ADMIN_ID] = {
            "product_id": product_id,
            "product_name": product_name,
            "variants": variant_rows,
            "step": "pick_variant",
        }
        lines = [f"📦 Produk: {product_name}", "", "Pilih variant:"]
        for v in variant_rows:
            lines.append(f"{v['id']}. {v['variant_name']}")
        lines.append("")
        lines.append("Balas dengan nombor ID variant. Contoh: 1")
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        pending_addcred[ADMIN_ID] = {
            "product_id": product_id,
            "product_name": product_name,
            "step": "enter_creds",
        }
        await update.message.reply_text(
            f"📦 Produk: {product_name} (ID: {product_id})\n\n"
            f"Hantar credentials sekarang, satu per baris:\n"
            f"email:password\n\n"
            f"Contoh:\nuser@gmail.com:pass123"
        )


# ─── /credstock ───────────────────────────────────────────────────────────────

async def cmd_credstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: show count of unused credentials per product."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not allowed")
        return
    if await _block_if_expired(update, context):
        return
    try:
        products = await _run_supabase(
            "products.credstock",
            lambda: sb_get("products", "select=id,name,auto_delivery&order=name"),
        ) or []
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Ralat: {_safe_error(exc)}")
        return
    if not products:
        await update.message.reply_text("Tiada produk dijumpai.")
        return
    lines = ["📦 STOK CREDENTIALS:", "━━━━━━━━━━━━━━━━━━"]
    for p in products:
        try:
            pid = p["id"]
            cred_rows = await _run_supabase(
                f"credentials.count pid={pid}",
                lambda pid=pid: sb_get("credentials", f"select=id&product_id=eq.{pid}&is_used=eq.false"),
            ) or []
            count = len(cred_rows)
        except Exception:
            count = "?"
        auto_tag = " 🤖" if p.get("auto_delivery") else ""
        if isinstance(count, int) and count > 0:
            status = f"{count} ✅"
        elif count == 0:
            status = "0 ⚠️ HABIS"
        else:
            status = f"{count} ❓"
        lines.append(f"• {p['name']}{auto_tag}: {status}")
    lines.append("━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines))


# ─── /credcheck ───────────────────────────────────────────────────────────────

async def cmd_credcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /credcheck PRODUCT_ID — show unused credentials for a product."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not allowed")
        return
    if await _block_if_expired(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /credcheck PRODUCT_ID\n"
            "Example: /credcheck 3\n\n"
            "Tunjukkan senarai credentials yang belum digunakan untuk produk tersebut."
        )
        return
    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Product ID mestilah nombor.")
        return
    try:
        prod_rows = await _run_supabase(
            f"products.credcheck id={product_id}",
            lambda: sb_admin_get("products", f"select=id,name,auto_delivery&id=eq.{product_id}&limit=1"),
        )
        if not prod_rows:
            await update.message.reply_text(f"⚠️ Produk ID {product_id} tidak dijumpai.")
            return
        product = prod_rows[0]

        unused_rows = await _run_supabase(
            f"credentials.unused pid={product_id}",
            lambda: sb_admin_get("credentials", f"select=id,email,password&product_id=eq.{product_id}&is_used=eq.false&order=id"),
        ) or []

        used_count_rows = await _run_supabase(
            f"credentials.used_count pid={product_id}",
            lambda: sb_admin_get("credentials", f"select=id&product_id=eq.{product_id}&is_used=eq.true"),
        ) or []

    except Exception as exc:
        await update.message.reply_text(f"⚠️ Ralat: {_safe_error(exc)}")
        return

    unused = len(unused_rows)
    used   = len(used_count_rows)
    total  = unused + used
    auto_tag = " 🤖 Auto Delivery" if product.get("auto_delivery") else ""

    lines = [
        f"🔍 CREDENTIAL CHECK",
        f"━━━━━━━━━━━━━━━━━━",
        f"📦 Produk: {product['name']}{auto_tag}",
        f"📊 Total: {total} | ✅ Belum guna: {unused} | ❌ Dah guna: {used}",
        f"━━━━━━━━━━━━━━━━━━",
    ]

    if unused_rows:
        lines.append("📋 Senarai credentials tersedia:")
        for i, cred in enumerate(unused_rows, 1):
            pw = cred["password"]
            masked_pw = pw[:2] + "*" * max(0, len(pw) - 4) + pw[-2:] if len(pw) > 4 else "****"
            lines.append(f"{i}. {cred['email']} | {masked_pw}")
    else:
        lines.append("⚠️ Tiada credentials tersedia! Tambah dengan /addcred " + str(product_id))

    await update.message.reply_text("\n".join(lines))


async def cmd_unsent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    try:
        orders = await _run_supabase(
            "orders.unsent",
            lambda: sb_get(
                "orders",
                "select=id,username,product_name,amount,status&status=eq.completed&credentials_sent=eq.false&order=id.desc&limit=20"
            ),
        ) or []
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Ralat: {_safe_error(exc)}")
        return

    if not orders:
        await update.message.reply_text("✅ Tiada order pending.")
        return

    STATUS_EMOJI = {
        "completed": "✅",
        "waiting_approval": "🔍",
    }

    lines = ["📋 SENARAI ORDER TERKINI", "━━━━━━━━━━━━━━━━━━"]
    for o in orders:
        emoji = STATUS_EMOJI.get(o["status"], "❓")
        lines.append(
            f"{emoji} {o['id']}\n"
            f"   👤 @{o.get('username') or 'tiada'}\n"
            f"   📦 {o.get('product_name') or '-'}\n"
            f"   💰 RM {o.get('amount') or '-'}\n"
            f"   📌 {o.get('status') or '-'}\n"
            f"   👉 /send {o['id']}\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"Total: {len(orders)} order")

    await update.message.reply_text("\n".join(lines))


async def _auto_cancel_expired_orders(context: ContextTypes.DEFAULT_TYPE):
    """Background job: cancel PENDING orders older than 24 hours.
    Stock is only reduced on admin approval, so no stock adjustment needed here.
    Statuses 'waiting', 'completed', 'rejected', 'cancelled' are never touched.
    """
    log.info("[AUTO-CANCEL] Auto-cancel check started")
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        expired = await _run_supabase(
            "orders.expired_pending",
            lambda: sb_get("orders", f"select=id,product_name&status=eq.pending&created_at=lt.{cutoff}"),
        ) or []
        log.info(f"[AUTO-CANCEL] Found {len(expired)} expired pending orders")
        if not expired:
            log.info("[AUTO-CANCEL] Auto-cancel check completed")
            return
        cancelled_lines = []
        for order in expired:
            oid = order.get("id", "?")
            pname = order.get("product_name", "-")
            try:
                await _run_supabase(
                    f"orders.auto_cancel id={oid}",
                    lambda _oid=oid: sb_patch(
                        "orders",
                        f"id=eq.{_oid}&status=eq.pending",
                        {"status": "cancelled"},
                    ),
                    attempts=2,
                )
                log.info(f"[AUTO-CANCEL] Cancelled order {oid} product={pname}")
                cancelled_lines.append(f"• {oid} — {pname}")
            except Exception as exc:
                log.warning(f"[AUTO-CANCEL] Failed to cancel order {oid}: {_safe_error(exc)}")

        # Admin notification (optional — only sent if at least one order was cancelled)
        if cancelled_lines and ADMIN_ID:
            try:
                summary = "\n".join(cancelled_lines)
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🗑️ Auto-Cancel Report\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{len(cancelled_lines)} pending order(s) expired (>24h) and were auto-cancelled:\n\n"
                        f"{summary}\n\n"
                        f"ℹ️ Only unpaid pending orders are affected.\n"
                        f"Waiting/completed orders were NOT touched."
                    ),
                )
                log.info(f"[AUTO-CANCEL] Admin notified — {len(cancelled_lines)} order(s) cancelled")
            except Exception as exc:
                log.warning(f"[AUTO-CANCEL] Admin notify failed: {_safe_error(exc)}")

    except Exception as exc:
        log.warning(f"[AUTO-CANCEL] Check failed: {_safe_error(exc)}", exc_info=True)
    log.info("[AUTO-CANCEL] Auto-cancel check completed")


def _to_float_amount(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _fetch_completed_orders_for_period(start_utc: datetime, end_utc: datetime) -> list:
    select_cols = "id,product_name,amount,completed_at,created_at,order_date"
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = ("completed_at", "created_at", "order_date")

    for date_col in candidates:
        try:
            return await _run_supabase(
                f"orders.daily_report.{date_col}",
                lambda _col=date_col: sb_get(
                    "orders",
                    (
                        f"select={select_cols}"
                        f"&status=eq.completed"
                        f"&{_col}=gte.{start_iso}"
                        f"&{_col}=lte.{end_iso}"
                        "&limit=10000"
                    ),
                ),
            ) or []
        except Exception as exc:
            # Some tables may not have completed_at/order_date, so fallback safely.
            log.warning(f"[SALES REPORT] Query fallback for {date_col}: {_safe_error(exc)}")
    return []


def _build_sales_report_text(report_date: datetime, orders: list) -> str:
    total_sales = 0.0
    by_product: dict[str, dict[str, float | int]] = {}

    for order in orders:
        product_name = (order or {}).get("product_name") or "Unknown"
        amount = _to_float_amount((order or {}).get("amount"))
        total_sales += amount

        row = by_product.setdefault(product_name, {"amount": 0.0, "orders": 0})
        row["amount"] = float(row["amount"]) + amount
        row["orders"] = int(row["orders"]) + 1

    top_products = sorted(
        by_product.items(),
        key=lambda item: (-float(item[1]["amount"]), -int(item[1]["orders"]), item[0].lower()),
    )[:3]

    lines = [
        "📊 Daily Sales Report",
        f"Date: {report_date.strftime('%d/%m/%Y')}",
        "━━━━━━━━━━━━━━━━━━",
        f"Total Orders Completed: {len(orders)}",
        f"Total Sales: RM {total_sales:.2f}",
        "",
        "Top Products:",
    ]

    if top_products:
        for idx, (name, stats) in enumerate(top_products, 1):
            lines.append(
                f"{idx}. {name} — RM {float(stats['amount']):.2f} / {int(stats['orders'])} orders"
            )
    else:
        lines.append("No completed orders.")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "This report is sent to admin only.",
        ]
    )
    return "\n".join(lines)


async def _send_daily_sales_report(context: ContextTypes.DEFAULT_TYPE, *, use_today: bool = False):
    if not ADMIN_ID:
        log.warning("[SALES REPORT] ADMIN_ID missing. Skipping report.")
        return

    tz = ZoneInfo("Asia/Kuala_Lumpur")
    now_local = datetime.now(tz)
    target_day = now_local.date() if use_today else (now_local - timedelta(days=1)).date()
    start_local = datetime.combine(target_day, dt_time(0, 0, 0), tzinfo=tz)
    end_local = datetime.combine(target_day, dt_time(23, 59, 59), tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    orders = await _fetch_completed_orders_for_period(start_utc, end_utc)
    text = _build_sales_report_text(start_local, orders)

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)
        log.info("[SALES REPORT] Report sent to admin")
    except Exception as exc:
        log.warning(f"[SALES REPORT] Failed to send report: {_safe_error(exc)}")


async def cmd_salesreport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if await _block_if_expired(update, context):
        return

    await _send_daily_sales_report(context)


async def cmd_clearpending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /clearpending USER_ID — cancel all pending orders for a user."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if not TENANT_ID:
        await update.message.reply_text("❌ TENANT_ID not configured.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /clearpending USER_ID")
        return
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID must be a number.")
        return
    try:
        rows = await asyncio.to_thread(
            lambda: sb_admin_get(
                "orders",
                f"select=id,status&user_id=eq.{target_user_id}&status=eq.pending&tenant_id=eq.{TENANT_ID}",
            )
        )
        if not rows:
            await update.message.reply_text(f"✅ No pending orders found for user {target_user_id}.")
            return
        pending_ids = [r["id"] for r in rows if r.get("id")]
        count = len(pending_ids)
        await asyncio.to_thread(
            lambda: sb_admin_patch(
                "orders",
                f"user_id=eq.{target_user_id}&status=eq.pending&tenant_id=eq.{TENANT_ID}",
                {"status": "cancelled"},
            )
        )
        await update.message.reply_text(
            f"✅ Cancelled {count} pending order(s) for user {target_user_id}.\n"
            f"Order IDs: {', '.join(pending_ids[:5])}{'...' if count > 5 else ''}"
        )
    except Exception as exc:
        log.exception(f"[CLEARPENDING] failed user_id={target_user_id}")
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


# ─── Tenant Admin Commands ───────────────────────────────────────────────────

async def cmd_checkrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /checkrent — show tenant rental status."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if not TENANT_ID:
        await update.message.reply_text("❌ TENANT_ID not configured.")
        return
    try:
        rows = await asyncio.to_thread(
            lambda: sb_admin_get("tenants", f"select=*&id=eq.{TENANT_ID}&limit=1")
        )
        if not rows:
            await update.message.reply_text(f"❌ Tenant '{TENANT_ID}' not found in DB.")
            return
        t = rows[0]
        name = t.get("name") or t.get("id", "?")
        bot_username = t.get("bot_username", "?")
        status = t.get("status", "?")
        rent_start = t.get("rent_start", "N/A")
        if rent_start and rent_start != "N/A":
            rent_start = str(rent_start)[:10]
        rent_end = t.get("rent_end", "N/A")
        days_left = "N/A"
        if rent_end and rent_end != "N/A":
            try:
                end = datetime.fromisoformat(str(rent_end).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                diff = (end - now).days
                days_left = str(max(0, diff))
            except Exception:
                days_left = "?"
        active_icon = "Active" if is_tenant_active() else "Expired"
        dashboard_enabled = "Yes" if t.get("dashboard_secret") else "No"
        msg = (
            f"📋 Tenant Rental Info\n\n"
            f"Name: {name}\n"
            f"Bot: @{bot_username}\n"
            f"ID: {TENANT_ID}\n"
            f"Status: {status} ({active_icon})\n"
            f"Rent Start: {rent_start}\n"
            f"Rent End: {str(rent_end)[:10] if rent_end != 'N/A' else rent_end}\n"
            f"Days Left: {days_left}\n"
            f"Dashboard: {dashboard_enabled}"
        )
        await update.message.reply_text(msg)
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Error: {_safe_error(exc)}")


async def cmd_setqr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /setqr — set tenant payment QR code (reply to a photo)."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if not TENANT_ID:
        await update.message.reply_text("❌ TENANT_ID not configured.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Reply to a photo with /setqr to set it as the payment QR.")
        return
    photo = update.message.reply_to_message.photo[-1]
    file_id = photo.file_id
    try:
        rows = sb_admin_upsert("bot_settings", {"key": "payment_qr_file_id", "value": file_id, "tenant_id": TENANT_ID})
        await _load_bot_settings()
        await update.message.reply_text(f"✅ Payment QR updated.")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Error: {_safe_error(exc)}")


async def cmd_setbanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /setbanner — set tenant shop banner (reply to a photo)."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    if not TENANT_ID:
        await update.message.reply_text("❌ TENANT_ID not configured.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Reply to a photo with /setbanner to set it as the shop banner.")
        return
    photo = update.message.reply_to_message.photo[-1]
    file_id = photo.file_id
    try:
        rows = sb_admin_upsert("bot_settings", {"key": "banner_file_id", "value": file_id, "tenant_id": TENANT_ID})
        await _load_bot_settings()
        await update.message.reply_text(f"✅ Shop banner updated.")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Error: {_safe_error(exc)}")


async def cmd_reloadsettings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /reloadsettings — reload bot settings from Supabase."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    await _load_bot_settings()
    await update.message.reply_text("✅ Settings reloaded.")


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /setup — guide to configure a new tenant bot."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    msg = (
        "🔧 **Tenant Setup Guide**\n\n"
        "1. Ensure TENANT_ID is set in environment\n"
        "2. Add your tenant record to Supabase `tenants` table\n"
        "3. Use /setqr (reply to a photo) to set payment QR\n"
        "4. Use /setbanner (reply to a photo) to set shop banner\n"
        "5. Add products via dashboard or manually\n"
        "6. Use /checkrent to verify tenant status\n"
        "7. Use /checksetup to verify everything is ready\n\n"
        "Your bot serves tenant: `" + (TENANT_ID or "❌ NOT SET") + "`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ─── Heartbeat for Central Dashboard ──────────────────────────────────────────

async def _heartbeat(context: ContextTypes.DEFAULT_TYPE = None):
    """Update tenants.last_heartbeat_at and bot_status for this tenant."""
    if not TENANT_ID:
        return
    try:
        now_utc = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(
            lambda: sb_admin_patch("tenants", f"id=eq.{TENANT_ID}", {
                "last_heartbeat_at": now_utc,
                "bot_status": "online",
            })
        )
        log.info("Tenant heartbeat updated")
    except Exception as exc:
        log.warning(f"Tenant heartbeat failed: {_safe_error(exc)}")


async def _heartbeat_startup():
    """Run heartbeat once at startup."""
    await _heartbeat()


async def cmd_checksetup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /checksetup — verify tenant setup completeness."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    lines = [f"Tenant Setup Status — ID: {TENANT_ID or '❌ NOT SET'}"]
    lines.append("─" * 35)

    # Tenant config
    lines.append(f"{'✅' if TENANT_ID else '❌'} TENANT_ID: {TENANT_ID or 'MISSING'}")

    # Rental status
    rental_active = False
    if TENANT_ID:
        try:
            rows = await asyncio.to_thread(
                lambda: sb_admin_get("tenants", f"select=id,status&id=eq.{TENANT_ID}&limit=1")
            )
            in_db = bool(rows)
            active = rows and rows[0].get("status") in ("active", "trial")
            rental_active = active
            lines.append(f"{'✅' if in_db else '❌'} Tenant in database")
            lines.append(f"{'✅' if active else '❌'} Rental active")
        except Exception:
            lines.append("❌ Tenant in database — lookup failed")
            lines.append("❌ Rental active — lookup failed")

    # Count queries scoped by tenant
    try:
        products = await asyncio.to_thread(lambda: sb_get("products", "select=id"))
        p_count = len(products)
        lines.append(f"{'✅' if p_count > 0 else '⚠️'} Products: {p_count}")
    except Exception:
        p_count = 0
        lines.append("❌ Products — query failed")

    try:
        variants = await asyncio.to_thread(lambda: sb_get("product_variants", "select=id"))
        v_count = len(variants)
        lines.append(f"{'✅' if v_count > 0 else 'ℹ️'} Variants: {v_count}")
    except Exception:
        v_count = 0
        lines.append("❌ Variants — query failed")

    try:
        settings_rows = await asyncio.to_thread(lambda: sb_get("bot_settings", "select=key"))
        s_count = len(settings_rows)
        lines.append(f"{'✅' if s_count > 0 else 'ℹ️'} Bot settings: {s_count}")
    except Exception:
        s_count = 0
        lines.append("❌ Bot settings — query failed")

    # Payment QR and banner
    if TENANT_ID:
        qr_file_id = await _setting("payment_qr_file_id", "")
        qr_url = await _setting("payment_qr_url", "")
        banner_url = await _setting("banner_url", "")
        banner_file_id = await _setting("banner_file_id", "")
        lines.append(f"Payment QR URL present: {'true' if qr_url else 'false'}")
        lines.append(f"Payment QR File present: {'true' if qr_file_id else 'false'}")
        lines.append(f"Banner URL present: {'true' if banner_url else 'false'}")
        lines.append(f"Banner File present: {'true' if banner_file_id else 'false'}")

    # Feature flags
    enable_fj = (await _setting("enable_force_join", "false")).lower() == "true"
    notify_fj_err = (await _setting("notify_admin_force_join_errors", "false")).lower() == "true"
    send_approved_msg = (await _setting("send_payment_approved_message", "true")).lower() == "true"
    enable_pts_msg = (await _setting("enable_points_message", "true")).lower() == "true"
    lines.append(f"REQUIRED_CHANNEL: {REQUIRED_CHANNEL or '(not set)'}")
    lines.append(f"enable_force_join: {enable_fj}")
    lines.append(f"notify_admin_force_join_errors: {notify_fj_err}")
    lines.append(f"send_payment_approved_message: {send_approved_msg}")
    lines.append(f"enable_points_message: {enable_pts_msg}")

    # Overall readiness
    shop_ready = p_count > 0
    qr_ok = bool(qr_file_id) or bool(qr_url) if TENANT_ID else False
    lines.append("─" * 35)
    lines.append(f"{'✅ Shop ready' if shop_ready else '❌ Shop NOT ready — add products first'}")
    lines.append("")
    if not shop_ready:
        lines.append("Use /setup for guidance on getting started.")
    elif not qr_ok:
        lines.append("⚠️ Payment QR not configured — customers will see a warning.")
    await update.message.reply_text("\n".join(lines))


async def cmd_shopdebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /shopdebug — show product/variant status breakdown."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return
    try:
        all_products = await asyncio.to_thread(
            lambda: sb_get("products", "select=id,name,stock,is_active,status&order=id")
        ) or []
        all_variants = await asyncio.to_thread(
            lambda: sb_get("product_variants", "select=id,product_id,variant_name,stock,price&stock=gt.0")
        ) or []
        shown_products = [
            p for p in all_products
            if p.get("is_active") is not False
            and str(p.get("status", "active")).lower() not in ("inactive", "deleted")
        ]
        active_count = sum(1 for p in all_products
                           if p.get("is_active") is True
                           and str(p.get("status", "")).lower() == "active")
        inactive_count = sum(1 for p in all_products
                             if p.get("is_active") is False
                             and str(p.get("status", "")).lower() == "inactive")
        deleted_count = sum(1 for p in all_products
                            if str(p.get("status", "")).lower() == "deleted")
        other_count = len(all_products) - active_count - inactive_count - deleted_count
        shown_product_ids = {p["id"] for p in shown_products}
        shown_variants = [v for v in all_variants if v.get("product_id") in shown_product_ids]
        lines = [
            f"Shop Debug — ID: {TENANT_ID}",
            "─" * 35,
            f"All products: {len(all_products)}",
            f"Active shown: {len(shown_products)}",
            f"Inactive hidden: {inactive_count}",
            f"Deleted hidden: {deleted_count}",
            f"Other/unknown: {other_count}",
            "Variants with stock>0:",
            f"  All variants: {len(all_variants)}",
            f"  Shown variants: {len(shown_variants)}",
            "─" * 35,
            "Latest 5 shown products:",
        ]
        for p in shown_products[-5:]:
            lines.append(f"  • {p.get('id')} {p.get('name','?')} "
                         f"is_active={p.get('is_active')} status={p.get('status','—')}")
        # ── Credential counts by product + variant ─────────────────────────
        try:
            all_creds = await asyncio.to_thread(
                lambda: sb_get("credentials", "select=id,product_id,variant_id,is_used")
            ) or []
            if all_creds:
                lines.append("─" * 35)
                lines.append("Credentials by product+variant:")
                cred_groups: dict[str, dict] = {}
                for c in all_creds:
                    pid = c.get("product_id")
                    vid = c.get("variant_id") or "null"
                    key = f"p{pid}_v{vid}"
                    if key not in cred_groups:
                        cred_groups[key] = {"product_id": pid, "variant_id": vid, "total": 0, "unused": 0}
                    cred_groups[key]["total"] += 1
                    if not c.get("is_used"):
                        cred_groups[key]["unused"] += 1
                for key in sorted(cred_groups.keys()):
                    g = cred_groups[key]
                    delivered = g["total"] - g["unused"]
                    lines.append(f"  Product {g['product_id']} | Variant {g['variant_id']}: "
                                 f"{g['total']} total ({g['unused']} unused, {delivered} delivered)")
        except Exception:
            pass
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Error: {_safe_error(exc)}")


# ─── Master Admin Tenant Management Commands ─────────────────────────────────

DEFAULT_TENANT_SETTINGS = {
    "welcome_message": "",
    "support_username": "",
    "shop_title": "LIST PRODUCT",
    "shop_footer": "Taip nombor atau tekan butang di bawah",
    "out_of_stock_msg": "Stok habis",
    "product_delivery_note": "Produk digital akan dihantar selepas pembayaran",
    "payment_title": "PAYMENT DETAILS",
    "payment_instruction": "Scan QR below to pay",
    "payment_button_instruction": "Saya sudah bayar",
    "order_summary_title": "ORDER SUMMARY",
    "order_proceed_msg": "Sila buat pembayaran",
    "delivery_msg": "Produk sedang dihantar",
    "auto_delivery_msg": "Produk akan dihantar secara automatik",
    "testimonial_template": "",
    "payment_qr_file_id": "",
    "banner_file_id": "",
}


def _is_master_admin(user_id: int) -> bool:
    return MASTER_ADMIN_ID > 0 and user_id == MASTER_ADMIN_ID


async def cmd_newtenant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /newtenant Name | bot_username | owner_id | owner_username | monthly_price | months"""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    args = " ".join(context.args).strip()
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 6:
        await update.message.reply_text(
            "Usage:\n/newtenant Store Name | bot_username | owner_telegram_id | owner_username | monthly_price | months\n\n"
            "Example:\n/newtenant Afiq Store | afiqshop_bot | 123456789 | afiq | 30 | 1"
        )
        return
    name, bot_username, owner_id_str, owner_username, price_str, months_str = parts[:6]
    try:
        owner_id = int(owner_id_str)
        monthly_price = float(price_str)
        months = int(months_str)
    except ValueError:
        await update.message.reply_text("❌ owner_telegram_id, monthly_price, and months must be numeric.")
        return
    if months < 1:
        await update.message.reply_text("❌ months must be at least 1.")
        return
    now_utc = datetime.now(timezone.utc)
    rent_start = now_utc.isoformat()
    rent_end = (now_utc + timedelta(days=30 * months)).isoformat()
    try:
        rows = sb_admin_post("tenants", {
            "name": name,
            "bot_username": bot_username,
            "owner_telegram_id": str(owner_id),
            "owner_username": owner_username,
            "status": "active",
            "plan_name": "monthly",
            "monthly_price": monthly_price,
            "rent_start": rent_start,
            "rent_end": rent_end,
            "notes": "Created from /newtenant",
        })
        if not rows:
            await update.message.reply_text("❌ Failed to create tenant — no row returned.")
            return
        tenant = rows[0]
        tenant_id = tenant.get("id") or tenant.get("tenant_id")
        if not tenant_id:
            await update.message.reply_text("❌ Tenant created but could not read ID.")
            return
        # Insert default bot_settings for this tenant
        for key, value in DEFAULT_TENANT_SETTINGS.items():
            sb_admin_post("bot_settings", {
                "key": key,
                "value": value,
                "tenant_id": tenant_id,
            })
        msg = (
            f"✅ **Tenant Created Successfully**\n\n"
            f"Name: {name}\n"
            f"Bot Username: @{bot_username}\n"
            f"Owner ID: {owner_id}\n"
            f"Rent Start: {rent_start}\n"
            f"Rent End: {rent_end}\n"
            f"TENANT_ID: `{tenant_id}`\n\n"
            f"**Render env template:**\n"
            f"```\n"
            f"BOT_TOKEN=\n"
            f"ADMIN_ID={owner_id}\n"
            f"TENANT_ID={tenant_id}\n"
            f"REQUIRED_CHANNEL=\n"
            f"REQUIRED_CHANNEL_URL=\n"
            f"SUPABASE_URL={SUPABASE_URL}\n"
            f"SUPABASE_KEY={SUPABASE_KEY}\n"
            f"SUPABASE_SERVICE_KEY={SUPABASE_SERVICE_KEY}\n"
            f"DASHBOARD_ADMIN_SECRET=\n"
            f"```"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error creating tenant: {_safe_error(exc)}")


async def cmd_tenantlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /tenantlist — show recent tenants."""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    try:
        rows = sb_admin_get("tenants", "select=id,name,bot_username,status,rent_end,owner_telegram_id&order=created_at.desc&limit=20")
        if not rows:
            await update.message.reply_text("No tenants found.")
            return
        lines = ["📋 **Recent Tenants**\n"]
        for t in rows:
            tid = t.get("id", "?")
            name = t.get("name", "?")
            bot = t.get("bot_username", "?")
            status = t.get("status", "?")
            rent_end = (t.get("rent_end") or "?")[:10]
            lines.append(f"`{tid}` | {name} | @{bot} | {status} | ends {rent_end}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


async def cmd_tenantinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /tenantinfo TENANT_ID — show tenant details."""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /tenantinfo TENANT_ID")
        return
    tenant_id = context.args[0].strip()
    try:
        rows = sb_admin_get("tenants", f"select=*&id=eq.{tenant_id}&limit=1")
        if not rows:
            await update.message.reply_text(f"❌ Tenant `{tenant_id}` not found.")
            return
        t = rows[0]
        settings_rows = sb_admin_get("bot_settings", f"select=key,value&tenant_id=eq.{tenant_id}")
        settings_map = {s["key"]: s["value"] for s in (settings_rows or [])}
        qr_set = bool(settings_map.get("payment_qr_file_id"))
        banner_set = bool(settings_map.get("banner_file_id"))
        product_count = len(sb_admin_get("products", f"select=id&tenant_id=eq.{tenant_id}") or [])
        user_count = len(sb_admin_get("users", f"select=id&tenant_id=eq.{tenant_id}") or [])
        order_count = len(sb_admin_get("orders", f"select=id&tenant_id=eq.{tenant_id}") or [])
        msg = (
            f"📋 **Tenant Info: `{tenant_id}`**\n\n"
            f"Name: {t.get('name', '?')}\n"
            f"Bot: @{t.get('bot_username', '?')}\n"
            f"Owner ID: {t.get('owner_telegram_id', '?')}\n"
            f"Owner: {t.get('owner_username', '?')}\n"
            f"Status: {t.get('status', '?')}\n"
            f"Plan: {t.get('plan_name', '?')}\n"
            f"Price: {t.get('monthly_price', '?')}\n"
            f"Rent Start: {t.get('rent_start', '?')[:10]}\n"
            f"Rent End: {t.get('rent_end', '?')[:10]}\n\n"
            f"**Setup Status:**\n"
            f"QR set: {'✅' if qr_set else '❌'}\n"
            f"Banner set: {'✅' if banner_set else '❌'}\n"
            f"Products: {product_count}\n"
            f"Users: {user_count}\n"
            f"Orders: {order_count}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


async def cmd_extendtenant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /extendtenant TENANT_ID months — extend rent."""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /extendtenant TENANT_ID months")
        return
    tenant_id = context.args[0].strip()
    try:
        months = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ months must be a number.")
        return
    if months < 1:
        await update.message.reply_text("❌ months must be at least 1.")
        return
    try:
        rows = sb_admin_get("tenants", f"select=id,rent_end,name&id=eq.{tenant_id}&limit=1")
        if not rows:
            await update.message.reply_text(f"❌ Tenant `{tenant_id}` not found.")
            return
        t = rows[0]
        current_end = t.get("rent_end")
        if current_end:
            try:
                base = datetime.fromisoformat(current_end.replace("Z", "+00:00"))
            except ValueError:
                base = datetime.now(timezone.utc)
        else:
            base = datetime.now(timezone.utc)
        new_end = (base + timedelta(days=30 * months)).isoformat()
        sb_admin_patch("tenants", f"id=eq.{tenant_id}", {"rent_end": new_end, "status": "active"})
        await update.message.reply_text(
            f"✅ **Tenant Extended**\n\n"
            f"Tenant: {t.get('name', tenant_id)}\n"
            f"Months added: {months}\n"
            f"New rent end: {new_end[:10]}",
            parse_mode="Markdown"
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


async def cmd_suspendtenant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /suspendtenant TENANT_ID — suspend a tenant."""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /suspendtenant TENANT_ID")
        return
    tenant_id = context.args[0].strip()
    try:
        rows = sb_admin_get("tenants", f"select=id,name&id=eq.{tenant_id}&limit=1")
        if not rows:
            await update.message.reply_text(f"❌ Tenant `{tenant_id}` not found.")
            return
        sb_admin_patch("tenants", f"id=eq.{tenant_id}", {"status": "suspended"})
        await update.message.reply_text(f"✅ Tenant `{rows[0].get('name', tenant_id)}` suspended.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


async def cmd_activatetenant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master admin: /activatetenant TENANT_ID — activate a tenant."""
    if not _is_master_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Only the bot platform owner can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /activatetenant TENANT_ID")
        return
    tenant_id = context.args[0].strip()
    try:
        rows = sb_admin_get("tenants", f"select=id,name&id=eq.{tenant_id}&limit=1")
        if not rows:
            await update.message.reply_text(f"❌ Tenant `{tenant_id}` not found.")
            return
        sb_admin_patch("tenants", f"id=eq.{tenant_id}", {"status": "active"})
        await update.message.reply_text(f"✅ Tenant `{rows[0].get('name', tenant_id)}` activated.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {_safe_error(exc)}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("ping",        cmd_ping)); log.info("[HANDLERS] ping registered")
    app.add_handler(CommandHandler("start",  cmd_start)); log.info("[HANDLERS] start registered")
    app.add_handler(CommandHandler("admin",       cmd_admin))
    app.add_handler(CommandHandler("adminorders", cmd_adminorders))
    app.add_handler(CommandHandler("unsent",      cmd_unsent))
    app.add_handler(CommandHandler("stock",       cmd_stock))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    app.add_handler(CommandHandler("testchannel", cmd_testchannel))
    app.add_handler(CommandHandler("shop",   show_shop))
    app.add_handler(CommandHandler("orders", my_orders))
    app.add_handler(CommandHandler("send",      send_account_command))
    app.add_handler(CommandHandler("addcred",   cmd_addcred))
    app.add_handler(CommandHandler("credstock", cmd_credstock))
    app.add_handler(CommandHandler("credcheck", cmd_credcheck))
    app.add_handler(CommandHandler("points",    cmd_points))
    app.add_handler(CommandHandler("salesreport", cmd_salesreport))
    app.add_handler(CommandHandler("clearpending", cmd_clearpending))
    app.add_handler(CommandHandler("checkrent",  cmd_checkrent))
    app.add_handler(CommandHandler("setup",      cmd_setup))
    app.add_handler(CommandHandler("setqr",      cmd_setqr))
    app.add_handler(CommandHandler("setbanner",  cmd_setbanner))
    app.add_handler(CommandHandler("reloadsettings", cmd_reloadsettings))
    app.add_handler(CommandHandler("checksetup", cmd_checksetup))
    app.add_handler(CommandHandler("shopdebug",  cmd_shopdebug))
    app.add_handler(CommandHandler("newtenant",  cmd_newtenant))
    app.add_handler(CommandHandler("tenantlist", cmd_tenantlist))
    app.add_handler(CommandHandler("tenantinfo", cmd_tenantinfo))
    app.add_handler(CommandHandler("extendtenant", cmd_extendtenant))
    app.add_handler(CommandHandler("suspendtenant", cmd_suspendtenant))
    app.add_handler(CommandHandler("activatetenant", cmd_activatetenant))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)); log.info("[HANDLERS] message handler registered")
    app.add_error_handler(on_error)
    # ── Tenant validation (safe to call sb_get now) ──────────────────────────
    log.info("─" * 35)
    _log_tenant_info()
    log.info("─" * 35)
    # ── Background job: auto-cancel expired pending orders every 15 minutes ──
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            _auto_cancel_expired_orders,
            interval=15 * 60,   # every 15 minutes
            first=60,           # first run 60 seconds after bot starts
            name="auto_cancel_expired_orders",
        )
        log.info("[AUTO-CANCEL] Background job registered successfully")
        app.job_queue.run_daily(
            _send_daily_sales_report,
            time=dt_time(hour=0, minute=0, second=0, tzinfo=ZoneInfo("Asia/Kuala_Lumpur")),
            name="daily_sales_report",
        )
        log.info("[SALES REPORT] Daily sales report job registered")
        # ── Heartbeat (every 5 min) ────────────────────────────────────────────
        app.job_queue.run_repeating(
            _heartbeat,
            interval=5 * 60,
            first=10,
            name="tenant_heartbeat",
        )
        log.info("[HEARTBEAT] Tenant heartbeat job registered (every 5 min)")
    else:
        log.warning("[AUTO-CANCEL] JobQueue unavailable. Install python-telegram-bot[job-queue] to enable auto-cancel.")
        log.warning("[SALES REPORT] JobQueue unavailable. Daily sales report disabled.")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_load_bot_settings())
            loop.create_task(_heartbeat_startup())
        else:
            loop.run_until_complete(_load_bot_settings())
            loop.run_until_complete(_heartbeat_startup())
    except Exception:
        pass
    return app

# ─── Auto-Restart Polling Loop ────────────────────────────────────────────────

def main():
    global _telegram_app, _telegram_loop
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN tidak ditetapkan — bot Telegram tidak akan dijalankan.")
        log.warning("Set BOT_TOKEN dalam Replit Secrets, kemudian restart workflow.")
        log.info("Flask server berjalan. Lawati /dashboard untuk panel admin.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            log.info("Dihenti oleh pengguna.")
        return

    if not _validate_telegram_token():
        log.warning("Token Telegram tidak sah — menunggu dalam Flask mode.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
        return

    retry_delay = 5          # seconds before first retry
    max_delay   = 120        # cap at 2 minutes
    attempt     = 0

    while True:
        attempt += 1
        log.info(f"Bot starting (attempt #{attempt})...")
        try:
            app = build_app()
            _telegram_app = app
            _telegram_loop = asyncio.get_event_loop()

            # Clear any lingering webhook so polling takes over cleanly
            try:
                _telegram_loop.run_until_complete(
                    app.bot.delete_webhook(drop_pending_updates=True)
                )
                log.info("[WEBHOOK] delete_webhook ok")
            except Exception as exc:
                log.warning(f"[WEBHOOK] delete_webhook failed: {_safe_error(exc)}")

            # Log webhook info for diagnostics
            try:
                wh = _telegram_loop.run_until_complete(app.bot.get_webhook_info())
                log.info(f"[WEBHOOK_INFO] url={wh.url!r}")
                log.info(f"[WEBHOOK_INFO] pending_update_count={wh.pending_update_count}")
                log.info(f"[WEBHOOK_INFO] last_error_message={wh.last_error_message!r}")
                log.info(f"[WEBHOOK_INFO] last_error_date={wh.last_error_date}")
            except Exception as exc:
                log.warning(f"[WEBHOOK_INFO] Could not fetch: {_safe_error(exc)}")

            log.info("[POLLING] started")
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
            )
            log.info("[POLLING] stopped")
            log.info("Bot berhenti dengan bersih.")
            break

        except KeyboardInterrupt:
            log.info("Bot dihenti oleh pengguna (Ctrl+C).")
            break

        except InvalidToken:
            log.critical("Telegram token rejected by Telegram API. Update the TELEGRAM_BOT_TOKEN secret, then restart the workflow.")
            sys.exit(1)

        except Exception as exc:
            log.error(f"[POLLING] error: {_safe_error(exc)}", exc_info=True)
            log.info(f"Restart dalam {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)   # exponential backoff


if __name__ == "__main__":
    main()
