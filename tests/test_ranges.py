"""Behavioural regressions: range, falling trend, broken floor and shifted low."""
import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scanner"))
from scanner import Config, best_candidate


def history(base):
    # A completed 23% decline precedes four separate round trips between 100 and 111.
    closes = np.r_[np.linspace(140, 130, 30), np.asarray(base)]
    return pd.DataFrame({"Date": pd.bdate_range("2026-01-01", periods=len(closes)),
        "Open": closes, "High": closes + .6, "Low": closes - .6,
        "Close": closes, "Volume": 1000000})


class RangeTests(unittest.TestCase):
    def setUp(self):
        self.cycle = np.array([101, 104, 108, 111, 109, 106, 103, 101.2])

    def test_flat_range_after_decline_is_kept(self):
        candidate = best_candidate(history(np.tile(self.cycle, 4)), Config())
        self.assertIsNotNone(candidate)
        self.assertTrue(candidate["range_validated"])
        self.assertGreaterEqual(candidate["visit_count"], 3)
        self.assertLess(abs(candidate["trend_drift_pct"]), 8)

    def test_prior_trend_does_not_restrict_a_drop_followed_by_a_range(self):
        for prior in [np.linspace(110, 140, 30), np.linspace(180, 130, 30)]:
            with self.subTest(prior_start=prior[0]):
                d = history(np.tile(self.cycle, 4))
                for col, delta in [("Open", 0), ("Close", 0), ("High", .6), ("Low", -.6)]:
                    d.loc[:29, col] = prior + delta
                candidate = best_candidate(d, Config())
                self.assertIsNotNone(candidate)
                self.assertNotIn("entry_signal", candidate)
                self.assertNotIn("suggested_stop", candidate)

    def test_falling_sawtooth_is_not_a_range(self):
        base = np.tile(self.cycle, 4) - np.linspace(0, 28, 32)
        self.assertIsNone(best_candidate(history(base), Config()))

    def test_floor_break_is_not_rebased_downwards(self):
        d = history(np.r_[np.tile(self.cycle, 4), [97, 94, 90]])
        self.assertIsNone(best_candidate(d, Config()))

    def test_late_crash_cannot_create_historical_floor_tests(self):
        base = np.r_[np.tile(self.cycle, 4), [60, 62, 59, 57]]
        self.assertIsNone(best_candidate(history(base), Config()))

    def test_recovery_trend_and_no_prior_decline_are_rejected(self):
        rising = np.tile(self.cycle, 4) + np.linspace(0, 30, 32)
        self.assertIsNone(best_candidate(history(rising), Config()))
        d = history(np.tile(self.cycle, 4)).iloc[30:].reset_index(drop=True)
        self.assertIsNone(best_candidate(d, Config()))

    def test_old_range_then_fresh_floor_requires_new_validation(self):
        base = np.r_[np.tile(self.cycle, 4), [80, 83, 87, 82, 80]]
        self.assertIsNone(best_candidate(history(base), Config()))

    def test_old_floor_tests_do_not_validate_an_isolated_new_return(self):
        base = np.r_[np.tile(self.cycle, 3), np.tile([108, 110, 109, 111], 12), [104, 101]]
        self.assertIsNone(best_candidate(history(base), Config()))



if __name__ == "__main__":
    unittest.main()
