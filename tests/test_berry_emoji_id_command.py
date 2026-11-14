"""The custom emoji reader is admin-only and cannot alter bot state."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
MENU = (ROOT / "berry_menu_visuals.py").read_text(encoding="utf-8")


class EmojiIdCommandTests(unittest.TestCase):
    def test_bot_syntax_and_menu_syntax(self):
        ast.parse(BOT)
        ast.parse(MENU)

    def test_reader_is_registered_and_private_admin_only(self):
        self.assertIn('CommandHandler("emojiid", cmd_emojiid)', BOT)
        func = BOT.split("async def cmd_emojiid(", 1)[1].split("# ─── /addcred", 1)[0]
        self.assertIn("update.effective_user.id != ADMIN_ID", func)
        self.assertIn('update.effective_chat.type != "private"', func)
        self.assertIn("msg.reply_to_message or msg", func)
        self.assertIn('e.type == "custom_emoji"', func)
        self.assertIn("e.custom_emoji_id", func)
        self.assertNotIn("sb_admin_post(", func)
        self.assertNotIn("sb_admin_patch(", func)
        self.assertNotIn("send_message(", func)

    def test_exposes_exact_environment_variable_names(self):
        func = BOT.split("async def cmd_emojiid(", 1)[1].split("# ─── /addcred", 1)[0]
        for key in ("BERRY_EMOJI_CAPCUT_ID", "BERRY_EMOJI_FIRE_ID",
                    "BERRY_EMOJI_WAVE_ID", "BERRY_ANIMATED_EMOJI_ENABLED"):
            self.assertIn(key, func)
        self.assertIn('("capcut", "✂️", "CAPCUT")', MENU)
        self.assertIn("icon('FIRE', '🔥')", MENU)
        self.assertIn("icon('WAVE', '👋')", MENU)


if __name__ == "__main__":
    unittest.main()
