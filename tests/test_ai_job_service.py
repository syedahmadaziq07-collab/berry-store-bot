import unittest
from ai_job_service import AIJobService, AIJobNotReady


class Mapping:
    def configured(self):
        return True
    def get(self):
        return {"revision": 3, "mappings": [
            {"tool_key": "image", "display_name": "Berry Image", "provider_model_id": "fal-ai/flux/dev",
             "credit_cost": 4, "enabled": True}]}


class Provider:
    def __init__(self):
        self.calls = 0
    def configured(self):
        return True
    def _model(self, value):
        return value
    def submit(self, model, arguments):
        self.calls += 1
        return {"request_id": "queued"}


class Tests(unittest.TestCase):
    def test_requires_confirmed_reservation(self):
        provider = Provider()
        service = AIJobService(Mapping(), provider)
        quote = service.quote("image")
        self.assertEqual(quote.credits, 4)
        with self.assertRaises(AIJobNotReady):
            service.submit_reserved(quote, {"prompt": "x"}, reservation_id="job-1",
                                    verify_reservation=lambda rid, q: False)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(service.submit_reserved(quote, {"prompt": "x"}, reservation_id="job-1",
                                                verify_reservation=lambda rid, q: True)["request_id"], "queued")

    def test_placeholder_rejected(self):
        mapping = Mapping()
        mapping.get = lambda: {"revision": 1, "mappings": [
            {"tool_key": "image", "display_name": "Test", "provider_model_id": "test/staging-model",
             "credit_cost": 4, "enabled": True}]}
        with self.assertRaises(AIJobNotReady):
            AIJobService(mapping, Provider()).quote("image")


if __name__ == "__main__":
    unittest.main()
