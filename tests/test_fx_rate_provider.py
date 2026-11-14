"""FX rate provider tests (mocked transport; no real requests, no paid calls)."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from fx_rate_provider import (ENDPOINT, FXRateProvider, FXRateUnavailable,
                              SOURCE)


def client(payload=None, status=200, timeout=False):
    def handler(request):
        if timeout:
            raise httpx.ReadTimeout("t")
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
GOOD = {"amount": 1.0, "base": "USD", "date": TODAY, "rates": {"MYR": 4.42}}


class FXProviderTests(unittest.TestCase):
    def test_fresh_verified_rate(self):
        p = FXRateProvider(client=client(GOOD), buffer_fraction=Decimal("0.02"))
        rate = p.get_rate()
        self.assertEqual(rate.source, SOURCE)
        self.assertEqual(rate.myr_per_usd, Decimal("4.42"))
        self.assertLessEqual(rate.timestamp, datetime.now(timezone.utc).timestamp())

    def test_stale_rate_fails_closed(self):
        old = (datetime.now(timezone.utc).replace(day=1)
               - __import__("datetime").timedelta(days=10)).strftime("%Y-%m-%d")
        p = FXRateProvider(client=client({"base": "USD", "date": old,
                                          "rates": {"MYR": 4.4}}))
        with self.assertRaises(FXRateUnavailable):
            p.get_rate()

    def test_future_timestamp_rejected(self):
        future = (datetime.now(timezone.utc)
                  + __import__("datetime").timedelta(days=2)).strftime("%Y-%m-%d")
        p = FXRateProvider(client=client({"base": "USD", "date": future,
                                          "rates": {"MYR": 4.4}}))
        with self.assertRaises(FXRateUnavailable):
            p.get_rate()

    def test_provider_timeout_fails_closed(self):
        p = FXRateProvider(client=client(timeout=True))
        with self.assertRaises(FXRateUnavailable):
            p.get_rate()

    def test_invalid_schema_rejected(self):
        for bad in (None, {}, {"base": "EUR", "date": TODAY, "rates": {"MYR": 4}},
                    {"base": "USD", "date": TODAY, "rates": {"SGD": 1}},
                    {"base": "USD", "date": "not-a-date", "rates": {"MYR": 4}},
                    {"base": "USD", "date": TODAY, "rates": {"MYR": "nan"}},
                    {"base": "USD", "date": TODAY, "rates": {"MYR": 0}}):
            with self.subTest(bad=bad):
                p = FXRateProvider(client=client(bad))
                with self.assertRaises(FXRateUnavailable):
                    p.get_rate()

    def test_http_error_fails_closed(self):
        p = FXRateProvider(client=client(GOOD, status=503))
        with self.assertRaises(FXRateUnavailable):
            p.get_rate()

    def test_weekend_publication_accepted_within_window(self):
        # A Saturday "today" query typically returns Friday's date; Friday's
        # publication within 4 calendar days is fresh.
        friday = (datetime.now(timezone.utc)
                  - __import__("datetime").timedelta(days=2)).strftime("%Y-%m-%d")
        p = FXRateProvider(client=client({"base": "USD", "date": friday,
                                          "rates": {"MYR": 4.4}}))
        rate = p.get_rate()
        self.assertEqual(rate.myr_per_usd, Decimal("4.4"))

    def test_cache_and_refresh(self):
        calls = []
        clock = {"t": datetime.now(timezone.utc).timestamp()}
        today = datetime.fromtimestamp(clock["t"], timezone.utc).strftime("%Y-%m-%d")
        payload = {"amount": 1.0, "base": "USD", "date": today,
                   "rates": {"MYR": 4.42}}
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=payload)
        p = FXRateProvider(client=httpx.Client(
            transport=httpx.MockTransport(handler)), clock=lambda: clock["t"])
        r1 = p.get_rate()
        p.get_rate()  # cached; no extra call
        self.assertEqual(len(calls), 1)
        # TTL expires → refetch
        clock["t"] += 4000
        r2 = p.get_rate()
        self.assertEqual(len(calls), 2)
        self.assertEqual(r1.myr_per_usd, r2.myr_per_usd)

    def test_concurrent_requests_threadsafe(self):
        import threading
        barrier = threading.Barrier(8)
        results = []
        p = FXRateProvider(client=client(GOOD))
        def run():
            barrier.wait()
            try:
                results.append(p.get_rate().myr_per_usd)
            except Exception as exc:
                results.append(exc)
        threads = [threading.Thread(target=run) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertTrue(all(r == Decimal("4.42") for r in results), results)

    def test_rate_is_decimal_and_typed_reference(self):
        p = FXRateProvider(client=client(GOOD))
        rate = p.get_rate()
        self.assertIsInstance(rate.myr_per_usd, Decimal)
        self.assertIn("reference", rate.source)

    def test_constructor_validations(self):
        with self.assertRaises(FXRateUnavailable):
            FXRateProvider(max_published_age_days=0)
        with self.assertRaises(FXRateUnavailable):
            FXRateProvider(cache_ttl_seconds=1)
        with self.assertRaises(FXRateUnavailable):
            FXRateProvider(buffer_fraction=Decimal("0.9"))


if __name__ == "__main__":
    unittest.main()
