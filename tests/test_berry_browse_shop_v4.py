"""Offline safety contracts for the production Browse Shop V4 release."""

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
SQL = (ROOT / "docs/sql/berry_browse_shop_descriptions_v4.sql").read_text(encoding="utf-8")


class BrowseShopV4Tests(unittest.TestCase):
    def test_checkout_requires_second_variant_confirmation(self):
        # The first callback must only display details; the second may create an order.
        ast.parse(BOT)
        callback = BOT[BOT.index('elif data.startswith("variant_confirm_")'):]
        callback = callback[:callback.index('elif data.startswith("qty_minus_")')]
        self.assertIn('is_confirm = data.startswith("variant_confirm_")', callback)
        self.assertIn('if not is_confirm:', callback)
        self.assertIn('callback_data=f"variant_confirm_{vid}"', callback)
        self.assertIn('callback_data=f"product_{pid}"', callback)
        self.assertIn('track_flow_message(context, preview_msg, "variant_select")\n                    return', callback)
        self.assertLess(callback.index('if not is_confirm:\n                    cached_products'),
                        callback.index('await create_order('))
        self.assertIn('if int(v.get("stock") or 0) < 1:', callback)

    def test_all_existing_product_and_variant_descriptions_have_seven_day_warranty(self):
        product_sql, variant_sql = SQL.split("UPDATE public.product_variants AS v", 1)
        product_entries = re.findall(r"WHEN (\d+) THEN \$copy\$(.*?)\$copy\$", product_sql, re.S)
        variant_entries = re.findall(r"WHEN (\d+) THEN \$copy\$(.*?)\$copy\$", variant_sql, re.S)
        self.assertEqual({int(item[0]) for item in product_entries},
                         {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 16, 26})
        self.assertEqual({int(item[0]) for item in variant_entries},
                         {1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 24, 31, 48})
        for _id, description in product_entries + variant_entries:
            self.assertIn("Warranty 7 hari", description)
            self.assertNotIn("20 hari", description)
            self.assertNotIn("6 bulan warranty", description.lower())

    def test_three_requested_names_and_catalog_data_safety(self):
        self.assertIn("WHEN 6 THEN 'Pro Private 7 Days'", SQL)
        self.assertIn("WHEN 13 THEN 'Pro 1 Month'", SQL)
        self.assertIn("WHEN 8 THEN 'Gemini AI Plus 6 Months'", SQL)
        self.assertIn("Microsoft Word, Excel, PowerPoint", SQL)
        self.assertIn("p.tenant_id = '92c1e5ca-8498-438f-b777-3dc1c3195c1b'", SQL)
        self.assertNotRegex(SQL, r"(?im)^\s*(?:price|stock|duration|status)\s*=")
        self.assertIn("BEGIN;", SQL)
        self.assertIn("COMMIT;", SQL)


if __name__ == "__main__":
    unittest.main()
