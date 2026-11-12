"""No paid fal.ai calls. Everything uses a mocked HTTP transport."""
import unittest
from decimal import Decimal
import httpx
from ai_video_pipeline import (
    FalVideoQueue, VideoRequest, VideoConfigurationError, ProviderRejected,
    ProviderUnknownOutcome, credits_to_myr, validate_provider_url,
)

REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"
BASE = "https://queue.fal.run/fal-ai/pixverse/v3.5/image-to-video"
STATUS = BASE + "/requests/" + REQUEST_ID + "/status"
RESULT = BASE + "/requests/" + REQUEST_ID


class VideoPipelineTests(unittest.TestCase):
    def setUp(self):
        self.input = VideoRequest("fal-ai/pixverse/v3.5/image-to-video",
                                  "Cinematic sunrise", "https://cdn.example.com/image.jpg", "5", "720p")

    def test_price_is_exact_in_wallet_myr(self):
        self.assertEqual(credits_to_myr(25), Decimal("0.02"))
        self.assertEqual(credits_to_myr(1250), Decimal("1.00"))
        self.assertEqual(credits_to_myr(2500), Decimal("2.00"))

    def test_reject_price_rounding_and_invalid_values(self):
        for bad in (0, 1, 2, 24, 26, -25, 1_000_001, True, 125.5):
            with self.subTest(bad=bad), self.assertRaises(VideoConfigurationError):
                credits_to_myr(bad)

    def test_reject_unsupported_model_and_invalid_payload(self):
        invalid = [
            VideoRequest("fal-ai/unknown", "nice", "https://cdn.example.com/a.jpg"),
            VideoRequest(self.input.model_id, "", self.input.image_url),
            VideoRequest(self.input.model_id, "🎬" * 600, self.input.image_url),
            VideoRequest(self.input.model_id, "nice", "http://cdn.example.com/a.jpg"),
            VideoRequest(self.input.model_id, "nice", "https://localhost/a.jpg"),
            VideoRequest(self.input.model_id, "nice", "https://u:p@cdn.example.com/a.jpg"),
            VideoRequest(self.input.model_id, "nice", "https://cdn.example.com/a.jpg", "15"),
            VideoRequest(self.input.model_id, "nice", "https://cdn.example.com/a.jpg", "5", "1080p"),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(VideoConfigurationError):
                value.payload()

    def test_provider_submit_validates_headers_and_result(self):
        sent = []
        def handler(req):
            sent.append(req)
            return httpx.Response(200, json={"request_id":REQUEST_ID,"status_url":STATUS,
                                             "response_url":RESULT})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        output = FalVideoQueue(key="fake-for-unit-test", client=client).submit_once(self.input)
        self.assertEqual(output["request_id"], REQUEST_ID)
        self.assertEqual(sent[0].headers["authorization"], "Key fake-for-unit-test")
        self.assertEqual(sent[0].url.path, "/fal-ai/pixverse/v3.5/image-to-video")

    def test_missing_key_never_submits(self):
        def handler(_):
            self.fail("Network must not be called")
        with self.assertRaises(VideoConfigurationError):
            FalVideoQueue(key="", client=httpx.Client(transport=httpx.MockTransport(handler))).submit_once(self.input)

    def test_ambiguous_response_is_never_safe_to_retry(self):
        for response in (httpx.Response(200, json={}),
                         httpx.Response(200, json={"request_id":REQUEST_ID, "status_url":"https://evil.test/x", "response_url":RESULT})):
            with self.subTest(response=response):
                client = httpx.Client(transport=httpx.MockTransport(lambda _: response))
                with self.assertRaises(ProviderUnknownOutcome):
                    FalVideoQueue(key="x", client=client).submit_once(self.input)

    def test_provider_400_is_definite_rejection(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(400)))
        with self.assertRaises(ProviderRejected):
            FalVideoQueue(key="x", client=client).submit_once(self.input)

    def test_provider_timeout_is_unknown_not_retryable(self):
        def handler(req):
            raise httpx.ConnectTimeout("timed out", request=req)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with self.assertRaises(ProviderUnknownOutcome):
            FalVideoQueue(key="x", client=client).submit_once(self.input)

    def test_provider_url_is_not_ssrf_or_api_key_leak(self):
        bad = ("https://evil.example/" + REQUEST_ID + "/status",
               "http://queue.fal.run" + STATUS[21:],
               "https://u:p@queue.fal.run/" + STATUS.split("queue.fal.run/")[1],
               "https://queue.fal.run/owner/path/requests/" + REQUEST_ID + "/status?token=abc")
        for url in bad:
            with self.subTest(url=url), self.assertRaises(VideoConfigurationError):
                validate_provider_url(url, REQUEST_ID, "/status")

    def test_status_and_result_are_separate_and_checked(self):
        def handler(req):
            if str(req.url) == STATUS:
                return httpx.Response(200, json={"status":"COMPLETED"})
            if str(req.url) == RESULT:
                return httpx.Response(200, json={"video":{"url":"https://fal.media/files/video.mp4"}})
            self.fail("unexpected")
        api = FalVideoQueue(key="x", client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(api.check_status(STATUS, REQUEST_ID), "COMPLETED")
        self.assertEqual(api.get_video_result(RESULT, REQUEST_ID), "https://fal.media/files/video.mp4")

    def test_result_cannot_return_plain_http(self):
        api = FalVideoQueue(key="x", client=httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"video":{"url":"http://127.0.0.1/private"}}))))
        with self.assertRaises(ProviderUnknownOutcome):
            api.get_video_result(RESULT, REQUEST_ID)


if __name__ == "__main__":
    unittest.main()
