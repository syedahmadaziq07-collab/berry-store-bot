"""Promotion Center unit tests: no external Telegram, Threads or Google requests."""
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from flask import Flask, request

from promotion_center import (PromotionCenter, PromotionError, prefilled_form_url,
                              register_promotion_routes, safe_form_url, validate_destination)


class MemoryPromotion(PromotionCenter):
    def __init__(self):
        super().__init__("https://project.supabase.co", "service-key", str(uuid4()), "bot-key",
                         "a-secret-longer-than-24-characters", client=object())
        self.data = {t: [] for t in ("promotion_destinations", "promotion_threads_accounts",
                                     "promotion_templates", "promotion_campaigns", "promotion_deliveries")}
        self.sent = []

    def _db(self, table, method="GET", *, params=None, body=None):
        if method == "POST":
            payloads = body if isinstance(body, list) else [body]
            rows=[]
            for p in payloads:
                row={"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                     "attempt_count": 0, **({"state":"queued"} if table=="promotion_deliveries" else {}), **p}
                self.data[table].append(row)
                rows.append(row)
            return rows
        query = params or {}
        selected=list(self.data[table])
        for key, condition in query.items():
            if key in {"select", "limit", "order"}:
                continue
            if condition.startswith("eq."):
                selected=[r for r in selected if str(r.get(key)).lower() == condition[3:].lower()]
        if method == "PATCH":
            for row in selected:
                row.update(body)
            return selected
        if method == "DELETE":
            for row in selected:
                self.data[table].remove(row)
            return selected
        if query.get("limit"):
            selected=selected[:int(query["limit"])]
        if "select" in query and query["select"] != "*":
            return [{k: r.get(k) for k in query["select"].split(",")} for r in selected]
        return selected

    def _telegram(self, method, payload):
        self.sent.append((method, payload))
        return {"message_id": 199, "type": "channel", "title": "Verified Group"}


class PromotionCenterTests(TestCase):
    def test_google_forms_url_avoids_untrusted_hosts(self):
        self.assertEqual(safe_form_url("https://forms.gle/aBcD1234"), "https://forms.gle/aBcD1234")
        for url in ["http://docs.google.com/forms/d/e/123/viewform",
                    "https://evil.com/forms/d/e/123/viewform",
                    "https://docs.google.com.evil.com/forms/d/e/123/viewform",
                    "https://docs.google.com@evil.com/forms/d/e/123/viewform"]:
            with self.subTest(url=url), self.assertRaises(PromotionError):
                safe_form_url(url)

    def test_form_prefill_stays_manual_and_maps_message_and_email(self):
        dest = validate_destination({
            "name": "IPG Confession", "kind": "google_form",
            "target_url": "https://docs.google.com/forms/d/e/123/viewform",
            "form_email": "owner@gmail.com", "form_email_entry": "entry.987",
            "form_message_entry": "entry.123", "posting_permitted": True,
        })
        url = prefilled_form_url(dest, "Berry Store & Turnitin")
        self.assertIn("entry.123=Berry+Store+%26+Turnitin", url)
        self.assertIn("entry.987=owner%40gmail.com", url)

    def test_telegram_requires_chat_id_not_just_group_link(self):
        with self.assertRaisesRegex(PromotionError, "chat ID"):
            validate_destination({"kind": "telegram_group", "name": "Student Group",
                                  "target_url": "https://t.me/groupname"})

    def test_campaign_does_not_submit_google_forms_and_reports_each_destination(self):
        promo = MemoryPromotion()
        telegram = promo.save_destination({"kind": "telegram_group", "name": "Student Group",
            "target_url": "https://t.me/berries_group", "telegram_chat_id": "-1001234567890",
            "posting_permitted": True})
        form = promo.save_destination({"kind": "google_form", "name": "IPG Confession",
            "target_url": "https://forms.gle/aBcD1234", "posting_permitted": True})
        campaign = promo.create_campaign({"title": "November", "message": "Promosi Berry Store",
                                          "destination_ids": [telegram["id"], form["id"]]})
        with patch("promotion_center.time.sleep"):
            self.assertEqual(promo.run_due(campaign_id=campaign["id"]), 2)
        deliveries=promo.data["promotion_deliveries"]
        self.assertEqual({d["state"] for d in deliveries}, {"sent", "manual"})
        self.assertEqual(len(promo.sent), 1)
        self.assertEqual(promo.sent[0][1]["chat_id"], "-1001234567890")
        self.assertEqual(promo.data["promotion_campaigns"][0]["state"], "completed")

    def test_duplicate_protection_and_permission_gate(self):
        promo = MemoryPromotion()
        unapproved = promo.save_destination({"kind": "telegram_channel", "name": "Channel",
            "target_url": "https://t.me/berries_test", "telegram_chat_id": "@berries_test",
            "posting_permitted": False})
        with self.assertRaises(PromotionError):
            promo.create_campaign({"title": "Test", "message": "Hello",
                                   "destination_ids": [unapproved["id"]]})
        promo.patch("promotion_destinations", unapproved["id"], {"posting_permitted": True})
        payload={"title": "Test", "message": "Hello", "destination_ids": [unapproved["id"]]}
        promo.create_campaign(payload)
        with self.assertRaisesRegex(PromotionError, "12 jam"):
            promo.create_campaign(payload)

    def test_backend_auth_and_no_threads_token_in_state(self):
        app=Flask(__name__)
        promo=MemoryPromotion()
        register_promotion_routes(app, promo,
                                  lambda: (request.headers.get("X-Dashboard-Secret") == "admin", ""))
        client=app.test_client()
        self.assertEqual(client.get("/api/dashboard/promotion/state").status_code, 401)
        good=client.get("/api/dashboard/promotion/state", headers={"X-Dashboard-Secret":"admin"})
        self.assertEqual(good.status_code, 200)
        self.assertNotIn("encrypted_token", good.get_data(as_text=True))
        unauth=client.post("/api/dashboard/promotion/campaign",json={"title":"x","message":"hi"})
        self.assertEqual(unauth.status_code,401)

    def test_threads_connect_requires_owner_meta_credentials(self):
        with self.assertRaisesRegex(PromotionError, "THREADS_APP_ID"):
            MemoryPromotion().begin_threads_oauth()

    def test_threads_token_is_encrypted_at_rest(self):
        promo=MemoryPromotion()
        promo.token_key="a-strong-separate-token-key-for-threads-123"
        sealed=promo.encrypt_token("short-lived-secret")
        self.assertNotIn("short-lived-secret", sealed)
        self.assertEqual(promo.decrypt_token(sealed),"short-lived-secret")

    def test_each_threads_account_can_use_its_own_caption(self):
        promo=MemoryPromotion()
        a,b=str(uuid4()),str(uuid4())
        for i in [a,b]:
            promo.data["promotion_threads_accounts"].append({"id":i,"tenant_id":promo.tenant,
                "username":"berry","provider_user_id":i,"active":True,"encrypted_token":"encrypted"})
        campaign=promo.create_campaign({"title":"Thread ideas","message":"General promo",
            "threads_account_ids":[a,b],"threads_captions":{a:"Only for Account A"}})
        posted=[]
        promo._send_threads=lambda account,message: posted.append(message) or "post123"
        with patch("promotion_center.time.sleep"):
            self.assertEqual(promo.run_due(campaign_id=campaign["id"]),2)
        self.assertEqual(posted,["Only for Account A","General promo"])

    def test_campaign_scheduled_in_future_is_not_sent_early(self):
        from datetime import timedelta
        promo=MemoryPromotion()
        d=promo.save_destination({"kind":"telegram_channel","name":"Only Channel",
            "target_url":"https://t.me/channelxyz","telegram_chat_id":"@channelxyz",
            "posting_permitted":True})
        due=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
        campaign=promo.create_campaign({"title":"Tomorrow","message":"Hello",
            "destination_ids":[d["id"]],"scheduled_for":due})
        self.assertEqual(promo.run_due(campaign_id=campaign["id"]),0)
        self.assertEqual(promo.sent,[])
        self.assertEqual(campaign["state"],"queued")

    def test_new_tables_server_only_and_navigation_integrated(self):
        root=Path(__file__).resolve().parents[1]
        sql=(root/"docs/sql/berry_promotion_center.sql").read_text(encoding="utf-8")
        html=(root/"dashboard.html").read_text(encoding="utf-8")
        bot=(root/"bot.py").read_text(encoding="utf-8")
        for table in ("promotion_destinations", "promotion_threads_accounts", "promotion_templates",
                      "promotion_campaigns", "promotion_deliveries"):
            self.assertIn("ALTER TABLE public."+table+" ENABLE ROW LEVEL SECURITY",sql)
        self.assertIn("FROM PUBLIC, anon, authenticated",sql)
        self.assertIn('id="page-promotion"',html)
        self.assertIn('data-page="promotion"',html)
        self.assertIn('promoAPI(\'/campaign\'',html)
        self.assertIn('register_promotion_routes(_app, _promotion_center, _check_dashboard_secret)',bot)


if __name__ == "__main__":
    import unittest
    unittest.main()
