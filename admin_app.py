"""Gemini dashboard host. Deliberately never imports bot.py or starts Telegram polling.

Staging can read the existing tenant. All business mutations fail closed until an
isolated write database and the audited RPC migration are explicitly configured.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from flask import Flask, jsonify, request, send_from_directory, g
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from ai_model_mapping import MappingValidationError, validate_mappings, encode_mappings, decode_mappings
from ai_model_mapping_store import PrivateMappingStore, PrivateMappingError, PrivateMappingConflict

log = logging.getLogger("berry.admin")
COOKIE = "__Host-berry_admin"
PREFIX = "/api/admin/v1"
SAFE_SETTINGS = frozenset({
    "welcome_message", "browse_shop_enabled", "ai_studio_enabled", "referral_enabled",
    "maintenance_mode", "banner_url", "payment_qr_url", "support_username",
    "announcement", "required_channel", "required_channel_url", "min_topup_amount",
    "referral_reward_rm",
})
COLUMNS = {
    "products": "id,name,description,price,stock,duration,is_active,auto_delivery,status,account_type,delivery_note,created_at",
    "product_variants": "id,product_id,variant_name,price,stock,description,delivery_note,created_at",
    "orders": "id,user_id,username,product_id,variant_id,product_name,quantity,amount,status,created_at,updated_at,credentials_sent",
    "users": "id,username,first_name,total_spent,referral_code,referred_by,created_at",
    "credentials": "id,product_id,variant_id,is_used,created_at,used_by_order_id",
    "ai_wallets": "user_id,currency,balance,updated_at",
    "ai_wallet_transactions": "id,user_id,kind,amount,balance_after,reference,idempotency_key,note,created_at",
    "bot_settings": "key,value",
    "categories": "id,name,emoji,description,display_order,is_active",
    "ai_tools": "id,name,category,enabled,provider,model_id,credit_cost,max_duration_sec,supported_ratios,daily_limit_per_user,maintenance,description",
    "ai_models": "id,name,provider,model_id,tool_category,provider_cost,customer_price,margin_pct,enabled,last_verified",
}


class BackendUnavailable(Exception):
    pass


class DataStore:
    """Server-only PostgREST client; no caller may specify a tenant or columns."""
    def __init__(self, url, key, tenant, client=None):
        self.url, self.key, self.tenant = url.rstrip("/"), key, tenant
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def configured(self):
        try:
            UUID(self.tenant)
            parsed = urlparse(self.url)
            return bool(self.key and parsed.scheme == "https" and parsed.hostname and parsed.hostname.endswith('.supabase.co') and parsed.port is None and not parsed.username and not parsed.password and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
        except (ValueError, TypeError, AttributeError):
            return False

    def headers(self):
        return {"apikey": self.key, "Authorization": "Bearer " + self.key}

    def read(self, table):
        if table not in COLUMNS or not self.configured():
            raise BackendUnavailable("Sambungan Supabase server belum dikonfigurasi")
        # Walk every page. Never present the first 500 rows as a complete total.
        rows = []
        sort = "key" if table == "bot_settings" else "user_id" if table == "ai_wallets" else "id"
        try:
            while True:
                response = self.client.get(f"{self.url}/rest/v1/{table}", headers=self.headers(), params={
                    "select": COLUMNS[table], "tenant_id": "eq." + self.tenant,
                    "order": sort + ".asc", "offset": len(rows), "limit": 500,
                })
                if response.status_code != 200:
                    log.warning("database read failed: table=%s status=%s", table, response.status_code)
                    raise BackendUnavailable(f"Data {table} belum tersedia; semak schema dan akses server")
                page = response.json()
                if not isinstance(page, list):
                    raise BackendUnavailable("Format respons database tidak sah")
                rows.extend(page)
                if len(page) < 500:
                    return rows
                if len(rows) >= 50000:
                    raise BackendUnavailable("Dataset melebihi had selamat; aggregation database diperlukan")
        except (httpx.HTTPError, ValueError) as from_exc:
            raise BackendUnavailable("Sambungan database gagal") from from_exc

    def mutate(self, operation, resource_id, payload, actor, key):
        if not self.configured():
            raise BackendUnavailable("Sambungan Supabase server belum dikonfigurasi")
        try:
            response = self.client.post(f"{self.url}/rest/v1/rpc/berry_admin_catalog_mutation", headers=self.headers(), json={
                "p_tenant": self.tenant, "p_operation": operation, "p_id": resource_id,
                "p_payload": payload, "p_actor": actor, "p_key": key,
            })
            if response.status_code != 200:
                raise BackendUnavailable("Transaksi ditolak; semak RPC audit dan idempotency sebelum mencuba semula")
            result = response.json()
            if not isinstance(result, dict) or result.get("status") != "committed":
                raise BackendUnavailable("Respons transaksi belum disahkan")
            return result
        except (httpx.HTTPError, ValueError) as exc:
            raise BackendUnavailable("Keputusan transaksi tidak diketahui. Semak audit sebelum cuba semula dengan idempotency key yang sama.") from exc


def money(value):
    try:
        amount = Decimal(str(value or 0))
        if not amount.is_finite():
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError):
        raise BackendUnavailable("Nilai wang database tidak sah")


def timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BackendUnavailable("Tarikh database tidak sah") from exc
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def overview(products, orders, wallets, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
    completed = [o for o in orders if o.get("status") in {"approved", "completed"}]
    def revenue(predicate):
        return float(sum((money(o.get("amount")) for o in completed if predicate(timestamp(o.get("created_at")))), Decimal(0)))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    trend = []
    for days in reversed(range(30)):
        day = start - timedelta(days=days)
        trend.append({"date": day.date().isoformat(), "revenue": revenue(lambda t: t is not None and day <= t < day + timedelta(days=1))})
    return {
        "kpis": {
            "totalRevenue": revenue(lambda t: True),
            "revenueToday": revenue(lambda t: t is not None and start <= t <= now),
            "revenueThisWeek": revenue(lambda t: t is not None and start - timedelta(days=now.weekday()) <= t <= now),
            "revenueThisMonth": revenue(lambda t: t is not None and start.replace(day=1) <= t <= now),
            "totalOrders": len(orders), "completedOrdersCount": len(completed),
            "pendingOrdersCount": sum(o.get("status") in {"pending", "waiting_payment", "waiting_approval"} for o in orders),
            "totalProducts": len(products),
            "lowStockCount": sum(bool(p.get("is_active")) and (p.get("stock") or 0) <= 5 for p in products),
            "aiWalletLiability": float(sum((money(w.get("balance")) for w in wallets), Decimal(0))),
            "estimatedGrossProfit": None,  # Cost basis is absent. Never invent profit.
        }, "revenueTrend": trend, "categoryRevenue": {}, "dataLimited": False,
        "unavailableMetrics": ["estimatedGrossProfit", "categoryRevenue"],
        "revenueBasis": "orders with approved/completed status, created_at in Asia/Kuala_Lumpur; gross sales, not a reconciled settlement ledger",
    }


def provider_key_present(names=None):
    """Presence-only audit: iterate environment NAMES; never fetch a secret value."""
    return any(name == "FAL_KEY" for name in (os.environ.keys() if names is None else names))


def create_app(config=None, store=None, mapping_store=None):
    app = Flask(__name__, static_folder=None)
    print("BERRY_PROVIDER_CONFIG fal_key_present=" + str(provider_key_present()).lower(), flush=True)
    # Render terminates TLS one trusted proxy hop ahead of the container.
    # Keep remote_addr unchanged; never trust client-supplied X-Forwarded-For.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1)
    app.config.update(
        ADMIN_PASSWORD_HASH=os.getenv("ADMIN_PASSWORD_HASH", ""),
        DASHBOARD_ADMIN_SECRET=os.getenv("DASHBOARD_ADMIN_SECRET", ""),
        SUPABASE_URL=os.getenv("SUPABASE_URL", ""),
        SUPABASE_SERVICE_KEY=os.getenv("SUPABASE_SERVICE_KEY", ""),
        TENANT_ID=os.getenv("TENANT_ID", ""),
        ADMIN_STATE_PATH=os.getenv("ADMIN_STATE_PATH", "/tmp/berry-admin-state.sqlite3"),
        ADMIN_MODE=os.getenv("ADMIN_MODE", "staging"),
        ADMIN_MODEL_MAPPING_DRAFT_ENABLED=os.getenv("ADMIN_MODEL_MAPPING_DRAFT_ENABLED", "false").lower() == "true",
        ADMIN_MODEL_MAPPING_PRIVATE_ENABLED=os.getenv("ADMIN_MODEL_MAPPING_PRIVATE_ENABLED", "false").lower() == "true",
        AI_MAPPING_SUPABASE_URL=os.getenv("AI_MAPPING_SUPABASE_URL", ""),
        AI_MAPPING_SUPABASE_SERVICE_KEY=os.getenv("AI_MAPPING_SUPABASE_SERVICE_KEY", ""),
        ADMIN_WRITES_ENABLED=os.getenv("ADMIN_WRITES_ENABLED", "false").lower() == "true",
        ADMIN_ISOLATED_DATABASE=os.getenv("ADMIN_ISOLATED_DATABASE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=256 * 1024,
        FRONTEND_DIST=str(Path(__file__).parent / "frontend" / "dist"),
    )
    if config:
        app.config.update(config)
    database = store or DataStore(app.config["SUPABASE_URL"], app.config["SUPABASE_SERVICE_KEY"], app.config["TENANT_ID"])
    app.extensions["berry_store"] = database
    private_mapping = mapping_store or PrivateMappingStore(
        app.config["AI_MAPPING_SUPABASE_URL"], app.config["AI_MAPPING_SUPABASE_SERVICE_KEY"],
        app.config["TENANT_ID"], business_url=app.config["SUPABASE_URL"])
    app.extensions["berry_private_mapping"] = private_mapping
    # The AI catalogue is staging-only and must never fall back to the shop database.
    ai_catalogue_store = DataStore(
        app.config["AI_MAPPING_SUPABASE_URL"],
        app.config["AI_MAPPING_SUPABASE_SERVICE_KEY"],
        app.config["TENANT_ID"],
    )
    app.extensions["berry_ai_catalogue"] = ai_catalogue_store


    def mapping_private_ready():
        return (app.config["ADMIN_MODE"] == "staging" and
                app.config["ADMIN_MODEL_MAPPING_PRIVATE_ENABLED"] and
                private_mapping.configured())

    def mapping_draft_ready():
        return (app.config["ADMIN_MODE"] == "staging" and
                not app.config["ADMIN_MODEL_MAPPING_PRIVATE_ENABLED"] and
                app.config["ADMIN_MODEL_MAPPING_DRAFT_ENABLED"])
    state = Path(app.config["ADMIN_STATE_PATH"])
    state.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, happened REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_ip_time ON attempts(ip,happened);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT NOT NULL, details TEXT NOT NULL, timestamp TEXT NOT NULL, ip TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ai_model_mapping_drafts (tenant_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
        """)
    state.chmod(0o600)

    def audit(action, details):
        # No submitted payloads, passwords, inventory secrets or service tokens.
        with sqlite3.connect(state) as conn:
            conn.execute("INSERT INTO audit(action,details,timestamp,ip) VALUES(?,?,?,?)", (action, details[:500], datetime.now(timezone.utc).isoformat(), request.remote_addr or "unknown"))
        log.info("admin audit action=%s", action)

    def origin_ok():
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return False
        return request.headers.get("Sec-Fetch-Site") not in {"cross-site"}

    @app.before_request
    def protect():
        if not request.path.startswith(PREFIX):
            return None
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not origin_ok():
            return jsonify(error="Origin tidak dibenarkan"), 403
        if request.path == PREFIX + "/auth/login" and request.method == "POST":
            return None
        raw = request.cookies.get(COOKIE, "")
        sid = hashlib.sha256(raw.encode()).hexdigest()
        with sqlite3.connect(state) as conn:
            session = conn.execute("SELECT csrf,expires FROM sessions WHERE id=?", (sid,)).fetchone()
        if not session or session[1] <= time.time():
            return jsonify(error="Authentication required", authenticated=False), 401
        g.session_id = sid
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-CSRF-Token", "")
            if not supplied or not hmac.compare_digest(supplied, session[0]):
                return jsonify(error="CSRF validation failed"), 403
        g.csrf = session[0]
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.path != PREFIX + "/auth/logout":
            # Narrow exception: edit an ephemeral staging-only SQLite draft.
            # No Supabase write, no provider job, no customer data mutation.
            draft_write = (request.method == "PUT"
                           and request.path == PREFIX + "/ai/model-mappings"
                           and (mapping_draft_ready() or mapping_private_ready()))
            if not draft_write and not (app.config["ADMIN_WRITES_ENABLED"] and app.config["ADMIN_ISOLATED_DATABASE"]):
                audit("mutation_blocked", request.method + " " + request.path)
                return jsonify(error="Tindakan dikunci: staging menggunakan data kedai sebenar. Database ujian berasingan dan RPC audit diperlukan."), 423
            key = request.headers.get("Idempotency-Key", "")
            try:
                UUID(key)
            except ValueError:
                return jsonify(error="Idempotency-Key UUID required"), 400
            g.idempotency_key = key
        return None

    @app.after_request
    def security_headers(response):
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        })
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(BackendUnavailable)
    def unavailable(error):
        return jsonify(error=str(error)), 503

    @app.errorhandler(404)
    def not_found(error):
        return jsonify(error="Endpoint tidak tersedia"), 404

    @app.errorhandler(405)
    def not_allowed(error):
        return jsonify(error="Kaedah tidak dibenarkan"), 405

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="Payload terlalu besar"), 413

    @app.post(PREFIX + "/auth/login")
    def login():
        ip = request.remote_addr or "unknown"
        now = time.time()
        with sqlite3.connect(state, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM attempts WHERE happened < ?", (now - 900,))
            conn.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            count = conn.execute("SELECT count(*) FROM attempts WHERE ip=?", (ip,)).fetchone()[0]
            if count >= 8:
                response = jsonify(error="Terlalu banyak percubaan. Cuba selepas 15 minit.")
                response.headers["Retry-After"] = "900"
                return response, 429
            conn.execute("INSERT INTO attempts VALUES(?,?)", (ip, now))
        payload = request.get_json(silent=True)
        password = payload.get("password") if isinstance(payload, dict) else None
        configured_hash, legacy = app.config["ADMIN_PASSWORD_HASH"], app.config["DASHBOARD_ADMIN_SECRET"]
        if not configured_hash and len(legacy) < 24:
            return jsonify(error="Admin authentication belum dikonfigurasi di server"), 503
        valid = False
        if isinstance(password, str) and 0 < len(password) <= 512:
            if configured_hash:
                try:
                    valid = check_password_hash(configured_hash, password)
                except ValueError:
                    valid = False
            else:
                valid = hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(legacy.encode()).digest())
        if not valid:
            audit("login_failed", "Invalid credentials")
            return jsonify(error="Kata laluan tidak sah"), 401
        raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with sqlite3.connect(state) as conn:
            old = request.cookies.get(COOKIE, "")
            conn.execute("DELETE FROM sessions WHERE id=?", (hashlib.sha256(old.encode()).hexdigest(),))
            conn.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(raw.encode()).hexdigest(), csrf, now + 3600))
        audit("login", "Admin session created")
        response = jsonify(user={"role": "admin"}, csrfToken=csrf)
        response.set_cookie(COOKIE, raw, max_age=3600, httponly=True, secure=True, samesite="Strict", path="/")
        return response

    @app.get(PREFIX + "/auth/me")
    def me():
        return jsonify(authenticated=True, user={"role": "admin"}, csrfToken=g.csrf)

    @app.post(PREFIX + "/auth/logout")
    def logout():
        with sqlite3.connect(state) as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (g.session_id,))
        audit("logout", "Admin session revoked")
        response = jsonify(ok=True)
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="Strict", path="/")
        return response

    def products():
        rows = database.read("products")
        variants = database.read("product_variants")
        for row in rows:
            row["id"] = str(row["id"])
            row["price"] = float(money(row.get("price")))
            row["stock"] = int(row.get("stock") or 0)
            row["description"] = row.get("description") or ""
            row["category"] = ""  # No category column in the current schema.
            row["variants"] = [dict(v, id=str(v["id"]), product_id=str(v["product_id"]), price=float(money(v.get("price"))), stock=int(v.get("stock") or 0)) for v in variants if str(v["product_id"]) == row["id"]]
        return rows

    @app.get(PREFIX + "/shop/products")
    def get_products():
        return jsonify(products())

    @app.get(PREFIX + "/orders")
    def get_orders():
        rows = database.read("orders")
        rows.sort(key=lambda row: (timestamp(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), str(row["id"])), reverse=True)
        return jsonify([dict(o, created_at=timestamp(o.get("created_at")).isoformat() if o.get("created_at") else None,
            product_id=str(o.get("product_id") or ""), amount=float(money(o.get("amount"))),
            username=o.get("username") or "", product_name=o.get("product_name") or "") for o in rows])

    @app.get(PREFIX + "/customers")
    def get_customers():
        users, orders, wallets = database.read("users"), database.read("orders"), database.read("ai_wallets")
        balances = {w["user_id"]: float(money(w.get("balance"))) for w in wallets}
        return jsonify([dict(u, name=u.get("first_name") or u.get("username") or str(u["id"]), username=u.get("username") or "", joined_at=u.get("created_at"), total_spent=float(money(u.get("total_spent"))), total_orders=sum(o.get("user_id") == u["id"] for o in orders), wallet_balance=balances.get(u["id"], 0), referral_count=sum(bool(u.get("referral_code")) and r.get("referred_by") == u["referral_code"] for r in users), status="unknown", notes="") for u in users])

    @app.get(PREFIX + "/credentials")
    def get_credentials():
        return jsonify([dict(row, id=str(row["id"]), product_id=str(row.get("product_id") or ""), variant_id=str(row["variant_id"]) if row.get("variant_id") else None, credential_data="", credential_data_masked="••••••••", order_id=str(row["used_by_order_id"]) if row.get("used_by_order_id") else None) for row in database.read("credentials")])

    @app.get(PREFIX + "/wallet")
    def wallet():
        wallets, transactions = database.read("ai_wallets"), database.read("ai_wallet_transactions")
        return jsonify(wallets=[dict(w, username=str(w["user_id"]), balance=float(money(w.get("balance")))) for w in wallets], transactions=[dict(t, amount=float(money(t.get("amount"))), balance_after=float(money(t.get("balance_after")))) for t in reversed(transactions)], totalBalance=float(sum((money(w.get("balance")) for w in wallets), Decimal(0))), dataLimited=False)

    @app.get(PREFIX + "/dashboard/overview")
    def get_overview():
        return jsonify(overview(database.read("products"), database.read("orders"), database.read("ai_wallets")))

    @app.get(PREFIX + "/bot-settings")
    def get_settings():
        return jsonify({row["key"]: row.get("value") or "" for row in database.read("bot_settings") if row["key"] in SAFE_SETTINGS})

    @app.get(PREFIX + "/referrals")
    def referrals():
        return jsonify(database.read("users"))

    @app.get(PREFIX + "/shop/categories")
    def categories():
        return jsonify(database.read("categories"))

    @app.get(PREFIX + "/ai/tools")
    @app.get(PREFIX + "/ai/models")
    def ai_catalogue():
        if (app.config["ADMIN_MODE"] != "staging" or
                not app.config["ADMIN_MODEL_MAPPING_PRIVATE_ENABLED"] or
                not private_mapping.configured() or
                not ai_catalogue_store.configured()):
            raise BackendUnavailable("AI Catalogue staging belum dikonfigurasi secara terasing")
        return jsonify(ai_catalogue_store.read("ai_tools" if request.path.endswith("tools") else "ai_models"))

    @app.get(PREFIX + "/ai/model-mappings")
    def model_mapping_list():
        """Only staging. Private persistent mode must be on an isolated project."""
        if app.config["ADMIN_MODEL_MAPPING_PRIVATE_ENABLED"]:
            if not mapping_private_ready():
                return jsonify(error="Private staging mapping database tidak dikonfigurasi secara berasingan"), 423
            try:
                data = private_mapping.get()
            except PrivateMappingError:
                return jsonify(error="Private mapping database belum tersedia; semak konfigurasi"), 503
            response = jsonify(data["mappings"])
            response.headers["X-Berry-Mapping-Mode"] = "private-persistent-staging"
            response.headers["X-Berry-Mapping-Revision"] = str(data["revision"])
            return response
        if not mapping_draft_ready():
            return jsonify(error="Model mapping tidak diaktifkan pada servis ini"), 423
        with sqlite3.connect(state) as conn:
            row = conn.execute(
                "SELECT payload FROM ai_model_mapping_drafts WHERE tenant_id=?",
                (app.config["TENANT_ID"],)
            ).fetchone()
        try:
            response = jsonify(decode_mappings(row[0] if row else None))
            response.headers["X-Berry-Mapping-Mode"] = "staging-draft-only"
            return response
        except MappingValidationError:
            return jsonify(error="Staging draft corrupt; semak storan tempatan"), 503

    @app.put(PREFIX + "/ai/model-mappings")
    def model_mapping_save():
        """Writes ONLY a local draft or dedicated private staging database."""
        if not (mapping_draft_ready() or mapping_private_ready()):
            return jsonify(error="Penyimpanan mapping staging tidak dibenarkan"), 423
        payload = request.get_json(silent=True)
        try:
            models = validate_mappings(payload)
        except MappingValidationError as exc:
            return jsonify(error=str(exc)), 400
        if app.config["ADMIN_MODEL_MAPPING_PRIVATE_ENABLED"]:
            try:
                revision = int(request.headers.get("X-Berry-Mapping-Revision", ""))
                if revision < 0:
                    raise ValueError
            except ValueError:
                return jsonify(error="Mapping revision diperlukan; refresh dahulu"), 400
            try:
                data = private_mapping.put(models, g.idempotency_key, revision)
            except PrivateMappingConflict:
                return jsonify(error="Mapping telah diubah. Refresh sebelum cuba semula"), 409
            except (PrivateMappingError, ValueError):
                return jsonify(error="Keputusan simpanan tidak pasti; refresh untuk semak sebelum cuba semula"), 503
            audit("ai_model_mapping_private_saved", "count=" + str(len(models)))
            response = jsonify(data["mappings"])
            response.headers["X-Berry-Mapping-Mode"] = "private-persistent-staging"
            response.headers["X-Berry-Mapping-Revision"] = str(data["revision"])
            return response
        with sqlite3.connect(state, timeout=10) as conn:
            conn.execute(
                """INSERT INTO ai_model_mapping_drafts(tenant_id, payload, updated_at)
                   VALUES(?, ?, ?) ON CONFLICT(tenant_id) DO UPDATE
                   SET payload=excluded.payload, updated_at=excluded.updated_at""",
                (app.config["TENANT_ID"], encode_mappings(models),
                 datetime.now(timezone.utc).isoformat())
            )
        audit("ai_model_mapping_staging_draft_saved", "count=" + str(len(models)))
        response = jsonify(models)
        response.headers["X-Berry-Mapping-Mode"] = "staging-draft-only"
        return response

    @app.get(PREFIX + "/broadcast")
    def broadcasts():
        return jsonify(error="Sejarah broadcast belum disimpan oleh bot sedia ada; penghantaran staging dikunci"), 501

    @app.get(PREFIX + "/ai/models/<model_id>/health")
    def model_health(model_id):
        return jsonify(error="Provider AI belum diuji; semakan berbayar dikunci"), 501

    @app.get(PREFIX + "/system/audit-logs")
    def logs():
        with sqlite3.connect(state) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r, actor="admin") for r in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]
        return jsonify(rows)

    @app.get(PREFIX + "/system/health")
    def health():
        database_status = "not_configured"
        if database.configured():
            try:
                database.read("bot_settings")
                database_status = "ok"
            except BackendUnavailable:
                database_status = "unavailable"
        return jsonify(configuration={"tenantConfigured": bool(app.config["TENANT_ID"]), "serverKeyConfigured": bool(app.config["SUPABASE_SERVICE_KEY"])}, database=database_status, telegram="polling_disabled_in_admin_host", ai="not_verified", mode=app.config["ADMIN_MODE"], writesEnabled=bool(app.config["ADMIN_WRITES_ENABLED"] and app.config["ADMIN_ISOLATED_DATABASE"]), auditPersistence="local_sqlite; configure persistent disk/shared store before production", status="ok" if database_status == "ok" else "degraded")

    @app.post(PREFIX + "/shop/products")
    @app.put(PREFIX + "/shop/products/<resource_id>")
    @app.delete(PREFIX + "/shop/products/<resource_id>")
    @app.patch(PREFIX + "/shop/products/<resource_id>/stock")
    def product_write(resource_id=None):
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify(error="JSON object required"), 400
        if resource_id is not None and (not resource_id.isdigit() or int(resource_id) <= 0):
            return jsonify(error="Invalid product ID"), 400
        if request.method == "DELETE":
            operation, validated = "product_archive", {}
        elif request.method == "PATCH":
            stock = payload.get("newStock")
            if isinstance(stock, bool) or not isinstance(stock, int) or not 0 <= stock <= 1000000:
                return jsonify(error="Stok mestilah integer 0–1000000"), 400
            operation, validated = "product_stock", {"stock": stock}
        else:
            name = payload.get("name")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
                return jsonify(error="Nama produk diperlukan (maksimum 200 aksara)"), 400
            try:
                price = Decimal(str(payload.get("price")))
                if not price.is_finite() or price < 0 or price > 1000000 or price.as_tuple().exponent < -2:
                    raise ValueError
                stock = payload.get("stock", 0)
                if isinstance(stock, bool) or not isinstance(stock, int) or not 0 <= stock <= 1000000:
                    raise ValueError
                if any(not isinstance(payload.get(k, False), bool) for k in ("is_active", "auto_delivery")):
                    raise ValueError
                for key in ("description", "duration"):
                    if not isinstance(payload.get(key, ""), str) or len(payload.get(key, "")) > 10000:
                        raise ValueError
            except (ValueError, InvalidOperation):
                return jsonify(error="Harga, stok atau field produk tidak sah"), 400
            # New UI fields have no durable counterpart: reject instead of silently discarding.
            if payload.get("category") or payload.get("variants") or payload.get("image_url"):
                return jsonify(error="Kategori, gambar dan variant nested memerlukan migration sebelum disimpan"), 409
            operation = "product_update" if resource_id else "product_create"
            validated = {k: payload[k] for k in ("description", "duration", "is_active", "auto_delivery") if k in payload}
            validated.update(name=name.strip(), price=str(price), stock=stock)
        result = database.mutate(operation, resource_id, validated, "admin", g.idempotency_key)
        audit(operation, f"resource={resource_id or 'new'}; transaction audited in database")
        return jsonify(result)

    @app.route(PREFIX + "/<path:unimplemented>", methods=["POST", "PUT", "PATCH", "DELETE"])
    def unavailable_mutation(unimplemented):
        return jsonify(error="Operasi belum diluluskan: atomic transaction, audit dan delivery worker perlu disahkan sebelum diaktifkan"), 501

    @app.get("/healthz")
    def liveness():
        return jsonify(status="ok", component="gemini-admin-host", botPolling=False)

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/dashboard/<path:route>")
    def index(route=""):
        dist = app.config["FRONTEND_DIST"]
        if not (Path(dist) / "index.html").exists():
            return jsonify(error="React production build belum tersedia"), 503
        return send_from_directory(dist, "index.html")

    @app.get("/assets/<path:asset>")
    def assets(asset):
        return send_from_directory(Path(app.config["FRONTEND_DIST"]) / "assets", asset)

    @app.get("/images/<path:image>")
    def images(image):
        return send_from_directory(Path(app.config["FRONTEND_DIST"]) / "images", image)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
