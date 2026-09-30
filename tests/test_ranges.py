"""Behavioural regressions: range, falling trend, broken floor and shifted low."""
import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scanner"))
from scanner import Config, best_candidate, daily_setup


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

    def test_near_floor_is_not_an_entry_while_falling(self):
        d = history([107, 105, 103, 101])
        d.loc[d.index[-1], "Open"] = 102
        self.assertEqual(daily_setup(d, 100, 112, Config())["entry_signal"], "ESPERAR_REBOTE")

    def test_daily_confirmation_needs_a_green_break_above_previous_high(self):
        d = history([101, 103])
        d.loc[d.index[-1], "Open"] = 102
        self.assertEqual(daily_setup(d, 100, 112, Config())["entry_signal"], "CONFIRMACION_DIARIA")
        self.assertEqual(daily_setup(d, 100, 107, Config())["entry_signal"], "SIN_MARGEN")
        d.loc[d.index[-1], "Close"] = 106
        self.assertEqual(daily_setup(d, 100, 112, Config())["entry_signal"], "FUERA_ZONA")

    def test_recent_touch_without_recovery_is_not_called_a_rebound(self):
        d = history(np.r_[np.tile(self.cycle, 4), 105.5])
        item = best_candidate(d, Config())
        self.assertIsNotNone(item)
        self.assertEqual(item["state"], "VIGILAR")


if __name__ == "__main__":
    unittest.main()
