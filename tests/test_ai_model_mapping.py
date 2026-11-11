import unittest
from ai_model_mapping import (MappingValidationError, decode_mappings, encode_mappings,
                              public_label, resolve_provider_model, validate_mappings)

GOOD = {"tool_key":"image", "display_name":"Berry Image Pro",
        "provider_model_id":"fal-ai/flux/dev", "credit_cost":1250, "enabled":True}


class ModelMappingTests(unittest.TestCase):
    def test_separate_private_provider_model_from_public_telegram_label(self):
        rows = validate_mappings([GOOD])
        self.assertEqual(public_label(rows, "image"), "Berry Image Pro")
        self.assertEqual(resolve_provider_model(rows, "image"), "fal-ai/flux/dev")
        self.assertNotIn("fal-ai", public_label(rows, "image"))

    def test_round_trip_and_other_tools(self):
        rows = decode_mappings(encode_mappings([GOOD]))
        self.assertEqual(rows, [GOOD])
        self.assertEqual(public_label(rows, "video"), None)

    def test_disabled_mapping_never_resolves(self):
        rows = validate_mappings([{**GOOD, "enabled": False}])
        self.assertIsNone(public_label(rows, "image"))
        self.assertIsNone(resolve_provider_model(rows, "image"))

    def test_reject_duplicates_and_injection(self):
        bad = [
            [GOOD, GOOD],
            [{**GOOD, "display_name":"Berry\nSneaky"}],
            [{**GOOD, "display_name":"<b>not safe</b>"}],
            [{**GOOD, "provider_model_id":"https://evil.example/path?x=1"}],
            [{**GOOD, "provider_model_id":"../fal"}],
            [{**GOOD, "credit_cost": True}],
            [{**GOOD, "credit_cost": 0.5}],
            [{**GOOD, "enabled": "true"}],
            [{**GOOD, "extra":"unexpected"}],
        ]
        for mapping in bad:
            with self.subTest(mapping=mapping), self.assertRaises(MappingValidationError):
                validate_mappings(mapping)

    def test_empty_config_is_safe_and_no_auto_generation(self):
        self.assertEqual(decode_mappings(None), [])
        self.assertEqual(validate_mappings([]), [])
        self.assertIsNone(public_label([], "image"))
        with self.assertRaises(MappingValidationError):
            decode_mappings("corrupt")

    def test_max_entries_enforced(self):
        with self.assertRaises(MappingValidationError):
            validate_mappings([GOOD] * 17)


if __name__ == "__main__":
    unittest.main()
