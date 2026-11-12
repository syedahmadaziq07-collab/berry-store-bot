"""STEP 3 — sendPhoto image delivery tests (gap I11). Mocked transport only."""
import unittest

import httpx

from telegram_image_delivery import TelegramImageDelivery
from video_myr_worker import JobError

USER = 900000088


class ImageDeliveryTests(unittest.TestCase):
    def test_send_photo_success_ack(self):
        calls = []

        def transport(request):
            calls.append(request)
            return httpx.Response(200, json={'ok': True, 'result': {
                'message_id': 77, 'chat': {'id': USER}}})

        d = TelegramImageDelivery('fixture-token',
                                  client=httpx.Client(transport=httpx.MockTransport(transport)))
        self.assertEqual(d.send(USER, 'image', 'https://fal.media/pic.png'), 77)
        self.assertEqual(len(calls), 1)
        self.assertIn('/sendPhoto', str(calls[0].url))
        d.close()

    def test_rejects_video_tool_and_bad_recipient(self):
        d = TelegramImageDelivery('fixture-token')
        for args in ((USER, 'video', 'https://fal.media/x.png'),
                     (-1, 'image', 'https://fal.media/x.png'),
                     ('uid', 'image', 'https://fal.media/x.png')):
            with self.assertRaises(JobError):
                d.send(*args)

    def test_untrusted_url_never_reaches_telegram(self):
        calls = []

        def transport(request):
            calls.append(request)
            return httpx.Response(200, json={})

        d = TelegramImageDelivery('fixture-token',
                                  client=httpx.Client(transport=httpx.MockTransport(transport)))
        for url in ('http://fal.media/x', 'https://evil.test/x', 'https://fal.media.evil.test/x'):
            with self.assertRaises(JobError):
                d.send(USER, 'image', url)
        self.assertEqual(calls, [])
        d.close()

    def test_ambiguous_outcome_held_without_token_leak(self):
        def transport(request):
            return httpx.Response(500)

        d = TelegramImageDelivery('secret-token-xyz',
                                  client=httpx.Client(transport=httpx.MockTransport(transport)))
        with self.assertRaises(JobError) as cm:
            d.send(USER, 'image', 'https://fal.media/x.png')
        self.assertNotIn('secret-token-xyz', str(cm.exception))
        self.assertNotIn('api.telegram.org', str(cm.exception))

    def test_negative_ack_rejected(self):
        def transport(request):
            return httpx.Response(200, json={'ok': False, 'result': {}})

        d = TelegramImageDelivery('t',
                                  client=httpx.Client(transport=httpx.MockTransport(transport)))
        with self.assertRaises(JobError):
            d.send(USER, 'image', 'https://fal.media/x.png')

    def test_constructor_requires_token(self):
        for token in ('', '   ', None, 5):
            with self.assertRaises(JobError):
                TelegramImageDelivery(token)


if __name__ == '__main__':
    unittest.main()
