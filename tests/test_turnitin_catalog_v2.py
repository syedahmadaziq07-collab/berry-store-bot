"""Regressions for the approved nine-service checkout and two-report bundles."""
import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

with patch.dict(sys.modules, {"httpx": ModuleType("httpx")}):
    from berry_turnitin_flow import TurnitinFlow
from turnitin_catalog import SERVICE_CODES, SERVICE_LABELS, available_stock, is_bundle

ROOT = Path(__file__).resolve().parents[1]
UPGRADE = (ROOT / "docs/sql/berry_turnitin_catalog_v2.sql").read_text(encoding="utf-8")


class CatalogV2Tests(TestCase):
    def test_every_service_exists_in_upgrade(self):
        self.assertEqual(len(SERVICE_CODES), 9)
        for code in SERVICE_CODES:
            self.assertIn("'" + code + "'", UPGRADE)
        self.assertEqual(list(SERVICE_LABELS)[0:2], ["similarity", "ai"])
        self.assertTrue(is_bundle("bundle_basic"))
        self.assertFalse(is_bundle("gptzero_basic"))
        self.assertEqual(available_stock({"stock": 40, "available_stock": 38}), 38)

    def test_prices_and_no_unwanted_disclaimer(self):
        self.assertIn("3.10,40,true,15", UPGRADE)
        self.assertIn("9.00,40,true,15", UPGRADE)
        for price in ("4.00", "5.00", "6.00", "7.00", "8.00", "15.00"):
            self.assertIn(price + ",40,true,15", UPGRADE)
        self.assertNotIn("Bahasa Indonesia atau English", UPGRADE)
        self.assertNotIn("Skor AI ialah anggaran", UPGRADE)
        self.assertIn("DO NOT update stock/enabled on conflict", UPGRADE)

    def test_component_stock_is_atomic_and_not_double_approved(self):
        self.assertIn("stock=stock-1", UPGRADE)
        self.assertIn("stock=stock-component.quantity", UPGRADE)
        self.assertIn("AND stock>=component.quantity", UPGRADE)
        self.assertIn("already_approved',true", UPGRADE)
        self.assertIn("FROM berry_private.turnitin_plan_components", UPGRADE)
        self.assertIn("LEAST(p.stock", UPGRADE)
        self.assertIn("staged_report_file_id", UPGRADE)

    def test_three_category_mockup_and_service_drilldown(self):
        class FakeBackend:
            def rpc(self, name, **kwargs):
                assert name == "catalog"
                return [{"code": code, "title": label, "description": "Test desc for plan",
                         "price_myr": "4", "stock": 40, "available_stock": 38,
                         "enabled": True} for code, label in SERVICE_LABELS.items()]

        buttons = []
        class FakeButton:
            def __init__(self, label, callback_data):
                buttons.append((label, callback_data))
        class FakeMarkup:
            def __init__(self, rows):
                self.rows = rows
        telegram_stub = ModuleType("telegram")
        telegram_stub.InlineKeyboardButton = FakeButton
        telegram_stub.InlineKeyboardMarkup = FakeMarkup

        user = SimpleNamespace(id=17)
        update = SimpleNamespace(
            effective_user=user,
            effective_chat=SimpleNamespace(type="private"),
            callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
        )
        flow = TurnitinFlow(FakeBackend(),17,checkout_enabled=True,admin_only=False)
        with patch.dict(sys.modules, {"telegram": telegram_stub}):
            asyncio.run(flow.menu(update,SimpleNamespace()))
            msg = update.callback_query.edit_message_text.await_args.args[0]
            self.assertIn("🍓 BERRY STORE",msg)
            self.assertIn("Pilih kategori",msg)
            self.assertNotIn("Stock 38",msg)
            self.assertEqual([c for _,c in buttons], [
                "turnitin:plan:similarity", "turnitin:category:ai",
                "turnitin:category:bundle", "turnitin:orders", "home"])

            buttons.clear()
            update.callback_query.edit_message_text.reset_mock()
            asyncio.run(flow.category(update,SimpleNamespace(),"ai"))
            msg = update.callback_query.edit_message_text.await_args.args[0]
            self.assertIn("🤖 AI DETECTION",msg)
            self.assertIn("Stock 38",msg)
            self.assertEqual([c for _,c in buttons], [
                "turnitin:plan:ai", "turnitin:plan:gptzero_basic",
                "turnitin:plan:gptzero_standard", "turnitin:plan:gptzero_premium", "turnitin"])

            buttons.clear()
            asyncio.run(flow.category(update,SimpleNamespace(),"bundle"))
            self.assertEqual([c for _,c in buttons], [
                "turnitin:plan:bundle_basic", "turnitin:plan:bundle_standard",
                "turnitin:plan:bundle_premium", "turnitin:plan:bundle_turnitin_ai", "turnitin"])

            for code, back in [("similarity","turnitin"),
                               ("gptzero_basic","turnitin:category:ai"),
                               ("bundle_basic","turnitin:category:bundle")]:
                buttons.clear()
                asyncio.run(flow.plan(update,SimpleNamespace(),code))
                msg = update.callback_query.edit_message_text.await_args.args[0]
                self.assertIn("Test desc for plan",msg)
                self.assertIn("Harga: RM4.00",msg)
                self.assertIn("Stock: 38",msg)
                self.assertEqual(buttons[-1][1],back)

    def test_bot_routes_category_callbacks(self):
        bot = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn('action.startswith("turnitin:category:")', bot)
        self.assertIn("flow.category(update, context",bot)

    def test_bundle_sends_two_reports_only_after_second_pdf(self):
        oid = "TT" + "B"*24
        called = []
        class FakeBackend:
            def rpc(self, name, **kwargs):
                called.append(name)
                if name=="delivery_stage":
                    return {"staged": called.count(name) == 1}
                if name=="delivery_claim":
                    return {"user_id": 101, "plan": "bundle_basic",
                            "staged_report_file_id": "pdf_one", "progress_message_id": None}
                if name=="delivery_complete":
                    return True
                raise AssertionError(name)

        msg = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=msg)
        bot = SimpleNamespace(send_document=AsyncMock())
        context = SimpleNamespace(bot=bot, user_data={
            "turnitin_admin_delivery":oid, "turnitin_admin_bundle":oid})
        flow = TurnitinFlow(FakeBackend(),1)
        file1 = SimpleNamespace(mime_type="application/pdf", file_size=150,file_id="pdf_one")
        file2 = SimpleNamespace(mime_type="application/pdf", file_size=150,file_id="pdf_two")

        asyncio.run(flow.report(update,context,file1))
        bot.send_document.assert_not_awaited()
        self.assertEqual(context.user_data["turnitin_admin_delivery"],oid)
        asyncio.run(flow.report(update,context,file2))
        self.assertEqual(bot.send_document.await_count,2)
        self.assertEqual(bot.send_document.await_args_list[0].kwargs["document"],"pdf_one")
        self.assertEqual(bot.send_document.await_args_list[1].kwargs["document"],"pdf_two")
        self.assertEqual(called, ["delivery_stage","delivery_stage","delivery_claim","delivery_complete"])
        self.assertNotIn("turnitin_admin_delivery",context.user_data)
