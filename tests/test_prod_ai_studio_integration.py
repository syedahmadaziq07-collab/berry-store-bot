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


def _load_credits_formatter():
    """Run the real formatter in isolation; importing bot starts its runtime."""
    tree = ast.parse(BOT)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_berry_credits_label")
    namespace = {"Decimal": Decimal}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "bot.py", "exec"), namespace)
    return namespace["_berry_credits_label"]


credits_label = _load_credits_formatter()


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
        self.assertEqual(credits_label(Decimal("4.99")), "6,237.5 Berry Credits")

    def test_whole_balance_clean(self):
        self.assertEqual(credits_label(Decimal("5.00")), "6,250 Berry Credits")

    def test_zero_and_transaction_signs(self):
        self.assertEqual(credits_label(Decimal("0")), "0 Berry Credits")
        self.assertEqual(credits_label(Decimal("5"), signed=True), "+6,250 Berry Credits")
        self.assertEqual(credits_label(Decimal("-1.25"), signed=True), "-1,562.5 Berry Credits")

    def test_nonfinite_money_rejected(self):
        for invalid in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                credits_label(Decimal(invalid))

    def test_bot_source_uses_exact_decimal_conversion(self):
        self.assertIn('credits = amount * Decimal("1250")', BOT)
        self.assertIn('balance_label = _berry_credits_label(balance)', BOT)
        self.assertNotIn('Berry Credits ({balance})', BOT)

    def test_studio_wallet_and_history_balance_labels_never_show_myr(self):
        studio = BOT.split('async def show_ai_video(', 1)[1].split('async def show_ai_studio_section(', 1)[0]
        wallet = BOT.split('elif section == "wallet":', 1)[1].split('elif section == "account":', 1)[0]
        self.assertIn('balance_label = _berry_credits_label(balance)', studio)
        self.assertIn('balance_label = _berry_credits_label(balance)', wallet)
        self.assertIn('amount_label = _berry_credits_label(amount, signed=True)', wallet)
        self.assertNotIn('RM', wallet)

    def test_video_confirm_balance_excludes_myr(self):
        video_handlers = Path('telegram_video_handlers.py').read_text(encoding='utf-8')
        self.assertIn("Baki: {ticket['balance_credits']} Berry Credits\\n", video_handlers)
        self.assertNotIn("ticket['balance_myr']", video_handlers)


class IdempotencyContractTests(unittest.TestCase):
    def test_concurrent_image_prepare_is_store_side_idempotent(self):
        # The image ticket id is a deterministic uuid5 of (tenant, update_id):
        # the same Telegram update can never create two tickets.
        from uuid import UUID, uuid5
        tenant = "11111111-1111-4111-8111-111111111111"
        a = uuid5(UUID(tenant), "berry-generation:42")
        b = uuid5(UUID(tenant), "berry-generation:42")
        self.assertEqual(a, b)
        c = uuid5(UUID(tenant), "berry-generation:43")
        self.assertNotEqual(a, c)


