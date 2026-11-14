"""Visual theme contract for Telegram menus (no network, no secrets)."""
import ast
import importlib.util
import os
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
VISUALS = (ROOT / "berry_menu_visuals.py").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("berry_menu_visuals", ROOT / "berry_menu_visuals.py")
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class BerryVisualMenuTests(TestCase):
    def test_python_source_parses(self):
        ast.parse(BOT)
        ast.parse(VISUALS)

    def test_unicode_fallback_no_premium_needed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(menu.icon("FIRE", "🔥"), "🔥")
            self.assertEqual(menu.product_icon("Netflix Premium"), "🎬")
            self.assertEqual(menu.product_icon("Canva Education"), "🎨")
            self.assertEqual(menu.product_icon("Microsoft Office Windows"), "🪟")
            self.assertEqual(menu.product_icon("Adobe Acrobat PRO"), "🅰️")
            self.assertEqual(menu.product_icon("VPN"), "🛡️")
            self.assertEqual(menu.product_icon("UNKNOWN PRODUCT"), "📦")

    def test_verified_config_required_for_animation(self):
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "false",
                                     "BERRY_EMOJI_FIRE_ID": "123456789012345"}, clear=True):
            self.assertEqual(menu.icon("FIRE", "🔥"), "🔥")
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "true",
                                     "BERRY_EMOJI_FIRE_ID": "bad<onload>"}, clear=True):
            self.assertEqual(menu.icon("FIRE", "🔥"), "🔥")
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "true",
                                     "BERRY_EMOJI_FIRE_ID": "123456789012345"}, clear=True):
            self.assertEqual(menu.icon("FIRE", "🔥"),
                             '<tg-emoji emoji-id="123456789012345">🔥</tg-emoji>')

    def test_html_escapes_unsafe_user_and_catalog_data(self):
        with patch.dict(os.environ, {}, clear=True):
            welcome = menu.welcome_message(
                welcome="<script>& hi", first_name='Ajiq <b>', username='x&y',
                telegram_id=456, total_users=100, total_sold=4,
                updated="today")
            self.assertIn("&lt;script&gt;&amp; hi", welcome)
            self.assertIn("Ajiq &lt;b&gt;", welcome)
            self.assertIn("@x&amp;y", welcome)
            self.assertNotIn("<script>", welcome)
            self.assertIn("🔥", welcome)
            line = menu.shop_line(1, "Canva & <Fake>", 7)
            self.assertIn("Canva &amp; &lt;Fake&gt;", line)
            self.assertTrue(line.startswith("🎨"))
            self.assertIn("qty.", line)
            studio = menu.ai_studio_message(balance="RM<1&2>", wallet_status="on")
            self.assertIn("RM&lt;1&amp;2&gt;", studio)

    def test_menu_integrations_and_button_controls_preserved(self):
        self.assertIn("welcome_message(", BOT)
        self.assertIn("shop_header(_shop_title, custom_ids)", BOT)
        self.assertIn('shop_line(i, p["name"], stock, custom_ids)', BOT)
        self.assertIn("ai_studio_message(", BOT)
        self.assertIn('parse_mode="HTML"', BOT)
        for action in ("shop", "ai_video", "myorders", "ai_studio:video",
                       "ai_studio:topup", "ai_studio:wallet", "ai_studio:history"):
            self.assertIn(f'callback_data="{action}"', BOT)
        self.assertIn("build_product_keyboard(products)", BOT)
        self.assertIn('if not _ai_video_is_admin(update):', BOT)

    def test_polling_conflict_recovers_without_dropping_updates(self):
        self.assertIn('context.application.bot_data["_berry_polling_conflict"] = True', BOT)
        self.assertIn('if app.bot_data.pop("_berry_polling_conflict", False):', BOT)
        self.assertIn('time.sleep(retry_delay)', BOT)
        self.assertIn('drop_pending_updates=False', BOT)

    def test_shop_caption_under_telegram_limit_with_typical_inventory(self):
        with patch.dict(os.environ, {}, clear=True):
            s = menu.shop_header("LIST PRODUCT")
            for i, name in enumerate([
                "API Key", "Adobe Acrobat PRO DC", "Autodesk AutoCAD 2023",
                "Canva Education", "Capcut PRO", "Microsoft Office MacOS",
                "Microsoft Office Windows", "Microsoft Project 2019",
                "Notion AI", "Prime Video", "VPN", "iLovePDF"
            ], start=1):
                s += menu.shop_line(i, name, 100)
            s += menu.shop_footer("Pilih nombor produk")
            self.assertLessEqual(len(s), 1024)


if __name__ == "__main__":
    main()
