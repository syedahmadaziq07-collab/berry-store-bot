"""Production model catalog tests. Mocked transport only; no real requests."""
import unittest
from unittest.mock import Mock

import httpx

from fal_pricing import PricingUnavailable, VerifiedFalPricing
from production_model_catalog import ProductionModelCatalog
from telegram_image_flow import VerifiedImageOffer

MODEL = "fal-ai/flux/schnell"
CATALOG = [dict(endpoint_id=MODEL, label="Berry Image FLUX", tool_key="image")]


def pricing_with(price=0.03, unit="image"):
    doc = {"prices": [{"endpoint_id": MODEL, "unit_price": price,
                       "unit": unit, "currency": "USD"}]}
    return VerifiedFalPricing(
        "k", client=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=doc))))


class CatalogTests(unittest.TestCase):
    def test_build_image_offer_frozen_verified_price(self):
        cat = ProductionModelCatalog(CATALOG)
        offer = cat.build_image_offer(
            pricing_with(), endpoint_id=MODEL, prompt="kucing",
            aspect="1:1", count=2, fx_rate=4.0, clock=lambda: 1000.0)
        self.assertIsInstance(offer, VerifiedImageOffer)
        q = offer.quote.payload()
        # cost: 0.03*2*4.0=RM0.24 -> 24 cents; credits aligned 25; debit 2 cents
        # -> but margin floor forces >= RM1 over cost; check invariants:
        self.assertEqual(q["all_in_cost_cents"], 24)
        self.assertEqual(q["credits"] % 25, 0)
        self.assertGreaterEqual(
            Decimal_h(q["debit_cents"]) - Decimal_h(q["all_in_cost_cents"]),
            Decimal_h(100))
        self.assertEqual(offer.verified_until, 1300)
        self.assertEqual(offer.arguments["num_images"], 2)

    def test_cost_snapshot_verified(self):
        cat = ProductionModelCatalog(CATALOG)
        snap = cat.cost_snapshot(pricing_with(), endpoint_id=MODEL,
                                 units=4, fx_rate=4.5)
        self.assertEqual(snap["all_in_cost_cents"], 54)  # 0.03*4*4.5=0.54
        self.assertEqual(snap["tool_key"], "image")

    def test_unknown_model_and_wrong_tool_rejected(self):
        cat = ProductionModelCatalog(CATALOG)
        with self.assertRaises(Exception):
            cat.entry("unknown/model")
        video_cat = ProductionModelCatalog(
            [dict(endpoint_id=MODEL, label="V", tool_key="video")])
        with self.assertRaises(Exception):
            video_cat.build_image_offer(
                pricing_with(), endpoint_id=MODEL, prompt="p", fx_rate=4.0)

    def test_invalid_catalog_rejected(self):
        for entries in (None, [], ["x"], [{}],
                        [dict(endpoint_id="a/b", label="L", tool_key="voice")]):
            with self.assertRaises(Exception):
                ProductionModelCatalog(entries)

    def test_pricing_failure_never_becomes_offer(self):
        cat = ProductionModelCatalog(CATALOG)
        broken = VerifiedFalPricing(
            "k", client=httpx.Client(transport=httpx.MockTransport(
                lambda r: httpx.Response(503, json={}))))
        with self.assertRaises(PricingUnavailable):
            cat.build_image_offer(broken, endpoint_id=MODEL, prompt="p",
                                  fx_rate=4.0)


def Decimal_h(value):
    from decimal import Decimal
    return Decimal(value)


if __name__ == "__main__":
    unittest.main()