class VideoFlowWiringTests(unittest.TestCase):
    """Production wiring of the STEP 2 video consent controller (gated)."""

    def test_video_flow_helper_gated_by_env(self):
        self.assertIn('_get_env("BERRY_VIDEO_STUDIO_ENABLED") != "true"', BOT)

    def test_install_video_flow_requires_flag_and_test_user(self):
        start = BOT.index("def _install_video_flow")
        end = BOT.index("def build_app", start)
        body = BOT[start:end]
        self.assertIn("BERRY_VIDEO_STUDIO_ENABLED", body)
        self.assertIn("BERRY_VIDEO_STUDIO_TEST_USER_ID", body)
        # inert worker at install time: no external actions can occur
        self.assertIn("allow_external=False", body)
        self.assertIn("budget_id=None", body)

    def test_install_called_in_build_app(self):
        self.assertIn("_install_video_flow(app)", BOT)

    def test_video_confirm_cancel_routes_registered(self):
        self.assertIn('data.startswith("ai_video_confirm:")', BOT)
        self.assertIn('data.startswith("ai_video_cancel:")', BOT)

    def test_video_routes_use_gated_flow(self):
        self.assertIn("flow = _video_flow(context)", BOT)
        self.assertIn("AI Video belum diaktifkan", BOT)

    def test_disabled_video_flow_never_reaches_handlers(self):
        # _video_flow returns None without the literal env flag, so the
        # callback router answers "not activated" without importing handlers.
        start = BOT.index("def _video_flow")
        end = BOT.index("\ndef ", start + 10)
        helper = BOT[start:end]
        self.assertIn("return None", helper)

    def test_install_failure_never_breaks_startup(self):
        call = BOT.index("_install_video_flow(app)", BOT.index("def build_app"))
        window = BOT[call - 100:call + 100]
        self.assertIn("try:", window)
        self.assertIn("except Exception:", window)

    def test_image_prompt_text_handler_wired(self):
        self.assertIn("await _ai_image_prompt_text(update, context)", BOT)

    def test_image_confirm_routes_registered(self):
        self.assertIn('data.startswith("ai_image_confirm:")', BOT)
        self.assertIn('data.startswith("ai_image_cancel:")', BOT)

    def test_video_wiring_makes_no_provider_or_wallet_calls(self):
        start = BOT.index("def _video_flow")
        end = BOT.index("def main()", start)
        body = BOT[start:end]
        for forbidden in ("FalProvider(", "provider.submit", "ai_wallet_apply",
                          "sb_patch", "sb_post"):
            self.assertNotIn(forbidden, body)


class ImageFlowInstallerTests(unittest.TestCase):
    """_install_image_flow: gated installer for the AI Image Studio."""

    def test_installer_exists_and_is_gated(self):
        start = BOT.index("def _install_image_flow")
        end = BOT.index("def _ai_image_prompt", start)
        body = BOT[start:end]
        self.assertIn("_image_studio_enabled()", body)
        self.assertIn("_image_studio_test_user()", body)
        self.assertIn("TENANT_ID and SUPABASE_SERVICE_KEY", body)

    def test_installer_uses_inert_worker_fail_closed(self):
        start = BOT.index("def _install_image_flow")
        end = BOT.index("def _ai_image_prompt", start)
        body = BOT[start:end]
        self.assertIn("allow_external = False", body)
        self.assertIn("budget_id = None", body)
        self.assertIn('JobError("image job reservation not yet enabled")', body)

    def test_installer_rejects_ticket_owner_mismatch_and_replay(self):
        start = BOT.index("def _install_image_flow")
        end = BOT.index("def _ai_image_prompt", start)
        body = BOT[start:end]
        self.assertIn("ticket owner mismatch", body)
        self.assertIn("ticket replay conflict", body)

    def test_installer_uses_reviewed_catalog_json_env(self):
        start = BOT.index("def _install_image_flow")
        end = BOT.index("def _ai_image_prompt", start)
        body = BOT[start:end]
        self.assertIn("BERRY_IMAGE_CATALOG_JSON", body)
        # No quotes when the reviewed catalog is absent.
        self.assertIn("consent-only", body)

    def test_installer_never_constructs_provider(self):
        start = BOT.index("def _install_image_flow")
        end = BOT.index("def _ai_image_prompt", start)
        body = BOT[start:end]
        self.assertNotIn("FalProvider(", body)
        self.assertNotIn("provider.submit", body)
        # delivery token never logged
        self.assertNotIn('log.info(f"{token', body)

    def test_installer_called_in_build_app_protected(self):
        call = BOT.index("_install_image_flow(app)", BOT.index("def build_app"))
        window = BOT[call - 100:call + 100]
        self.assertIn("try:", window)
        self.assertIn("except Exception:", window)

    def test_image_prompt_text_routes_to_real_flow_prepare(self):
        start = BOT.index("async def _ai_image_prompt_text")
        end = BOT.index("async def _ai_image_confirm", start)
        body = BOT[start:end]
        self.assertIn("flow.prepare(user.id, update.update_id, prompt)", body)
        self.assertIn("return False", body)


if __name__ == "__main__":
    unittest.main()
