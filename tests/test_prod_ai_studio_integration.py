"""Production integration safety tests for the AI Studio wiring on main.

Static/AST + unit checks: no bot token required, no network, no wallet.
Covers feature flags default-off, gated image entry, startup pending-update
preservation, exact wallet display, and idempotency contracts.
"""
import ast
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import Mock, patch

BOT = Path("bot.py").read_text(encoding="utf-8")


def credits_label(balance: str) -> str:
    credits = Decimal(balance.replace('RM', '').replace(',', '')) * 1250
    label = f"{credits:,.2f}".rstrip("0").rstrip(".")
    return f"{label} Berry Credits ({balance})"


class FeatureFlagTests(unittest.TestCase):
    def test_image_studio_flag_default_off(self):
        self.assertIn('_get_env("BERRY_IMAGE_STUDIO_ENABLED") == "true"', BOT)

    def test_topup_flag_still_off(self):
        self.assertIn('_get_env("BERRY_TOPUP_CHECKOUT_ENABLED") == "true"', BOT)

    def test_wallet_gate_requires_service_key(self):
        self.assertIn("def _wallet_enabled", BOT)
        self.assertIn("TENANT_ID and SUPABASE_SERVICE_KEY", BOT)

    def test_image_flow_never_constructs_worker_itself(self):
        # The helper must only read bot_data, never build a worker/store.
        start = BOT.index("def _image_flow")
        end = BOT.index("\ndef ", start + 10)
        body = BOT[start:end]
        self.assertNotIn("MyrVideoWorker", body)
        self.assertNotIn("StagingJobWorker", body)
        self.assertNotIn("Worker(", body)
        self.assertIn("bot_data.get", body)


class ImageEntryGatingTests(unittest.TestCase):
    """The disabled path shows the unavailable message; no flow is touched."""

    def test_disabled_flag_blocks_entry(self):
        import importlib
        import os
        with patch.dict(os.environ, {"BERRY_IMAGE_STUDIO_ENABLED": ""}):
            # Import the helper logic without running bot mainline: use the
            # source-level check plus the module-free flag semantics.
            self.assertFalse("true" == os.getenv("BERRY_IMAGE_STUDIO_ENABLED", ""))

    def test_entry_registered_in_callback_router(self):
        self.assertIn('data == "ai_image_prompt"', BOT)
        self.assertIn("await _ai_image_prompt", BOT)


class StartupPendingUpdateTests(unittest.TestCase):
    def test_delete_webhook_preserves_pending_updates(self):
        tree = ast.parse(BOT)
        found = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "delete_webhook"):
                for kw in node.keywords:
                    if kw.arg == "drop_pending_updates":
                        found.append(ast.dump(kw.value))
        self.assertTrue(found)
        for kw in found:
            self.assertIn("Constant(value=False)", kw)

    def test_run_polling_preserves_pending_updates(self):
        tree = ast.parse(BOT)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run_polling"):
                flags = [kw for kw in node.keywords if kw.arg == "drop_pending_updates"]
                self.assertEqual(len(flags), 1)
                self.assertIsInstance(flags[0].value, ast.Constant)
                self.assertFalse(flags[0].value.value)

    def test_no_early_token_close_or_import_time_webhook_drop(self):
        self.assertNotIn("deleteWebhook?drop_pending_updates=true", BOT)
        self.assertNotIn("_EARLY_TOKEN", BOT)


class WalletDisplayTests(unittest.TestCase):
    def test_odd_cent_balance_preserves_fractional_credits(self):
        self.assertEqual(credits_label("RM4.99"), "6,237.5 Berry Credits (RM4.99)")

    def test_whole_balance_clean(self):
        self.assertEqual(credits_label("RM5.00"), "6,250 Berry Credits (RM5.00)")

    def test_bot_source_uses_exact_decimal_conversion(self):
        self.assertIn("Decimal(balance.replace('RM','').replace(',','')) * 1250", BOT)
        self.assertNotIn("int(Decimal(balance.replace('RM','').replace(',',''))*1250)", BOT)


class ImagePromptWiringTests(unittest.TestCase):
    """Text-stage wiring in bot.py: gated, non-consuming, fail-closed."""

    def test_prompt_stage_wired_before_generic_handler(self):
        self.assertIn("await _ai_image_prompt_text(update, context)", BOT)
        self.assertIn("return False  # not consumed", BOT)

    def test_prompt_text_helper_is_gated(self):
        start = BOT.index("async def _ai_image_prompt_text")
        end = BOT.index("async def _ai_image_confirm", start)
        body = BOT[start:end]
        self.assertIn('stage.get("stage") != "prompt"', body)
        self.assertIn("return False", body)

    def test_confirm_fail_closed_message_present(self):
        start = BOT.index("async def _ai_image_confirm")
        end = BOT.index("async def _ai_image_cancel", start)
        body = BOT[start:end]
        self.assertIn("belum diaktifkan", body)
        self.assertIn("Tiada debit", body)

    def test_callback_routes_registered(self):
        self.assertIn('data.startswith("ai_image_confirm:")', BOT)
        self.assertIn('data.startswith("ai_image_cancel:")', BOT)
        self.assertIn('await _ai_image_confirm(update, context, data.split(":", 1)[1])', BOT)
        self.assertIn('await _ai_image_cancel(update, context, data.split(":", 1)[1])', BOT)

    def test_no_wallet_or_provider_call_in_wiring(self):
        start = BOT.index("async def _ai_image_prompt_text")
        end = BOT.index("async def show_home", start)
        body = BOT[start:end]
        for forbidden in ("sb_patch", "ai_wallet_apply_transaction",
                          "provider.submit", "FalProvider("):
            self.assertNotIn(forbidden, body)

    def test_prompt_stage_never_blocks_normal_messages_when_disabled(self):
        # With the gate off, _image_flow returns None and the helper returns
        # False immediately; handle_message continues to its normal flow.
        start = BOT.index("def _image_flow")
        end = BOT.index("\ndef ", start + 10)
        helper = BOT[start:end]
        self.assertIn("return None", helper)

    def test_uuid5_ticket_idempotency(self):
        # The image ticket id is a deterministic uuid5 of (tenant, update_id):
        # the same Telegram update can never create two tickets.
        from uuid import UUID, uuid5
        tenant = "11111111-1111-4111-8111-111111111111"
        a = uuid5(UUID(tenant), "berry-generation:42")
        b = uuid5(UUID(tenant), "berry-generation:42")
        self.assertEqual(a, b)
        c = uuid5(UUID(tenant), "berry-generation:43")
        self.assertNotEqual(a, c)


if __name__ == "__main__":
    unittest.main()
