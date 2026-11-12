"""Fail-closed fal.ai video transport and Berry Credits pricing primitives.

The API calls here do not debit wallets or send Telegram messages. Only the
job coordinator may call them after an atomic database reservation exists.
No implicit retries for a possibly accepted paid queue submission.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

CREDITS_PER_MYR = 1250
QUEUE_BASE = "https://queue.fal.run"
# Explicit provider allowlist prevents unknown models being called with
# incompatible, potentially expensive arguments.
SUPPORTED_VIDEO_MODELS = frozenset({
    "fal-ai/pixverse/v3.5/image-to-video",
})
VIDEO_DURATIONS = frozenset({"5", "8"})
VIDEO_RESOLUTIONS = frozenset({"720p"})
REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f-]{36}$", re.ASCII)


class VideoConfigurationError(ValueError):
    """Request cannot safely be submitted. No provider call was made."""


class ProviderUnknownOutcome(RuntimeError):
    """Provider submission could have succeeded; NEVER blindly resubmit."""


class ProviderRejected(RuntimeError):
    """Provider returned a definite non-200 response."""


@dataclass(frozen=True)
class VideoRequest:
    model_id: str
    prompt: str
    image_url: str
    duration: str = "5"
    resolution: str = "720p"

    def payload(self) -> dict[str, str]:
        if self.model_id not in SUPPORTED_VIDEO_MODELS:
            raise VideoConfigurationError("Model video belum diuji/dibenarkan.")
        if not isinstance(self.prompt, str) or not 1 <= len(self.prompt.encode("utf-8")) <= 2048:
            raise VideoConfigurationError("Prompt mesti 1–2048 UTF-8 bytes.")
        if not isinstance(self.image_url, str):
            raise VideoConfigurationError("URL gambar tidak sah.")
        parsed = urlparse(self.image_url)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username or parsed.password or parsed.fragment or
                parsed.port not in (None, 443) or
                parsed.hostname in ("localhost", "127.0.0.1")):
            raise VideoConfigurationError("Gambar mesti melalui HTTPS URL yang sah.")
        if self.duration not in VIDEO_DURATIONS or self.resolution not in VIDEO_RESOLUTIONS:
            raise VideoConfigurationError("Durasi atau resolution tidak disokong.")
        return {
            "prompt": self.prompt,
            "image_url": self.image_url,
            "duration": self.duration,
            "resolution": self.resolution,
        }


def credits_to_myr(credits: int) -> Decimal:
    """Wallet stores 2-decimal MYR; 25 Berry Credits = RM0.02 exactly.

    Never silently round a 1-credit price down to zero.
    """
    if type(credits) is not int or credits < 25 or credits > 1_000_000:
        raise VideoConfigurationError("Caj mesti antara 25 dan 1,000,000 Berry Credits.")
    value = Decimal(credits) / Decimal(CREDITS_PER_MYR)
    if value != value.quantize(Decimal("0.01")):
        raise VideoConfigurationError("Caj mesti gandaan 25 Berry Credits (unit wallet MYR).")
    return value


def validate_provider_request_id(value: str) -> str:
    if not isinstance(value, str) or not REQUEST_ID_PATTERN.fullmatch(value):
        raise VideoConfigurationError("Provider request ID tidak sah.")
    try:
        UUID(value)
    except ValueError as exc:
        raise VideoConfigurationError("Provider request ID tidak sah.") from exc
    return value


def validate_provider_url(url: Any, request_id: str, suffix: str) -> str:
    """Never follow an arbitrary provider-returned URL with the API key."""
    validate_provider_request_id(request_id)
    if not isinstance(url, str):
        raise VideoConfigurationError("Provider URL hilang.")
    parsed = urlparse(url)
    expected_suffix = "/requests/" + request_id + suffix
    if (parsed.scheme != "https" or parsed.hostname != "queue.fal.run" or
            parsed.port not in (None, 443) or parsed.username or parsed.password or
            parsed.query or parsed.fragment or not parsed.path.endswith(expected_suffix)):
        raise VideoConfigurationError("Provider URL tidak dipercayai.")
    return url


class FalVideoQueue:
    """Network boundary only. Persist provider request ID before polling."""

    def __init__(self, key: str | None = None, client: httpx.Client | None = None):
        self.key = key if key is not None else os.environ.get("FAL_KEY", "")
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)

    def _headers(self) -> dict[str, str]:
        if not self.key or not self.key.strip():
            raise VideoConfigurationError("FAL_KEY belum dikonfigurasi.")
        return {"Authorization": "Key " + self.key, "Content-Type": "application/json"}

    def submit_once(self, request: VideoRequest) -> dict[str, str]:
        """Submit a paid request ONCE; network ambiguity requires operator review."""
        payload = request.payload()
        try:
            response = self.client.post(
                QUEUE_BASE + "/" + request.model_id,
                headers=self._headers(), json=payload,
            )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise ProviderUnknownOutcome("Submission fal.ai tidak dapat dipastikan; jangan retry.") from exc
        if response.status_code != 200:
            raise ProviderRejected("Provider menolak job (HTTP %s)." % response.status_code)
        try:
            body = response.json()
            request_id = validate_provider_request_id(body["request_id"])
            return {
                "request_id": request_id,
                "status_url": validate_provider_url(body["status_url"], request_id, "/status"),
                "response_url": validate_provider_url(body["response_url"], request_id, ""),
            }
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderUnknownOutcome("Provider mungkin telah menerima job tetapi respons tidak sah.") from exc

    def check_status(self, status_url: str, request_id: str) -> str:
        status_url = validate_provider_url(status_url, request_id, "/status")
        try:
            response = self.client.get(status_url, headers=self._headers())
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnknownOutcome("Status provider tidak dapat diperiksa.") from exc
        status = result.get("status")
        if status not in ("IN_QUEUE", "IN_PROGRESS", "COMPLETED"):
            raise ProviderUnknownOutcome("Status provider tidak dikenali.")
        if result.get("error"):
            raise ProviderRejected("Provider menandakan job gagal; perlu reconciliation.")
        return status

    def get_video_result(self, response_url: str, request_id: str) -> str:
        response_url = validate_provider_url(response_url, request_id, "")
        try:
            response = self.client.get(response_url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            url = data["video"]["url"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderUnknownOutcome("Hasil provider belum dapat disahkan.") from exc
        if not isinstance(url, str):
            raise ProviderUnknownOutcome("Provider tidak memulangkan video URL.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ProviderUnknownOutcome("Provider memulangkan video URL tidak sah.")
        return url
