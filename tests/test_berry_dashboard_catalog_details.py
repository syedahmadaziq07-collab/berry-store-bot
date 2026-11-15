"""The production dashboard edits real product/variant details without erasing inventory."""

import ast
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")


class OverlayNestingChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parents = {}

    def handle_starttag(self, tag, attrs):
        if tag in {"div", "span", "form", "table", "tr", "td", "details", "summary"}:
            attributes = dict(attrs)
            element_id = attributes.get("id")
            if element_id:
                self.parents[element_id] = tuple(self.stack)
            if tag in {"div", "span", "form", "table", "tr", "td", "details", "summary"}:
                self.stack.append((tag, element_id))

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()


class DashboardCatalogDetailsTests(unittest.TestCase):
    def test_variant_detail_modal_is_not_nested_inside_variant_list_modal(self):
        checker = OverlayNestingChecker()
        checker.feed(DASH)
        ancestors = checker.parents["variantEditOverlay"]
        self.assertNotIn(("div", "variantsOverlay"), ancestors)

    def test_dashboard_javascript_parses(self):
        if not shutil.which("node"):
            self.skipTest("Node.js not available")
        script = DASH.split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run(
            ["node", "--check"], input=script, text=True,
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_products_and_variants_have_full_description_controls(self):
        for field in (
            "editDeliveryNote", "editAccountType", "editActive", "editDesc",
            "newVarDescription", "newVarDeliveryNote", "varDetailName",
            "varDetailPrice", "varDetailStock", "varDetailDescription",
            "varDetailDeliveryNote", "variantEditOverlay",
        ):
            with self.subTest(field=field):
                self.assertIn('id="' + field + '"', DASH)
        self.assertIn(".update({variant_name:name, price, stock, description, delivery_note})", DASH)
        self.assertIn("description, delivery_note\n", DASH)
        self.assertIn("products').insert(record)", DASH)
        self.assertIn('"products": {"select","insert","update"}', BOT)

    def test_deactivation_keeps_all_stock_and_does_not_write_fake_variant_status(self):
        start = DASH.index("async function setProductAvailability(")
        end = DASH.index("async function toggleAutoDelivery(", start)
        code = DASH[start:end]
        self.assertIn("is_active: active, status: active ? 'active' : 'inactive'", code)
        self.assertNotIn("stock: 0", code)
        self.assertNotIn("product_variants", code)
        self.assertNotIn("tryVariantUpdateByProduct", DASH)

    def test_variant_writes_use_real_columns_and_tenant_ownership(self):
        self.assertIn('"product_variants": {"select","insert","update","delete"}', BOT)
        self.assertIn('table == "product_variants" and action == "insert"', BOT)
        self.assertIn('"tenant_id": f"eq.{TENANT_ID}"', BOT)
        self.assertIn('"product_id"', BOT)
        variant_actions = DASH[DASH.index("function deactivateVariant("):DASH.index("async function loadCredentials(", DASH.index("function deactivateVariant("))]
        self.assertNotIn(".update({ is_active: false })", variant_actions)

    def test_catalog_server_rejects_malformed_sale_values(self):
        parsed = ast.parse(BOT)
        node = next(n for n in parsed.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_dashboard_valid_catalog_record")
        namespace = {"Decimal": Decimal, "InvalidOperation": InvalidOperation}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "bot.py", "exec"), namespace)
        valid = namespace["_dashboard_valid_catalog_record"]
        good_product = {"name": "Canva Pro", "price": 12.50, "stock": 4,
                        "description": "Warranty 7 hari", "is_active": True}
        self.assertTrue(valid("products", "insert", good_product))
        self.assertTrue(valid("product_variants", "insert", {
            "product_id": 2, "variant_name": "Private 1 Month", "price": 15,
            "stock": 3, "description": "Warranty 7 hari", "delivery_note": "Login email",
        }))
        for field, bad in (("stock", -1), ("stock", 2.5), ("stock", True),
                           ("price", "NaN"), ("price", -2), ("price", 2.555),
                           ("status", {}), ("is_active", "true")):
            with self.subTest(field=field, bad=bad):
                self.assertFalse(valid("products", "insert", {**good_product, field: bad}))
        self.assertFalse(valid("product_variants", "update", {"product_id": 2}))


if __name__ == "__main__":
    unittest.main()
