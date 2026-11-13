"""Offline regression tests: zero external API/Telegram traffic."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

from berry_admin_minimax_trial import AdminMiniMaxTrial, MODEL, mini_max_arguments
from fal_provider import FalProvider, FalProviderError


ADMIN = 900000088


def update(user_id=ADMIN, chat_id=ADMIN, chat_type="private"):
    return NS(effective_user=NS(id=user_id),
              effective_chat=NS(id=chat_id, type=chat_type),
              message=NS(reply_text=AsyncMock()))


class TestTrial(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.provider = Mock()
        self.provider.submit.return_value = {
            "request_id": "fixture_123",
            "status_url": "https://queue.fal.run/minimax/h3-max-turbo/requests/fixture_123/status",
            "response_url": "https://queue.fal.run/minimax/h3-max-turbo/requests/fixture_123",
        }
        self.provider.status.return_value = {"status": "COMPLETED", "request_id": "fixture_123"}
        self.provider.result.return_value = {"video": {"url": "https://fal.media/fixture.mp4"}}
        self.delivery = Mock()
        self.delivery.send.return_value = 2
        self.path = str(Path(self.tmp.name) / "one.json")
        self.trial = AdminMiniMaxTrial(
            ADMIN, "fake-bot-token", state_path=self.path,
            provider=self.provider, delivery=self.delivery)
        self.tasks = []
        self.ctx = NS(
            args=["A", "white", "kitten", "running"],
            application=NS(create_task=lambda coro: self.tasks.append(coro)),
            bot=NS(send_message=AsyncMock()),
        )
        self.update = update()

    def test_exact_parameters(self):
        self.assertEqual(mini_max_arguments(" hi "), {
            "prompt": "hi", "duration": 10, "resolution": "480P",
            "prompt_expansion_mode": "balanced", "aspect_ratio": "16:9",
            "enable_safety_checker": True,
        })
        with self.assertRaises(ValueError):
            mini_max_arguments(" ")

    async def test_no_non_admin_or_group_access(self):
        for item in (update(user_id=ADMIN + 1), update(chat_type="group"),
                     update(chat_id=ADMIN + 1)):
            await self.trial.prepare(item, self.ctx)
            await self.trial.confirm(item, self.ctx)
        self.provider.submit.assert_not_called()
        self.assertFalse(Path(self.path).exists())

    async def test_prepare_is_free_and_exact_one_post(self):
        await self.trial.prepare(self.update, self.ctx)
        self.provider.submit.assert_not_called()
        await self.trial.confirm(self.update, self.ctx)
        self.assertTrue(Path(self.path).exists())
        await self.trial.confirm(self.update, self.ctx)
        self.assertEqual(len(self.tasks), 1)
        await self.tasks.pop()
        self.provider.submit.assert_called_once_with(
            MODEL, mini_max_arguments("A white kitten running"))
        self.delivery.send.assert_called_once_with(
            ADMIN, "video", "https://fal.media/fixture.mp4")
        self.assertEqual(json.loads(Path(self.path).read_text())["status"], "delivered")

    async def test_submit_timeout_never_retries(self):
        self.provider.submit.side_effect = TimeoutError("fake-error-secret")
        await self.trial.prepare(self.update, self.ctx)
        await self.trial.confirm(self.update, self.ctx)
        await self.tasks.pop()
        await self.trial.confirm(self.update, self.ctx)
        self.provider.submit.assert_called_once()
        self.delivery.send.assert_not_called()
        self.assertEqual(json.loads(Path(self.path).read_text())["status"],
                         "claimed_before_post")
        sent = " ".join(c.kwargs["text"] for c in
                        self.ctx.bot.send_message.call_args_list)
        self.assertNotIn("fake-error-secret", sent)

    async def test_persisted_checkpoint_blocks_restarted_runner(self):
        await self.trial.prepare(self.update, self.ctx)
        await self.trial.confirm(self.update, self.ctx)
        await self.tasks.pop()
        other = AdminMiniMaxTrial(ADMIN, "fake-bot-token", state_path=self.path,
                                  provider=self.provider, delivery=self.delivery)
        await other.prepare(self.update, self.ctx)
        await other.confirm(self.update, self.ctx)
        self.provider.submit.assert_called_once()

    async def test_bad_provider_urls_hold_without_retry(self):
        self.provider.submit.return_value = {
            "request_id": "fixture_123",
            "status_url": "https://example.com/status",
            "response_url": "https://example.com/result",
        }
        await self.trial.prepare(self.update, self.ctx)
        await self.trial.confirm(self.update, self.ctx)
        await self.tasks.pop()
        self.provider.status.assert_not_called()
        self.delivery.send.assert_not_called()
        self.provider.submit.assert_called_once()


class TestProviderKey(unittest.TestCase):
    def test_outer_whitespace_normalized(self):
        provider = FalProvider(api_key="  example-key\n")
        self.assertEqual(provider._headers()["Authorization"], "Key example-key")

    def test_internal_whitespace_never_accepted(self):
        with self.assertRaises(FalProviderError):
            FalProvider(api_key="example\nkey")._headers()


if __name__ == "__main__":
    unittest.main()
