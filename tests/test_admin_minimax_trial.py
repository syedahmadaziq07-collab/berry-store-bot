"""Offline regression tests: zero external API/Telegram traffic."""
import asyncio
import json
import tempfile
import unittest
import httpx
from unittest.mock import patch
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
        self.env_patch = patch.dict("os.environ", {"BERRY_MINIMAX_TRIAL_PAID_ENABLED": "true"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
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


    async def test_diagnose_200_readonly_does_not_touch_trial_checkpoint(self):
        requests = []
        def fake_handler(req):
            requests.append(req)
            return httpx.Response(200, json={"prices": []})
        client = httpx.Client(transport=httpx.MockTransport(fake_handler))
        self.addCleanup(client.close)
        self.trial._diag_client = client
        self.trial.provider = FalProvider(api_key="fixture-key")
        await self.trial.diagnose(self.update, self.ctx)
        answer = self.update.message.reply_text.call_args.args[0]
        self.assertIn("HTTP 200", answer)
        self.assertIn("BUKAN bukti inference", answer)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")
        self.assertTrue(str(requests[0].url).startswith("https://api.fal.ai/v1/models/pricing"))
        self.provider.submit.assert_not_called()
        self.assertFalse(Path(self.path).exists())

    async def test_diag_http_status_sanitized(self):
        self.trial.provider = FalProvider(api_key="fixture-key")
        for status in (401, 403, 429, 500):
            client = httpx.Client(
                transport=httpx.MockTransport(
                    lambda req, status=status: httpx.Response(status, text="secret-token-please-hide")))
            self.trial._diag_client = client
            await self.trial.diagnose(self.update, self.ctx)
            msg = self.update.message.reply_text.call_args.args[0]
            self.assertIn("HTTP " + str(status), msg)
            self.assertNotIn("secret-token", msg)
            client.close()
        self.provider.submit.assert_not_called()

    async def test_paid_gate_blocks_even_when_preview_exists_and_checkpoint_missing(self):
        await self.trial.prepare(self.update, self.ctx)
        with patch.dict("os.environ", {"BERRY_MINIMAX_TRIAL_PAID_ENABLED": "false"}):
            await self.trial.confirm(self.update, self.ctx)
        self.assertFalse(Path(self.path).exists())
        self.assertEqual(len(self.tasks), 0)
        self.provider.submit.assert_not_called()

    async def test_failure_sanitizes_provider_status(self):
        self.provider.submit.side_effect = FalProviderError(
            "fake-secret-in-exception", code="http_403")
        await self.trial.prepare(self.update, self.ctx)
        await self.trial.confirm(self.update, self.ctx)
        await self.tasks.pop()
        text = " ".join(str(c.kwargs.get("text","")) for c in
                        self.ctx.bot.send_message.call_args_list)
        self.assertIn("http_403", text)
        self.assertNotIn("fake-secret", text)

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


    def test_http_errors_keep_numeric_status_only(self):
        def call(_):
            return httpx.Response(403, text="provider-secret-sensitive")
        client = httpx.Client(transport=httpx.MockTransport(call))
        self.addCleanup(client.close)
        provider = FalProvider(api_key="fixture-key", client=client)
        with self.assertRaises(FalProviderError) as raised:
            provider.submit(MODEL, mini_max_arguments("test prompt"))
        self.assertEqual(raised.exception.code, "http_403")
        self.assertNotIn("provider-secret", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_internal_whitespace_never_accepted(self):
        with self.assertRaises(FalProviderError):
            FalProvider(api_key="example\nkey")._headers()


if __name__ == "__main__":
    unittest.main()
