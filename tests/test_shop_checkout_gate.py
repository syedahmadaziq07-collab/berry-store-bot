"""Regression guard for the legacy shop checkout's fail-closed preflight."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ShopCheckoutGate(unittest.TestCase):
    def test_duplicate_check_failure_returns_before_any_order_insert(self):
        tree=ast.parse((ROOT/'bot.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='create_order')
        check=next(n for n in fn.body if isinstance(n,ast.Try) and 'orders.dup_check' in ast.unparse(n))
        self.assertTrue(any(isinstance(n,ast.Return) for n in ast.walk(check.handlers[0])))
        self.assertIn('pending,waiting,waiting_approval',ast.unparse(check))

    def test_database_index_covers_both_checkout_paths(self):
        sql=(ROOT/'docs/sql/berry_create_topup_order.sql').read_text()
        self.assertIn('CREATE UNIQUE INDEX IF NOT EXISTS berry_orders_one_active_user',sql)
        self.assertIn("status IN ('pending','waiting','waiting_approval')",sql)
