"""Top-up approval DM formatting; no database writes or network calls."""
import ast
import unittest
from pathlib import Path

BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class TopupApprovedDmTests(unittest.TestCase):
    def test_bot_parses(self):
        ast.parse(BOT)

    def test_approval_dm_has_real_newlines(self):
        start = BOT.index('text=f"🍓 Top Up diluluskan!')
        end = BOT.index('            except Exception as exc:', start)
        segment = BOT[start:end]
        self.assertIn(r'f"\nOrder: {order_id}\nSemak baki dalam My Wallet."', segment)
        self.assertNotIn(r'f"\\nOrder: {order_id}\\nSemak baki dalam My Wallet."', segment)


if __name__ == "__main__":
    unittest.main()
