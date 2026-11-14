"""Channel announcement regression tests: all Telegram and database calls mocked."""
import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
ANN = (ROOT / "berry_channel_announcements.py").read_text(encoding="utf-8")
FLOW = (ROOT / "telegram_video_flow.py").read_text(encoding="utf-8")
SQL = (ROOT / "docs/sql/berry_channel_announcements.sql").read_text(encoding="utf-8")


class ChannelAnnouncementTests(unittest.TestCase):
    def test_all_python_sources_parse(self):
        for value in (BOT, ANN, FLOW):
            ast.parse(value)

    def test_event_specific_telegram_buttons(self):
        self.assertIn("https://t.me/berryshopps_bot?start=browse_shop", ANN)
        self.assertIn("https://t.me/berryshopps_bot?start=ai_studio", ANN)
        self.assertIn('"shop": "🛍 Browse Shop"', ANN)
        self.assertIn('"topup": "🎬 AI Studio"', ANN)
        self.assertIn('"video": "🎬 AI Studio"', ANN)

    def test_deep_links_open_inbot_destinations(self):
        self.assertIn('if start_payload == "browse_shop":', BOT)
        self.assertIn('await show_shop(update, context)', BOT)
        self.assertIn('elif start_payload == "ai_studio":', BOT)
        self.assertIn('await show_ai_video(update, context)', BOT)
        self.assertIn("else update.message.reply_text", BOT)
        self.assertIn("AI Studio belum dibuka kepada pelanggan", BOT)

    def test_shop_and_topup_announce_only_after_approval(self):
        shop = BOT[BOT.index("async def _post_testimonial("):
                   BOT.index("# ─── Loyalty Points")]
        self.assertIn('_announce_channel_event(context, "shop", str(order_id), text)', shop)
        self.assertNotIn("context.bot.send_message(chat_id=TESTIMONIALS_CHANNEL_ID", shop)
        approval = BOT[BOT.index("async def _approve_order_core("):
                       BOT.index("async def _reject_order_core(")]
        self.assertIn('context, "topup", order_id,', approval)
        self.assertLess(approval.index('lambda: _topup_approve_atomic'),
                        approval.index('context, "topup", order_id,'))
        receipt = BOT[BOT.index("async def _store_topup_receipt("):
                      BOT.index("async def show_ai_video_text(")]
        self.assertNotIn("_announce_channel_event(", receipt)

    def test_durable_at_most_once_claim_per_channel(self):
        self.assertIn("PRIMARY KEY(tenant_id,event_type,event_id,channel_id)", SQL)
        self.assertIn("ON CONFLICT DO NOTHING", SQL)
        self.assertIn("o.status='completed'", SQL)
        self.assertIn("t.idempotency_key='berry-topup:'||o.id", SQL)
        self.assertIn("state=''delivered''", SQL)
        self.assertIn("ENABLE ROW LEVEL SECURITY", SQL)
        self.assertIn("SECURITY INVOKER", SQL)
        self.assertIn("FROM PUBLIC,anon,authenticated", SQL)
        self.assertIn("service_role", SQL)
        self.assertNotIn("DROP TABLE", SQL.upper())

    def test_video_notification_only_when_delivered(self):
        self.assertIn("if job and job.get('state') == 'delivered' and self.on_delivered:", FLOW)
        self.assertIn("self.on_delivered(ticket_id)", FLOW)
        self.assertIn("announce_video_delivered_sync(", BOT)
        self.assertIn("berry_private.ai_video_jobs", SQL)

    def test_duplicate_publish_skips_both_channels(self):
        fn = next(n for n in ast.parse(ANN).body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "announce_async")
        scope = {"asyncio": asyncio, "LOG": logging.getLogger("channel-tests"),
                 "channel_keyboard": lambda kind: {"kind": kind},
                 "AnnouncementUnavailable": ValueError}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<channel>", "exec"), scope)

        class Ledger:
            def __init__(self):
                self.claimed = set()
                self.marked = []
            def claim(self, kind, event_id, channel_id):
                key = (kind, event_id, channel_id)
                if key in self.claimed:
                    return False
                self.claimed.add(key)
                return True
            def mark_sent(self, kind, event_id, channel_id, message_id):
                self.marked.append((kind, event_id, channel_id, message_id))
                return True

        class Bot:
            def __init__(self):
                self.sent = []
            async def send_message(self, *, chat_id, text, reply_markup):
                self.sent.append((chat_id, text, reply_markup))
                return SimpleNamespace(message_id=10 + len(self.sent))

        ledger, bot = Ledger(), Bot()
        async def run():
            for _ in range(2):
                await scope["announce_async"](
                    bot, ledger, kind="topup", event_id="BTTEST", text="Approved",
                    channel_ids=(-1001, -1002))
        asyncio.run(run())
        self.assertEqual(len(bot.sent), 2)
        self.assertEqual(len(ledger.marked), 2)
        self.assertEqual({x[0] for x in bot.sent}, {-1001, -1002})

    def test_uncertain_send_never_retries(self):
        fn = next(n for n in ast.parse(ANN).body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "announce_async")
        scope = {"asyncio": asyncio, "LOG": logging.getLogger("channel-tests"),
                 "channel_keyboard": lambda kind: None,
                 "AnnouncementUnavailable": ValueError}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<channel>", "exec"), scope)
        claimed = set()
        attempts = []
        class Ledger:
            def claim(self, kind, event_id, channel_id):
                if channel_id in claimed:
                    return False
                claimed.add(channel_id)
                return True
            def mark_sent(self, *args):
                self.fail("not reached")
        class Bot:
            async def send_message(self, **kwargs):
                attempts.append(kwargs)
                raise RuntimeError("timeout")
        async def run():
            for _ in range(2):
                await scope["announce_async"](
                    Bot(), Ledger(), kind="shop", event_id="O123",
                    text="Approved", channel_ids=(-1001,))
        asyncio.run(run())
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
