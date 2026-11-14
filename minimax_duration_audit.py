"""MiniMax duration-mismatch investigation (request 01a1d621...).

Facts from the owner's controlled E2E run:
  payload sent: {"duration": 10, "resolution": "480P", ...}
  fal.ai billing: USD 0.18 at quantity 10.00 seconds  → provider BILLED 10s
  Telegram playback observed: ~5 seconds

Root-cause analysis requires comparing the ORIGINAL provider output file with
the Telegram-delivered copy. This module captures the exact diagnostic
procedure and encodes the resulting delivery validation, without submitting
any new paid request.

Procedure (owner-executed, documented in the audit doc):
  1. Download the original: the request result URL
     https://queue.fal.run/minimax/h3-max-turbo/requests/<id>
     returns {"video": {"url": "https://v3b.fal.media/...mp4", ...}} while
     the result is retained. Re-running that GET is FREE (no new generation).
  2. ffprobe both files:
       ffprobe -v error -show_entries format=duration -of csv=p=0 original.mp4
       ffprobe -v error -show_entries format=duration -of csv=p=0 telegram.mp4
  3. Compare with the billed quantity (10.00 s).

Likely causes (ranked, to be confirmed by the probe):
  A. Provider honored duration but Telegram re-encoded/preview-trimmed →
     original would be ~10s, Telegram copy ~5s (playback/metadata issue).
  B. Telegram sendVideo stream preview trimmed → same as A variant.
  C. Provider actually produced ~5s and billed 10s → provider-side issue;
     escalate to fal support with request_id (billing evidence).
The stored file_size for this request (see earlier probe fixtures) helps
distinguish: a 10s 480p clip is typically ~3–6 MB.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from video_myr_worker import JobError, trusted_result_url

MINIMUM_ACCEPTED_SECONDS = Decimal5 = 9.5  # 10s minus tolerated overrun margin


def probe_original_result(provider, request_id):
    """Read-only GET of an EXISTING request result. No new generation."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise JobError("request id required")
    url = ("https://queue.fal.run/minimax/h3-max-turbo/requests/"
           + request_id.strip())
    return provider.result(url)


def original_video_url(provider, request_id):
    result = probe_original_result(provider, request_id)
    video = (result or {}).get("video") or {}
    url = video.get("url")
    if not isinstance(url, str) or not url:
        raise JobError("original video url unavailable")
    return trusted_result_url(url), video


def compare_durations(original_seconds, telegram_seconds, billed_seconds=10.0):
    """Classify the mismatch once both durations are measured with ffprobe."""
    for name, v in (("original", original_seconds),
                    ("telegram", telegram_seconds),
                    ("billed", billed_seconds)):
        if not isinstance(v, (int, float)) or v <= 0:
            raise JobError(f"invalid {name} duration")
    verdict = {
        "original_seconds": original_seconds,
        "telegram_seconds": telegram_seconds,
        "billed_seconds": billed_seconds,
    }
    if abs(original_seconds - billed_seconds) <= 1.0:
        if abs(telegram_seconds - original_seconds) <= 1.0:
            verdict["root_cause"] = "no_mismatch"
        else:
            verdict["root_cause"] = "telegram_delivery_or_playback"
            verdict["fix"] = ("deliver original file bytes (sendVideo with "
                              "explicit supports_streaming and no re-encode) "
                              "or send as document; validate duration before "
                              "marking DELIVERED")
    else:
        verdict["root_cause"] = "provider_output_short"
        verdict["fix"] = ("escalate to fal support with request_id and both "
                          "ffprobe outputs; do NOT retry the paid request; "
                          "hold billing reconciliation")
    return verdict
