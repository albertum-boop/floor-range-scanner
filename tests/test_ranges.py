"""Benchmark the deployed adapter against the audited historical controls."""
import hashlib
import sys
import unittest
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scanner"))
from scanner import Config, MODEL_SHA256, candidate, model_bars, scan


class AuditedRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.snapshot = scan(
            ROOT / "tests/fixtures/audited", Config(), as_of="2026-09-25"
        )
        cls.by_ticker = {r["ticker"]: r for r in cls.snapshot["candidates"]}

    def test_exact_classifier_is_vendored(self):
        digest = hashlib.sha256((ROOT / "scanner/audited_model.py").read_bytes()).hexdigest()
        self.assertEqual(digest, MODEL_SHA256)
        self.assertEqual(self.snapshot["strategy"]["classifier_sha256"], digest)
        self.assertEqual(self.snapshot["strategy"]["version"], 9)

    def test_musa_and_app_keep_repeated_floor_above_dips(self):
        musa = self.by_ticker["MUSA"]
        self.assertEqual((musa["floor"], musa["floor_zone_high"]), (501.12, 506.01))
        self.assertEqual(musa["wick_dip"]["low"], 490.29)
        self.assertEqual(musa["wick_dip"]["recovered_at"], "2026-09-09")
        self.assertEqual(musa["first_detectable"], "2026-09-25")

        app = self.by_ticker["APP"]
        self.assertEqual((app["floor"], app["floor_zone_high"]), (303.17, 307.76))
        self.assertAlmostEqual(app["minimum_since_first_visit"], 297.5, places=2)
        self.assertEqual(app["wick_dip"]["date"], "2026-08-21")
        self.assertEqual(app["recovered_breach"]["recovered_at"], "2026-08-25")
        self.assertEqual(app["first_detectable"], "2026-09-03")

    def test_lower_repeated_contact_is_not_an_isolated_dip(self):
        onds = self.by_ticker["ONDS"]
        self.assertEqual((onds["floor"], onds["floor_zone_high"]), (7.13, 7.26))
        self.assertIsNone(onds["wick_dip"])
        self.assertEqual(onds["lower_repeated_contact"]["low"], 6.98)
        for ticker in ("KOP", "AVAV"):
            self.assertIsNone(self.by_ticker[ticker]["wick_dip"])

    def test_old_broken_shelves_are_not_current(self):
        self.assertEqual(set(self.by_ticker), {"APP", "MUSA", "ONDS", "KOP", "AVAV", "CAL", "LXU"})
        for ticker in ("PTRN", "DY", "POST"):
            self.assertNotIn(ticker, self.by_ticker)
        self.assertEqual(self.by_ticker["LXU"]["state"], "PENETRACION_PENDIENTE")
        self.assertTrue(all(row["last_confirmed"] == "2026-09-25"
                            for row in self.snapshot["candidates"]))

    def test_broken_candidate_does_not_abort_daily_publication(self):
        bars = model_bars(pd.read_csv(ROOT / "tests/fixtures/audited/MUSA.csv"), "2026-09-25")
        episode = {"last_confirmed": "2026-09-25", "status": "recent",
                   "first_contact": "2026-08-01", "modal_floor_low": 800,
                   "modal_floor_high": 810}
        self.assertIsNone(candidate("MUSA", episode, bars, Config()))


if __name__ == "__main__":
    unittest.main()
