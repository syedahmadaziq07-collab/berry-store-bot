"""Duration audit tests: classification logic only (no network, no ffprobe)."""
import unittest

from minimax_duration_audit import compare_durations
from video_myr_worker import JobError


class DurationClassificationTests(unittest.TestCase):
    def test_provider_short_output_is_escalated(self):
        out = compare_durations(5.0, 5.0, billed_seconds=10.0)
        self.assertEqual(out["root_cause"], "provider_output_short")
        self.assertIn("fal support", out["fix"])
        self.assertIn("do NOT retry", out["fix"])

    def test_telegram_delivery_mismatch_detected(self):
        out = compare_durations(10.0, 5.0, billed_seconds=10.0)
        self.assertEqual(out["root_cause"], "telegram_delivery_or_playback")
        self.assertIn("sendVideo", out["fix"])

    def test_matching_durations_report_no_mismatch(self):
        out = compare_durations(10.0, 10.0, billed_seconds=10.0)
        self.assertEqual(out["root_cause"], "no_mismatch")

    def test_small_overrun_within_tolerance(self):
        # provider overrun ~0.7s documented; 10.7 original is fine
        out = compare_durations(10.7, 10.6, billed_seconds=10.0)
        self.assertEqual(out["root_cause"], "no_mismatch")

    def test_invalid_durations_rejected(self):
        for a, b in ((0, 5), (-1, 5), (None, 5), ("5", 5)):
            with self.assertRaises(JobError):
                compare_durations(a, b, billed_seconds=10.0)

    def test_billed_seconds_recorded_for_reconciliation(self):
        out = compare_durations(10.0, 5.0, billed_seconds=10.0)
        self.assertEqual(out["billed_seconds"], 10.0)


if __name__ == "__main__":
    unittest.main()
