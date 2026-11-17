"""Berry Store Promotion Center: tenant-bound campaigns, permissioned delivery.

Only the server can access these PostgREST tables and Threads OAuth tokens.
Google Forms belonging to third parties are presented as *prefilled manual*
submissions: the official Google Forms API cannot submit a respondent answer.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urlunparse

import httpx
from flask import Blueprint, jsonify, request, redirect
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

log = logging.getLogger("berry.promotion")
TABLES = ("promotion_destinations", "promotion_threads_accounts", "promotion_templates",
          "promotion_campaigns", "promotion_deliveries")
MAX_DESTINATIONS = 40  # safeguard against accidental bulk unsolicited posting
THREADS_LIMIT = 3
THREADS_TEXT_MAX = 500
_workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="berry-promotion")
ENTRY_ID = re.compile(r"entry\.[0-9]{1,20}\Z")
CHAT_ID = re.compile(r"(?:-?[0-9]{5,20}|@[A-Za-z][A-Za-z0-9_]{4,31})\Z")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\Z")


class PromotionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def safe_form_url(url):
    """Restrict prefill links to bona fide Google Forms view pages."""
    try:
        p = urlparse(url)
        if p.scheme != "https" or p.port is not None or p.username or p.password:
            raise ValueError
        if p.hostname == "forms.gle" and re.fullmatch(r"/[A-Za-z0-9_-]{5,100}", p.path):
            return "https://forms.gle" + p.path
        if (p.hostname != "docs.google.com" or not p.path.startswith("/forms/")
                or not (p.path.endswith("/viewform") or p.path.endswith("/viewform/"))):
            raise ValueError
        return urlunparse(("https", "docs.google.com", p.path.rstrip("/"), "", "", ""))
    except ValueError as exc:
        raise PromotionError("Gunakan link Google Form /viewform yang sah") from exc


def prefilled_form_url(destination, message):
    base = safe_form_url(destination.get("target_url") or "")
    if base.startswith("https://forms.gle/"):
        # Short URLs redirect, so entry IDs cannot be applied without following
        # the redirect. Never promise a prefilled form in this case.
        return base
    params = {"usp": "pp_url"}
    for field, content in ((destination.get("form_message_entry"), message),
                           (destination.get("form_email_entry"), destination.get("form_email"))):
        if field and ENTRY_ID.fullmatch(field) and content:
            params[field] = content
    fixed = destination.get("form_fixed_fields") or {}
    for key, value in fixed.items():
        if ENTRY_ID.fullmatch(str(key)) and isinstance(value, str):
            params[key] = value
    return base + "?" + urlencode(params)


def validate_destination(data):
    if not isinstance(data, dict):
        raise PromotionError("Butiran destinasi tidak sah")
    name = str(data.get("name") or "").strip()
    kind = str(data.get("kind") or "").strip()
    url = str(data.get("target_url") or "").strip()
    if not 1 <= len(name) <= 120 or kind not in {"telegram_group", "telegram_channel", "google_form"}:
        raise PromotionError("Nama atau jenis destinasi tidak sah")
    if len(url) > 2048:
        raise PromotionError("Link terlalu panjang")
    out = {"name": name, "kind": kind, "posting_permitted": data.get("posting_permitted") is True,
           "active": data.get("active", True) is True}
    if kind == "google_form":
        out["target_url"] = safe_form_url(url)
        out["telegram_chat_id"] = None
        email = str(data.get("form_email") or "").strip()
        if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            raise PromotionError("Alamat Gmail tidak sah")
        out["form_email"] = email or None
        for key in ("form_message_entry", "form_email_entry"):
            field = str(data.get(key) or "").strip()
            if field and not ENTRY_ID.fullmatch(field):
                raise PromotionError("Entry ID Google Form mesti bermula dengan entry. diikuti nombor")
            out[key] = field or None
        fixed = data.get("form_fixed_fields") or {}
        if not isinstance(fixed, dict) or len(fixed) > 15 or any(
            not ENTRY_ID.fullmatch(str(k)) or not isinstance(v, str) or len(v) > 500
            for k, v in fixed.items()
        ):
            raise PromotionError("Mapping Google Form tidak sah")
        out["form_fixed_fields"] = fixed
    else:
        p = urlparse(url)
        if p.scheme != "https" or p.hostname not in {"t.me", "telegram.me"} or not p.path.strip("/"):
            raise PromotionError("Link Telegram mesti https://t.me/...")
        out["target_url"] = url
        chat_id = str(data.get("telegram_chat_id") or "").strip()
        if not CHAT_ID.fullmatch(chat_id):
            raise PromotionError("Masukkan chat ID numerik atau @username yang sah. Link sahaja tak cukup.")
        out["telegram_chat_id"] = chat_id
        out.update(form_email=None, form_message_entry=None, form_email_entry=None,
                   form_fixed_fields={})
    return out


class PromotionCenter:
    def __init__(self, supabase_url, service_key, tenant_id, bot_token, admin_secret,
                 *, threads_app_id="", threads_app_secret="", token_key="", origin="", client=None):
        self.url = supabase_url.rstrip("/")
        self.key = service_key
        self.tenant = tenant_id
        self.bot_token = bot_token
        self.admin_secret = admin_secret
        self.app_id = threads_app_id
        self.app_secret = threads_app_secret
        self.token_key = token_key
        self.origin = origin.rstrip("/")
        self.client = client or httpx.Client(timeout=12, follow_redirects=False)

    def ready(self):
        return (bool(self.key and self.tenant and self.url.startswith("https://"))
                and (urlparse(self.url).hostname or "").endswith(".supabase.co"))

    def _db(self, table, method="GET", *, params=None, body=None):
        if not self.ready() or table not in TABLES:
            raise PromotionError("Promotion Center: Supabase belum dikonfigurasi", 503)
        query = {"tenant_id": "eq." + self.tenant, **(params or {})}
        headers = {"apikey": self.key, "Authorization": "Bearer " + self.key,
                   "Prefer": "return=representation"}
        try:
            res = self.client.request(method, f"{self.url}/rest/v1/{table}",
                                      params=query, json=body, headers=headers)
            if res.status_code >= 400:
                log.warning("[PROMO DB] table=%s method=%s code=%s", table, method, res.status_code)
                raise PromotionError("Database Promotion Center belum tersedia atau operasi ditolak", 503)
            return res.json() if res.content else []
        except httpx.HTTPError as exc:
            raise PromotionError("Tidak dapat sambung database Promotion Center", 503) from exc

    def rows(self, table, *, filters=None, columns="*", limit=100):
        return self._db(table, params={"select": columns, "limit": str(limit),
                                        **(filters or {})})

    def one(self, table, row_id, *, columns="*"):
        if not UUID_RE.fullmatch(str(row_id)):
            raise PromotionError("ID tidak sah")
        rows = self.rows(table, filters={"id": "eq." + str(row_id)}, columns=columns, limit=1)
        if not rows:
            raise PromotionError("Rekod tidak ditemui", 404)
        return rows[0]

    def insert(self, table, body):
        payload = [dict(x, tenant_id=self.tenant) for x in body] if isinstance(body, list) else dict(body, tenant_id=self.tenant)
        return self._db(table, "POST", body=payload)

    def patch(self, table, row_id, payload, *, state=None):
        params = {"id": "eq." + str(row_id)}
        if state:
            params["state"] = "eq." + state
        return self._db(table, "PATCH", params=params, body=payload)

    def state(self):
        return {
            "destinations": self.rows("promotion_destinations", limit=300),
            "threads_accounts": self.rows("promotion_threads_accounts",
                                          columns="id,username,provider_user_id,expires_at,created_at,active",
                                          filters={"active": "eq.true"}, limit=3),
            "templates": self.rows("promotion_templates", limit=100),
            "campaigns": self.rows("promotion_campaigns", limit=100,
                                   filters={"order": "created_at.desc"}),
            "deliveries": self.rows("promotion_deliveries", limit=500,
                                    filters={"order": "updated_at.desc"}),
            "threads_configured": bool(self.app_id and self.app_secret and self.token_key and self.origin),
            "auto_form_submission": False,
        }

    def save_destination(self, body):
        entry = validate_destination(body)
        rid = body.get("id")
        if rid:
            self.one("promotion_destinations", rid)
            rows = self.patch("promotion_destinations", rid, {**entry, "updated_at": datetime.now(timezone.utc).isoformat()})
        else:
            rows = self.insert("promotion_destinations", entry)
        return rows[0]

    def save_template(self, body):
        title = str(body.get("name") or "").strip()
        message = str(body.get("message") or "").strip()
        if not 1 <= len(title) <= 120 or not 1 <= len(message) <= 1800:
            raise PromotionError("Nama atau mesej template tidak sah (maksimum 1,800 aksara)")
        return self.insert("promotion_templates", {"name": title, "message": message})[0]

    def _telegram(self, method, payload):
        if not self.bot_token:
            raise PromotionError("Telegram bot token belum dikonfigurasi", 503)
        try:
            res = self.client.post(f"https://api.telegram.org/bot{self.bot_token}/{method}", json=payload)
            data = res.json()
            if not data.get("ok"):
                raise PromotionError("Telegram menolak mesej: semak akses bot dan kebenaran posting", 422)
            return data["result"]
        except (httpx.HTTPError, ValueError) as exc:
            raise PromotionError("Telegram tidak dapat disahkan; status penghantaran tidak pasti", 502) from exc

    def test_telegram(self, destination_id):
        dest = self.one("promotion_destinations", destination_id)
        if not dest["kind"].startswith("telegram_"):
            raise PromotionError("Test Connection hanya untuk Telegram")
        if not dest.get("telegram_chat_id"):
            raise PromotionError("Chat ID Telegram belum disimpan")
        chat = self._telegram("getChat", {"chat_id": dest["telegram_chat_id"]})
        if chat.get("type") not in {"group", "supergroup", "channel"}:
            raise PromotionError("Destinasi bukan group atau channel", 422)
        # getChat confirms visibility only; send permission is ultimately checked
        # by Telegram when Send Campaign runs, not assumed here.
        return {"accessible": True, "title": chat.get("title", ""),
                "message": "Bot boleh akses destinasi. Posting masih tertakluk pada permission admin."}

    def create_campaign(self, body):
        if not isinstance(body, dict):
            raise PromotionError("Kempen tidak sah")
        title = str(body.get("title") or "").strip()
        message = str(body.get("message") or "").strip()
        destination_ids = body.get("destination_ids") or []
        account_ids = body.get("threads_account_ids") or []
        thread_captions = body.get("threads_captions") or {}
        if not 1 <= len(title) <= 120 or not 1 <= len(message) <= 1800:
            raise PromotionError("Tajuk/mesej diperlukan (1–1,800 aksara)")
        if (not isinstance(destination_ids, list) or not isinstance(account_ids, list)
                or not destination_ids + account_ids or len(destination_ids) + len(account_ids) > MAX_DESTINATIONS
                or len(set(destination_ids)) != len(destination_ids)
                or len(set(account_ids)) != len(account_ids)):
            raise PromotionError("Pilih 1 hingga 40 destinasi tanpa duplicate")
        if any(not UUID_RE.fullmatch(str(i)) for i in destination_ids + account_ids):
            raise PromotionError("ID destinasi tidak sah")
        if (not isinstance(thread_captions, dict) or any(
            i not in account_ids or not isinstance(c, str) or not 1 <= len(c.strip()) <= THREADS_TEXT_MAX
            for i, c in thread_captions.items()
        )):
            raise PromotionError("Caption custom Threads tidak sah (maksimum 500 aksara)")
        destinations = self.rows("promotion_destinations", limit=300)
        accounts = self.rows("promotion_threads_accounts",
                             columns="id,username,expires_at,active", limit=3,
                             filters={"active": "eq.true"})
        destmap = {d["id"]: d for d in destinations}
        accmap = {a["id"]: a for a in accounts}
        if any(i not in destmap or not destmap[i]["active"] or not destmap[i]["posting_permitted"]
               for i in destination_ids):
            raise PromotionError("Destinasi tidak aktif / belum disahkan dibenarkan posting")
        if any(i not in accmap for i in account_ids):
            raise PromotionError("Akaun Threads tidak disambungkan")
        if account_ids and any(len(thread_captions.get(i, message)) > THREADS_TEXT_MAX for i in account_ids):
            raise PromotionError("Caption Threads maksimum 500 aksara. Sediakan mesej yang lebih ringkas.")
        try:
            scheduled = datetime.fromisoformat(str(body.get("scheduled_for") or "").replace("Z", "+00:00"))
            if scheduled.tzinfo is None:
                raise ValueError
        except ValueError:
            scheduled = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        if scheduled > now + timedelta(days=60):
            raise PromotionError("Jadual maksimum 60 hari ke hadapan")
        # Avoid accidentally reposting an identical campaign to the same
        # destination within 12 hours, even when the owner clicks twice.
        recent = self.rows("promotion_campaigns", limit=200,
                           filters={"created_at": "gte." + (now - timedelta(hours=12)).isoformat()})
        for campaign in recent:
            if campaign.get("message") != message or campaign.get("state") == "cancelled":
                continue
            deliveries = self.rows("promotion_deliveries", limit=100,
                                   filters={"campaign_id": "eq." + campaign["id"]})
            for d in deliveries:
                if d.get("destination_id") in destination_ids or d.get("threads_account_id") in account_ids:
                    raise PromotionError("Mesej sama dah dijadualkan/dihantar ke destinasi dipilih dalam 12 jam. Semak History.", 409)
        campaign = self.insert("promotion_campaigns", {
            "title": title, "message": message, "scheduled_for": max(scheduled, now).isoformat(),
            "state": "queued"})[0]
        rows = ([{"campaign_id": campaign["id"], "destination_id": i} for i in destination_ids]
                + [{"campaign_id": campaign["id"], "threads_account_id": i,
                    "message_override": thread_captions.get(i)} for i in account_ids])
        try:
            self.insert("promotion_deliveries", rows)
        except PromotionError:
            self.patch("promotion_campaigns", campaign["id"], {"state": "cancelled"})
            raise
        return campaign

    def _send_threads(self, account, message):
        token = self.decrypt_token(account["encrypted_token"])
        if account.get("expires_at") and datetime.fromisoformat(account["expires_at"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
            raise PromotionError("Threads token tamat tempoh. Sambungkan akaun semula.", 422)
        headers = {"Authorization": "Bearer " + token}
        try:
            container = self.client.post("https://graph.threads.net/v1.0/me/threads",
                                         headers=headers, data={"media_type": "TEXT", "text": message})
            container.raise_for_status()
            creation_id = container.json()["id"]
            published = self.client.post("https://graph.threads.net/v1.0/me/threads_publish",
                                         headers=headers, data={"creation_id": creation_id})
            published.raise_for_status()
            return str(published.json()["id"])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise PromotionError("Threads API gagal atau status tidak pasti; semak akaun sebelum retry", 502) from exc

    def run_due(self, *, campaign_id=None):
        if campaign_id:
            campaigns = [self.one("promotion_campaigns", campaign_id)]
        else:
            campaigns = self.rows("promotion_campaigns", limit=10,
                                  filters={"state": "eq.queued", "scheduled_for": "lte." + datetime.now(timezone.utc).isoformat(),
                                           "order": "scheduled_for.asc"})
        processed = 0
        for campaign in campaigns:
            if campaign.get("state") != "queued":
                continue
            scheduled = datetime.fromisoformat(campaign["scheduled_for"].replace("Z", "+00:00"))
            if scheduled > datetime.now(timezone.utc):
                continue
            claim = self.patch("promotion_campaigns", campaign["id"], {"state": "running"}, state="queued")
            if not claim:
                continue
            deliveries = self.rows("promotion_deliveries", limit=MAX_DESTINATIONS,
                                   filters={"campaign_id": "eq." + campaign["id"], "state": "eq.queued"})
            for delivery in deliveries:
                claim_delivery = self.patch("promotion_deliveries", delivery["id"],
                                            {"state": "processing", "attempt_count": delivery["attempt_count"] + 1},
                                            state="queued")
                if not claim_delivery:
                    continue
                state, external_id, error = "failed", None, None
                try:
                    if delivery.get("destination_id"):
                        dest = self.one("promotion_destinations", delivery["destination_id"])
                        if not dest["active"] or not dest["posting_permitted"]:
                            state, error = "skipped", "Destinasi dinyahaktifkan / tiada kebenaran"
                        elif dest["kind"] == "google_form":
                            # No misleading claim of automatic third-party form submission.
                            state = "manual"
                            external_id = prefilled_form_url(dest, campaign["message"])
                        else:
                            sent = self._telegram("sendMessage", {"chat_id": dest["telegram_chat_id"],
                                                                  "text": campaign["message"],
                                                                  "disable_web_page_preview": True})
                            state, external_id = "sent", str(sent.get("message_id", ""))
                    else:
                        acc = self.one("promotion_threads_accounts", delivery["threads_account_id"])
                        if not acc.get("active", True):
                            state, error = "skipped", "Akaun Threads telah disconnected"
                        else:
                            external_id = self._send_threads(acc, delivery.get("message_override") or campaign["message"])
                            state = "sent"
                except PromotionError as exc:
                    error = str(exc)
                    state = "unknown" if exc.status == 502 else "failed"
                except Exception:
                    log.exception("[PROMO] Unexpected delivery failure id=%s", delivery["id"])
                    error, state = "Server gagal menghantar; semak sebelum retry", "unknown"
                self.patch("promotion_deliveries", delivery["id"], {
                    "state": state, "external_id": external_id, "error_message": error,
                    "sent_at": datetime.now(timezone.utc).isoformat() if state == "sent" else None,
                    "updated_at": datetime.now(timezone.utc).isoformat()})
                processed += 1
                # Bound sending speed to avoid Telegram flood limits.
                time.sleep(1)
            self.patch("promotion_campaigns", campaign["id"], {"state": "completed",
                       "finished_at": datetime.now(timezone.utc).isoformat()})
        return processed

    def retry_failed(self, campaign_id):
        campaign = self.one("promotion_campaigns", campaign_id)
        if campaign["state"] != "completed":
            raise PromotionError("Hanya kempen selesai boleh retry")
        rows = self.rows("promotion_deliveries", filters={"campaign_id": "eq." + campaign_id})
        failed = [d for d in rows if d["state"] == "failed" and d["attempt_count"] < 5]
        if not failed:
            raise PromotionError("Tiada penghantaran gagal yang boleh retry")
        for delivery in failed:
            self.patch("promotion_deliveries", delivery["id"], {"state": "queued", "error_message": None})
        self.patch("promotion_campaigns", campaign_id, {"state": "queued",
                   "scheduled_for": datetime.now(timezone.utc).isoformat(), "finished_at": None})
        return self.run_due(campaign_id=campaign_id)

    def cancel_campaign(self, campaign_id):
        campaign = self.one("promotion_campaigns", campaign_id)
        if campaign["state"] != "queued":
            raise PromotionError("Hanya kempen yang belum bermula boleh dibatalkan")
        if not self.patch("promotion_campaigns", campaign_id, {"state": "cancelled"}, state="queued"):
            raise PromotionError("Kempen sudah mula dihantar; tidak boleh dibatalkan", 409)
        for delivery in self.rows("promotion_deliveries", filters={"campaign_id": "eq." + campaign_id}):
            self.patch("promotion_deliveries", delivery["id"], {"state": "skipped"}, state="queued")
        return {"ok": True}

    def disconnect_threads(self, account_id):
        self.one("promotion_threads_accounts", account_id, columns="id")
        # Wipe the usable token but keep the row for historical campaign IDs.
        return self.patch("promotion_threads_accounts", account_id,
                          {"active": False, "encrypted_token": "disconnected"})

    def threads_ready(self):
        return bool(self.app_id and self.app_secret and len(self.token_key) >= 32 and self.origin
                    and urlparse(self.origin).scheme == "https")

    def encrypt_token(self, token):
        from cryptography.fernet import Fernet
        import base64
        key = base64.urlsafe_b64encode(hashlib.sha256(self.token_key.encode()).digest())
        return Fernet(key).encrypt(token.encode()).decode()

    def decrypt_token(self, value):
        from cryptography.fernet import Fernet
        import base64
        key = base64.urlsafe_b64encode(hashlib.sha256(self.token_key.encode()).digest())
        return Fernet(key).decrypt(value.encode()).decode()

    def begin_threads_oauth(self):
        if not self.threads_ready():
            raise PromotionError("Set THREADS_APP_ID, THREADS_APP_SECRET, PROMOTION_TOKEN_KEY dan PROMOTION_PUBLIC_URL di Render", 503)
        if len(self.rows("promotion_threads_accounts", columns="id", limit=4,
                         filters={"active": "eq.true"})) >= THREADS_LIMIT:
            raise PromotionError("Maksimum 3 akaun Threads. Putuskan akaun lama dahulu.")
        state = URLSafeTimedSerializer(self.admin_secret, salt="berry-threads-oauth").dumps({
            "tenant": self.tenant, "nonce": secrets.token_urlsafe(18)})
        params = {"client_id": self.app_id,
                  "redirect_uri": self.origin + "/api/dashboard/promotion/threads/callback",
                  "scope": "threads_basic,threads_content_publish", "response_type": "code", "state": state}
        return "https://threads.net/oauth/authorize?" + urlencode(params)

    def finish_threads_oauth(self, state, code):
        if not self.threads_ready():
            raise PromotionError("Threads OAuth belum dikonfigurasi", 503)
        try:
            payload = URLSafeTimedSerializer(self.admin_secret, salt="berry-threads-oauth").loads(state, max_age=600)
        except (BadSignature, SignatureExpired) as exc:
            raise PromotionError("Threads OAuth state tamat tempoh / tidak sah") from exc
        if payload.get("tenant") != self.tenant or len(code or "") > 1000:
            raise PromotionError("Threads OAuth ditolak")
        redirect_uri = self.origin + "/api/dashboard/promotion/threads/callback"
        try:
            res = self.client.post("https://graph.threads.net/oauth/access_token", data={
                "client_id": self.app_id, "client_secret": self.app_secret,
                "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code})
            res.raise_for_status()
            short = res.json()["access_token"]
            long = self.client.get("https://graph.threads.net/access_token",
                                   params={"grant_type": "th_exchange_token", "client_secret": self.app_secret,
                                           "access_token": short},
                                   headers={"Authorization": "Bearer " + short})
            long.raise_for_status()
            token = long.json().get("access_token", short)
            expires_in = int(long.json().get("expires_in", 3600))
            profile = self.client.get("https://graph.threads.net/v1.0/me",
                                      params={"fields": "id,username"},
                                      headers={"Authorization": "Bearer " + token})
            profile.raise_for_status()
            account = profile.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PromotionError("Threads OAuth gagal. Semak Meta App permission dan redirect URL.", 502) from exc
        existing = self.rows("promotion_threads_accounts", limit=4,
                             filters={"provider_user_id": "eq." + str(account["id"])})
        record = {"provider_user_id": str(account["id"]), "username": account.get("username") or str(account["id"]),
                  "encrypted_token": self.encrypt_token(token),
                  "active": True,
                  "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()}
        if existing:
            self.patch("promotion_threads_accounts", existing[0]["id"], record)
        else:
            if len(self.rows("promotion_threads_accounts", columns="id", limit=4,
                             filters={"active": "eq.true"})) >= THREADS_LIMIT:
                raise PromotionError("Maksimum 3 akaun Threads")
            self.insert("promotion_threads_accounts", record)
        return account.get("username", "Threads")


def register_promotion_routes(app, promo, check_secret):
    routes = Blueprint("berry_promotion", __name__, url_prefix="/api/dashboard/promotion")

    @routes.before_request
    def guard():
        if request.endpoint == "berry_promotion.threads_callback":
            return None  # OAuth state is signed and time-limited.
        ok, _ = check_secret()
        if not ok:
            return jsonify(error="Dashboard authentication required"), 401
        return None

    @routes.errorhandler(PromotionError)
    def on_promo_error(error):
        return jsonify(error=str(error)), error.status

    @routes.get("/state")
    def state():
        return jsonify(promo.state())

    @routes.post("/destination")
    def destination():
        return jsonify(promo.save_destination(request.get_json(silent=True))), 200

    @routes.post("/destination/<rid>/test")
    def test_destination(rid):
        return jsonify(promo.test_telegram(rid))

    @routes.post("/template")
    def template():
        return jsonify(promo.save_template(request.get_json(silent=True) or {}))

    @routes.post("/campaign")
    def campaign():
        created = promo.create_campaign(request.get_json(silent=True))
        # Dispatch now only if due. Scheduled campaigns are picked up on tick.
        if datetime.fromisoformat(created["scheduled_for"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            _workers.submit(promo.run_due, campaign_id=created["id"])
        return jsonify(campaign=created)

    @routes.post("/campaign/<rid>/retry")
    def retry(rid):
        campaign = promo.one("promotion_campaigns", rid)
        failed = promo.rows("promotion_deliveries", filters={"campaign_id": "eq." + rid,
                                                         "state": "eq.failed"})
        if campaign["state"] != "completed" or not failed:
            raise PromotionError("Tiada penghantaran gagal untuk retry", 409)
        _workers.submit(promo.retry_failed, rid)
        return jsonify(queued=True)

    @routes.post("/campaign/<rid>/cancel")
    def cancel(rid):
        return jsonify(promo.cancel_campaign(rid))

    @routes.post("/threads/connect")
    def threads_connect():
        return jsonify(url=promo.begin_threads_oauth())

    @routes.post("/threads/<rid>/disconnect")
    def threads_disconnect(rid):
        promo.disconnect_threads(rid)
        return jsonify(ok=True)

    @routes.get("/threads/callback")
    def threads_callback():
        try:
            if request.args.get("error"):
                raise PromotionError("Threads menolak sambungan")
            promo.finish_threads_oauth(request.args.get("state", ""), request.args.get("code", ""))
            return redirect(promo.origin + "/dashboard#promotion-connected", code=302)
        except PromotionError as exc:
            log.warning("Threads OAuth error: %s", type(exc).__name__)
            return jsonify(error=str(exc)), exc.status

    app.register_blueprint(routes)
