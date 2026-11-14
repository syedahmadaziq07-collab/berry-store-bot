"""Berry Store private, durable at-most-once channel announcements.

No IO on import. Database claim occurs BEFORE any Telegram send. Claims are
non-retryable because Telegram could accept a message despite network timeout.
A claimed-but-unmarked delivery requires human reconciliation, not replay.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

import httpx

LOG = logging.getLogger(__name__)
BOT_USERNAME = "berryshopps_bot"
ALLOWED_EVENTS = {"shop", "topup", "video"}
LINKS = {
    "shop": "https://t.me/berryshopps_bot?start=browse_shop",
    "topup": "https://t.me/berryshopps_bot?start=ai_studio",
    "video": "https://t.me/berryshopps_bot?start=ai_studio",
}
BUTTONS = {
    "shop": "🛍 Browse Shop",
    "topup": "🎬 AI Studio",
    "video": "🎬 AI Studio",
}


class AnnouncementUnavailable(RuntimeError):
    pass


def action_link(kind: str):
    if kind not in ALLOWED_EVENTS:
        raise AnnouncementUnavailable("Unknown announcement event")
    return BUTTONS[kind], LINKS[kind]


def channel_keyboard(kind: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    label, url = action_link(kind)
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url)]])


def button_payload(kind: str):
    label, url = action_link(kind)
    return {"inline_keyboard": [[{"text": label, "url": url}]]}


class AnnouncementLedger:
    """Only server-side service-role RPCs, never anonymous Supabase keys."""

    def __init__(self, supabase_url, service_key, tenant_id, *, client=None):
        if (not isinstance(supabase_url, str)
                or not supabase_url.startswith("https://")
                or not supabase_url.endswith(".supabase.co")
                or not service_key):
            raise AnnouncementUnavailable("Server-only announcement connection required")
        self.tenant_id = str(UUID(str(tenant_id)))
        self.url = supabase_url.rstrip("/")
        self._key = service_key
        self._client = client

    def _rpc(self, name, data):
        if self._client is None:
            self._client = httpx.Client(timeout=12, follow_redirects=False)
        try:
            r = self._client.post(
                f"{self.url}/rest/v1/rpc/{name}",
                headers={"apikey": self._key,
                         "Authorization": "Bearer " + self._key,
                         "Content-Type": "application/json"},
                json=data, timeout=12, follow_redirects=False)
            r.raise_for_status()
            result = r.json()
        except (httpx.HTTPError, ValueError, TypeError):
            raise AnnouncementUnavailable("Announcement database unavailable") from None
        if type(result) is not bool:
            raise AnnouncementUnavailable("Unexpected announcement database response")
        return result

    def claim(self, kind: str, event_id: str, channel_id: int):
        self._validate(kind, event_id, channel_id)
        return self._rpc("berry_channel_announcement_claim", {
            "p_tenant": self.tenant_id, "p_kind": kind,
            "p_event_id": event_id, "p_channel_id": channel_id})

    def mark_sent(self, kind: str, event_id: str, channel_id: int, message_id: int):
        self._validate(kind, event_id, channel_id)
        if type(message_id) is not int or message_id <= 0:
            raise AnnouncementUnavailable("Invalid Telegram message ID")
        return self._rpc("berry_channel_announcement_mark_sent", {
            "p_tenant": self.tenant_id, "p_kind": kind,
            "p_event_id": event_id, "p_channel_id": channel_id,
            "p_message_id": message_id})

    @staticmethod
    def _validate(kind, event_id, channel_id):
        if (kind not in ALLOWED_EVENTS or not isinstance(event_id, str)
                or not 1 <= len(event_id) <= 128
                or type(channel_id) is not int or channel_id >= 0):
            raise AnnouncementUnavailable("Invalid announcement identity")

    def close(self):
        if self._client is not None:
            self._client.close()


async def announce_async(bot, ledger, *, kind, event_id, text, channel_ids):
    """For Telegram bot.py shop / manual-approved top-up announcements."""
    if not isinstance(text, str) or not text or len(text) > 4000:
        raise AnnouncementUnavailable("Invalid announcement text")
    for channel_id in channel_ids:
        try:
            claimed = await asyncio.to_thread(ledger.claim, kind, event_id, channel_id)
            if not claimed:
                continue
            try:
                message = await bot.send_message(
                    chat_id=channel_id, text=text, reply_markup=channel_keyboard(kind))
            except Exception as exc:
                LOG.warning("[CHANNEL] Telegram send uncertain for %s: %s; no retry",
                            kind, type(exc).__name__)
                continue
            try:
                await asyncio.to_thread(
                    ledger.mark_sent, kind, event_id, channel_id, message.message_id)
            except Exception as exc:
                LOG.warning("[CHANNEL] Sent but ack missing for %s: %s; no retry",
                            kind, type(exc).__name__)
        except Exception as exc:
            LOG.warning("[CHANNEL] suppressed unverified %s announcement: %s",
                        kind, type(exc).__name__)


def announce_video_delivered_sync(ledger, *, token, job_id, channel_ids):
    """Hook for *confirmed delivered* video job only; never exposes a video URL."""
    try:
        job_id = str(UUID(str(job_id)))
    except (TypeError, ValueError):
        return
    if not isinstance(token, str) or not token:
        return
    text = ("🎬 Berry AI Studio\n\n"
            "✅ AI Video successfully generated and delivered!\n"
            "🍓 Discover what you can create at Berry Store.")
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        for channel_id in channel_ids:
            try:
                if not ledger.claim("video", job_id, channel_id):
                    continue
                try:
                    r = client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": channel_id, "text": text,
                              "reply_markup": button_payload("video")},
                        timeout=12, follow_redirects=False)
                    r.raise_for_status()
                    data = r.json()
                    if (data.get("ok") is not True or
                            type(data.get("result", {}).get("message_id")) is not int):
                        raise AnnouncementUnavailable("Telegram receipt invalid")
                    msg_id = data["result"]["message_id"]
                except Exception as exc:
                    LOG.warning("[CHANNEL] Video send uncertain: %s; no retry",
                                type(exc).__name__)
                    continue
                try:
                    ledger.mark_sent("video", job_id, channel_id, msg_id)
                except Exception as exc:
                    LOG.warning("[CHANNEL] Video sent but ack missing: %s; no retry",
                                type(exc).__name__)
            except Exception as exc:
                LOG.warning("[CHANNEL] Video announcement suppressed: %s",
                            type(exc).__name__)
