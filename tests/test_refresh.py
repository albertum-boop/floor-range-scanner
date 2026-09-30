import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from scripts.refresh_data import finalized_prices, latest_completed_session, publish_snapshot, split_download


class RefreshTests(unittest.TestCase):
    def test_closed_sessions_holidays_and_dst(self):
        cases = {
            "2026-09-29T02:00:00+02:00": "2026-09-28",
            "2026-09-29T17:59:00-04:00": "2026-09-28",
            "2026-09-29T18:01:00-04:00": "2026-09-29",
            "2026-09-28T02:00:00+02:00": "2026-09-25",
            "2026-09-08T02:00:00+02:00": "2026-09-04",
            "2026-10-27T02:00:00+01:00": "2026-10-26",
            "2026-03-31T02:00:00+02:00": "2026-03-30",
        }
        for now, expected in cases.items():
            with self.subTest(now=now):
                self.assertEqual(str(latest_completed_session(now).date()), expected)

    def setUp(self):
        self.sessions = pd.DatetimeIndex(mcal.get_calendar("NYSE").schedule(
            start_date="2026-05-01", end_date="2026-09-28").index)
        self.cutoff = self.sessions[-1]
        self.raw = pd.DataFrame({"Open": 10., "High": 11., "Low": 9., "Close": 10., "Volume": 1000000}, index=self.sessions)

    def test_in_progress_bar_is_excluded(self):
        raw = self.raw.copy()
        raw.index.name = "Date"  # Actual Yahoo layout; Date must not be both index and column.
        raw.loc[pd.Timestamp("2026-09-29")] = [100, 101, 99, 100, 1]
        result = finalized_prices(raw, self.cutoff, self.sessions)
        self.assertEqual(result.Date.max(), self.cutoff)
        self.assertEqual(result.Close.iloc[-1], 10)

    def test_stale_missing_and_invalid_histories_are_rejected(self):
        invalid = self.raw.copy()
        invalid.loc[self.cutoff, "High"] = np.inf
        for raw in [self.raw.iloc[:-1], self.raw.drop(self.sessions[-3]), invalid]:
            with self.assertRaises(ValueError):
                finalized_prices(raw, self.cutoff, self.sessions)

    def test_yahoo_column_layouts(self):
        multi = pd.concat({"SES": self.raw, "APP": self.raw}, axis=1)
        for raw in [multi, multi.swaplevel(axis=1)]:
            self.assertEqual(set(split_download(raw, ["SES", "APP"])), {"SES", "APP"})

    def test_failed_coverage_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            previous = output / "current.json"
            previous.write_text('{"as_of":"2026-09-25"}')
            with self.assertRaises(RuntimeError), patch("scripts.refresh_data.scan") as scan:
                publish_snapshot(output, output, ["SES", "APP"], {"SES"}, {"APP": "missing"},
                    self.cutoff, datetime.now(timezone.utc), .95, "test")
            scan.assert_not_called()
            self.assertEqual(previous.read_text(), '{"as_of":"2026-09-25"}')


if __name__ == "__main__":
    unittest.main()
