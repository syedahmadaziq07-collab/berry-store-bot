import unittest
from fal_pricing import PricingUnavailable
from step3_minimax_offer import make_minimax_staging_offer_builder


class FixturePricing:
    def exact_price(self, model):
        assert model == "minimax/h3-max-turbo/text-to-video"
        return 0.0175, "seconds"


class Step3OfferTests(unittest.TestCase):
    def builder(self, **override):
        options = dict(fx_myr_per_usd=4.7, verified_extra_cost_myr="0.20",
                       all_extra_costs_verified=True)
        options.update(override)
        return make_minimax_staging_offer_builder(FixturePricing(), **options)

    def test_10s_offer_uses_standard_floor_and_frozen_quote(self):
        offer = self.builder()("Kitten running", "16:9")
        self.assertEqual(offer.arguments["duration"], 10)
        self.assertEqual(offer.arguments["resolution"], "480P")
        self.assertEqual(offer.quote.provider_model_id,
                         "minimax/h3-max-turbo/text-to-video")
        self.assertEqual(offer.quote.all_in_cost_cents, 150)
        self.assertGreaterEqual(offer.quote.debit_cents - offer.quote.all_in_cost_cents, 100)
        self.assertEqual(offer.quote.credits * 100,
                         offer.quote.debit_cents * 1250)
        self.assertGreater(offer.verified_until, 0)

    def test_portrait_changes_only_ratio(self):
        offer = self.builder()("Garden scene", "9:16")
        self.assertEqual(offer.arguments["aspect_ratio"], "9:16")

    def test_unknown_cost_blocks_offer(self):
        with self.assertRaises(PricingUnavailable):
            self.builder(all_extra_costs_verified=False)("Cat", "16:9")

    def test_bad_ratio_is_rejected(self):
        with self.assertRaises(PricingUnavailable):
            self.builder()("Cat", "4:3")


if __name__ == "__main__":
    unittest.main()
