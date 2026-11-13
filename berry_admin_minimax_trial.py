"""Owner-only, single-attempt MiniMax smoke test for a dedicated Telegram test bot.

This is a diagnostic path, NOT a storefront checkout or verified retail offer.
No wallet debits, no customer activation and absolutely no automatic POST retry.
Set BERRY_MINIMAX_TRIAL_ENABLED=true deliberately; disabled by default.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

from fal_provider import FalProvider
from staging_job_worker import queue_urls
from telegram_video_delivery import TelegramVideoDelivery
from video_myr_worker import trusted_result_url

MODEL = "minimax/h3-max-turbo/text-to-video"
MAX_POLL_SECONDS = 600
POLL_INTERVAL_SECONDS = 5
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


def mini_max_arguments(prompt: str):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
        raise ValueError("Prompt mesti antara 1 hingga 1500 aksara")
    return {
        "prompt": prompt.strip(),
        "duration": 10,
        "resolution": "480P",
        "prompt_expansion_mode": "balanced",
        "aspect_ratio": "16:9",
        "enable_safety_checker": True,
    }


class AdminMiniMaxTrial:
    def __init__(self, admin_id: int, bot_token: str, *,
                 state_path="/tmp/berry_minimax_trial_once.json",
                 provider=None, delivery=None):
        if type(admin_id) is not int or admin_id <= 0:
            raise ValueError("ADMIN_ID sah diperlukan")
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("BOT_TOKEN diperlukan")
        self.admin_id = admin_id
        self.provider = provider if provider is not None else FalProvider()
        self.delivery = delivery if delivery is not None else TelegramVideoDelivery(bot_token)
        self.state_path = Path(state_path)
        self._pending = None
        self._attempt_claimed = False

    def _authorized(self, update):
        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        return bool(user is not None and chat is not None
                    and user.id == self.admin_id and chat.id == self.admin_id
                    and chat.type == "private")

    def _spent(self):
        return self._attempt_claimed or self.state_path.exists()

    def _claim(self):
        """Record the irreversible attempt BEFORE any provider POST."""
        fd = os.open(str(self.state_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"status": "claimed_before_post", "model": MODEL}, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            # Keep the checkpoint: unknown whether any effect occurred.
            raise

    def _receipt(self, request_id, status):
        # Only fixed, non-secret fields; never store API keys, prompts or URLs.
        temporary = self.state_path.with_suffix(".tmp")
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump({"status": status, "request_id": request_id, "model": MODEL}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_path)

    async def prepare(self, update, context):
        if not self._authorized(update):
            return
        if self._spent():
            await update.message.reply_text(
                "⚠️ Satu percubaan ujian sudah dikunci. Semak fal.ai Usage sebelum tindakan lain.")
            return
        prompt = " ".join(context.args).strip()
        try:
            mini_max_arguments(prompt)
        except ValueError:
            await update.message.reply_text(
                "Cara guna: /videotest A white kitten running in a sunny garden")
            return
        self._pending = (prompt, time.monotonic() + 180)
        await update.message.reply_text(
            "🎬 MiniMax Turbo: 10 saat • 480P • balanced • 16:9.\n"
            "Ini satu request BERBAYAR. Harga standard rujukan sekitar USD0.25 "
            "untuk tepat 10 saat dibil; jumlah sebenar belum dijamin.\n"
            "Untuk submit SEKALI sahaja: /videotest_confirm\n"
            "Batal: abaikan; permintaan tamat selepas 3 minit.")

    async def confirm(self, update, context):
        if not self._authorized(update):
            return
        pending = self._pending
        if self._spent() or pending is None or time.monotonic() > pending[1]:
            self._pending = None
            await update.message.reply_text("⚠️ Ujian sudah digunakan atau confirmation tamat.")
            return
        try:
            self._claim()
        except FileExistsError:
            await update.message.reply_text("⚠️ Checkpoint ujian sedia ada; request baharu ditolak.")
            return
        except OSError:
            await update.message.reply_text("⚠️ Tidak dapat simpan checkpoint; tiada request dihantar.")
            return
        self._attempt_claimed = True
        self._pending = None
        await update.message.reply_text(
            "⏳ Ujian satu kali dimulakan. Jangan tekan Confirm lagi atau cuba semula jika timeout.")
        # Background task uses the existing FalProvider queue client and TelegramVideoDelivery.
        context.application.create_task(self._generate(update.effective_chat.id, pending[0], context))

    async def _generate(self, chat_id: int, prompt: str, context):
        request_id = None
        try:
            payload = mini_max_arguments(prompt)
            submitted = await asyncio.to_thread(self.provider.submit, MODEL, payload)
            if not isinstance(submitted, dict):
                raise ValueError("Unexpected provider submit response")
            request_id = submitted.get("request_id")
            if not isinstance(request_id, str) or not ID_PATTERN.fullmatch(request_id):
                raise ValueError("Missing provider request ID")
            receipt = queue_urls(MODEL, request_id,
                                 submitted.get("status_url"), submitted.get("response_url"))
            await asyncio.to_thread(self._receipt, request_id, "queued")
            await context.bot.send_message(
                chat_id=chat_id, text="✅ Provider request_id: " + request_id)
            end = time.monotonic() + MAX_POLL_SECONDS
            while time.monotonic() < end:
                status = await asyncio.to_thread(self.provider.status, receipt["queue_status_url"])
                if not isinstance(status, dict) or status.get("request_id") not in (None, request_id):
                    raise ValueError("Provider status identity mismatch")
                if status.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                if status.get("status") != "COMPLETED" or status.get("error") or status.get("error_type"):
                    raise ValueError("Provider not completed successfully")
                result = await asyncio.to_thread(self.provider.result, receipt["queue_result_url"])
                video_url = trusted_result_url(result["video"]["url"])
                await asyncio.to_thread(self.delivery.send, chat_id, "video", video_url)
                await asyncio.to_thread(self._receipt, request_id, "delivered")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Video dihantar. Semak fal.ai Usage untuk caj sebenar; "
                         "ini bukan bukti kos maksimum.")
                return
            await context.bot.send_message(
                chat_id=chat_id, text="⏳ Belum siap. request_id: " + request_id +
                ". Jangan submit lagi; semak provider dahulu.")
        except Exception:
            # Never leak provider exception strings, credentials, URLs or prompt.
            note = (" Request ID: " + request_id) if request_id else ""
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Keputusan ujian belum disahkan." + note +
                     " Jangan submit semula; semak fal.ai Usage/Requests dahulu.")
