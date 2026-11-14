"""STEP 3 — automatic verified USD/MYR FX rate provider.

Primary source (documented, auditable, no API key): Frankfurter
https://api.frankfurter.dev/v2/rate/usd/myr
  - Reference/mid-market rates from central banks and official sources.
  - Published daily (weekends carry the last trading day's date, handled by
    the freshness policy below).
  - v2 single-pair response: {"date":"YYYY-MM-DD","base":"USD","quote":"MYR","rate":4.x}

Freshness policy: v2 provides a reference DATE, not a publication timestamp.
For the legacy FXRate(timestamp) interface we use midnight UTC of the source
reference date as a conservative age anchor, never an invented publication
hour. The rate is accepted only within the configured age window and fails
closed on longer holidays or data outages.

Money math is Decimal. Rate type is REFERENCE (mid-market), NOT a
transaction rate; the configurable FX buffer provides conservatism.
Fail-closed on outage, schema mismatch, invalid pair or stale rate.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from ai_pricing_engine import FXRate

SOURCE = "frankfurter.dev-v2-reference"
ENDPOINT = "https://api.frankfurter.dev/v2/rate/usd/myr"
DEFAULT_MAX_PUBLISHED_AGE_DAYS = 4     # daily rate: covers weekend + 1 holiday
DEFAULT_CACHE_TTL_SECONDS = 1800       # 30 min between network fetches
DEFAULT_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 2


class FXRateUnavailable(RuntimeError):
    """Raised instead of guessing a rate; message is safe to display."""


class FXRateProvider:
    """Thread-safe, cached, fail-closed USD/MYR reference-rate provider."""

    def __init__(self, *, client=None,
                 max_published_age_days=DEFAULT_MAX_PUBLISHED_AGE_DAYS,
                 cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
                 buffer_fraction=Decimal("0.02"), clock=None):
        if not (isinstance(max_published_age_days, int) and max_published_age_days >= 1):
            raise FXRateUnavailable("Invalid FX freshness window")
        if not (isinstance(cache_ttl_seconds, int) and 60 <= cache_ttl_seconds <= 86400):
            raise FXRateUnavailable("Invalid FX cache TTL")
        if not isinstance(buffer_fraction, Decimal) or not (
                Decimal("0") <= buffer_fraction < Decimal("0.5")):
            raise FXRateUnavailable("Invalid FX buffer")
        self._client = client
        self._clock = clock or time.time
        self._max_age_days = max_published_age_days
        self._cache_ttl = cache_ttl_seconds
        self._buffer = buffer_fraction
        self._lock = threading.Lock()
        self._cached = None       # (FXRate, fetched_at)
        self._fetch_budget = {"window_start": 0, "count": 0}

    @staticmethod
    def _published_timestamp(date_str, now=None):
        """Conservative UTC-day age anchor for the API's reference DATE.

        Frankfurter v2 returns no actual publication time. In particular,
        do not pretend 16:00 MYT is a published timestamp or overwrite it
        with the current application time.
        """
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise FXRateUnavailable("Invalid FX reference date") from None
        ts = int(d.timestamp())
        now = time.time() if now is None else now
        if ts > now:
            raise FXRateUnavailable("FX reference date in the future")
        return ts

    def _parse(self, payload):
        # /v2/rate/{base}/{quote} returns a FLAT object, unlike /v1/latest.
        if not isinstance(payload, dict):
            raise FXRateUnavailable("Invalid FX response schema")
        date = payload.get("date")
        if payload.get("base") != "USD" or payload.get("quote") != "MYR" \
                or "rate" not in payload or not isinstance(date, str):
            raise FXRateUnavailable("Invalid FX currency pair or schema")
        try:
            value = Decimal(str(payload["rate"]))
        except (InvalidOperation, ValueError, TypeError):
            raise FXRateUnavailable("Invalid FX rate value") from None
        if not value.is_finite() or value <= 0:
            raise FXRateUnavailable("Non-positive or non-finite FX rate")
        return value, self._published_timestamp(date, now=int(self._clock()))

    def _fetch(self):
        last_exc = None
        for _ in range(MAX_ATTEMPTS):
            try:
                if self._client is None:
                    with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS,
                                      follow_redirects=False) as owned:
                        response = owned.get(ENDPOINT)
                else:
                    response = self._client.get(ENDPOINT)
                response.raise_for_status()
                payload = response.json() \
                    if not isinstance(response, dict) else response
                value, published = self._parse(payload)
                return value, published
            except httpx.TimeoutException:
                last_exc = FXRateUnavailable("FX source timeout")
            except httpx.HTTPError:
                last_exc = FXRateUnavailable("FX source unavailable")
            except ValueError:
                last_exc = FXRateUnavailable("Invalid FX response")
            time.sleep(1)
        raise last_exc or FXRateUnavailable("FX source failed")

    def _budget_ok(self, now):
        if now - self._fetch_budget["window_start"] > 300:
            self._fetch_budget = {"window_start": now, "count": 0}
        self._fetch_budget["count"] += 1
        return self._fetch_budget["count"] <= 10

    def _fresh(self, published, now):
        if published > now:
            raise FXRateUnavailable("FX published timestamp in the future")
        if now - published > self._max_age_days * 86400:
            raise FXRateUnavailable(
                "FX rate stale (older than freshness window); fail closed")

    def get_rate(self) -> FXRate:
        """Return a FRESH, verified FXRate or raise (never guess)."""
        now = int(self._clock())
        with self._lock:
            if self._cached is not None:
                rate, fetched_at = self._cached
                # Cache entry expires by TTL; the PUBLICATION freshness is
                # re-validated on every call regardless of cache.
                try:
                    self._fresh(rate.timestamp, now)
                except FXRateUnavailable:
                    self._cached = None   # stale publication → drop cache
                else:
                    if now - fetched_at < self._cache_ttl:
                        return rate
                    self._cached = None   # TTL expired → refetch same rate
            if not self._budget_ok(now):
                raise FXRateUnavailable("FX fetch budget exceeded")
            value, published = self._fetch()
            self._fresh(published, now)
            rate = FXRate(myr_per_usd=value, source=SOURCE,
                          timestamp=published, buffer_fraction=self._buffer)
            self._cached = (rate, now)
            return rate