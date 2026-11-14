"""Private admin registration of real Telegram custom app icons.

These tests never send a Telegram message, touch Supabase, or incur AI costs.
"""
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


class RealAppIconMappingTests(TestCase):
    def test_sources_parse(self):
        ast.parse(BOT)
        ast.parse(VISUALS)

    def test_every_brand_uses_owner_supplied_real_id(self):
        ids = {
            "CAPCUT": "1234567890123456789",
            "CHATGPT": "2234567890123456789",
            "NETFLIX": "3234567890123456789",
            "CANVA": "4234567890123456789",
            "SPOTIFY": "5234567890123456789",
            "FIRE": "6234567890123456789",
            "WAVE": "7234567890123456789",
        }
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "true"}):
            for brand, key in [
                ("Capcut Pro", "CAPCUT"), ("ChatGPT Go", "CHATGPT"),
                ("Netflix Original 4K Premium", "NETFLIX"),
                ("Canva Education", "CANVA"), ("Spotify Premium", "SPOTIFY"),
            ]:
                row = menu.shop_line(1, brand, 1, ids)
                self.assertIn(f'emoji-id="{ids[key]}"', row)
                self.assertIn(brand, row)
            title = menu.shop_header("LIST PRODUCT", ids)
            self.assertIn(f'emoji-id="{ids["FIRE"]}"', title)
            welcome = menu.welcome_message(
                welcome="Welcome", first_name="User", username="user",
                telegram_id=42, total_users=10, total_sold=5,
                updated="today", custom_ids=ids)
            self.assertIn(f'emoji-id="{ids["WAVE"]}"', welcome)

    def test_gate_closed_keeps_untrusted_icons_out(self):
        ids = {"CAPCUT": "1234567890123456789"}
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "false"}, clear=True):
            row = menu.shop_line(1, "CapCut Pro", 5, ids)
            self.assertNotIn("<tg-emoji", row)

    def test_invalid_saved_ids_not_embedded_in_html(self):
        with patch.dict(os.environ, {"BERRY_ANIMATED_EMOJI_ENABLED": "true"}, clear=True):
            result = menu.shop_line(1, "CapCut", 3, {"CAPCUT": '12"><script>'})
            self.assertNotIn("<script>", result)
            self.assertNotIn("<tg-emoji", result)

    def test_command_admin_only_and_save_restricted(self):
        self.assertIn('CommandHandler("setemoji", cmd_setemoji)', BOT)
        self.assertIn('CommandHandler("emojitest", cmd_emojitest)', BOT)
        self.assertIn('CommandHandler("emojistatus", cmd_emojistatus)', BOT)
        segment = BOT.split("async def cmd_setemoji(", 1)[1].split("async def cmd_emojitest(", 1)[0]
        self.assertIn("user.id != ADMIN_ID", segment)
        self.assertIn('update.effective_chat.type != "private"', segment)
        self.assertIn('source = msg.reply_to_message', segment)
        self.assertIn('e.type == "custom_emoji"', segment)
        self.assertIn("len(ids) != 1", segment)
        self.assertIn("sb_admin_upsert(", segment)
        self.assertIn('record["key"]', segment)
        self.assertIn('_bot_settings[record["key"]] = ids[0]', segment)

    def test_installed_ids_used_by_all_three_menus(self):
        self.assertIn("def _menu_custom_ids()", BOT)
        self.assertIn('custom_ids=_menu_custom_ids()', BOT)
        self.assertIn('text = shop_header(_shop_title, custom_ids)', BOT)
        self.assertIn('text += shop_line(i, p["name"], stock, custom_ids)', BOT)
        self.assertIn("BERRY_ANIMATED_EMOJI_ENABLED", BOT)
        self.assertIn('"BERRY_EMOJI_" + key.upper() + "_ID"', VISUALS)


if __name__ == "__main__":
    main()
