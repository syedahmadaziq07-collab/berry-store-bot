"""Source-level safety gates avoid importing bot.py, which initializes runtime state."""
import ast
from pathlib import Path
import unittest

class RestartSafety(unittest.TestCase):
    def test_every_polling_restart_preserves_queued_updates(self):
        tree=ast.parse(Path('bot.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
               and isinstance(n.func,ast.Attribute) and n.func.attr in ('delete_webhook','run_polling')]
        self.assertGreaterEqual(len(calls),2)
        for call in calls:
            flags=[k.value for k in call.keywords if k.arg=='drop_pending_updates']
            self.assertEqual(len(flags),1)
            self.assertIsInstance(flags[0],ast.Constant)
            self.assertIs(flags[0].value,False)
    def test_no_early_token_network_takeover(self):
        source=Path('bot.py').read_text()
        self.assertNotIn('_EARLY_TOKEN',source)
        self.assertNotIn('deleteWebhook?drop_pending_updates=true',source)
        self.assertNotIn('ONLY running bot',source)
