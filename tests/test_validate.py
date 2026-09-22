"""The validator must catch broken data loudly — these tests prove it does."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import validate as V


def today(offset_days=0):
    return (datetime.now(timezone.utc).date() + timedelta(days=offset_days)).isoformat()


def healthy_macro():
    d = [today(-2), today(-1)]
    mk = lambda a, b: {"dates": d, "values": [a, b]}
    return {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "series": {
                "net_liquidity": mk(5.8, 5.9), "global_cb": mk(17.0, 17.1),
                "m2_yoy": mk(4.0, 4.1), "cpi_yoy": mk(3.0, 3.1),
                "core_cpi_yoy": mk(2.8, 2.9), "unrate": mk(4.0, 4.1),
                "fedfunds": mk(4.5, 4.5), "dgs10": mk(4.2, 4.3),
                "t10y2y": mk(0.2, 0.25), "t10y3m": mk(0.5, 0.55),
                "hy_oas": mk(3.0, 3.1), "dxy_broad": mk(115.0, 115.2),
                "vix": mk(15.0, 15.5), "spx": mk(6000.0, 6010.0),
                "nasdaq": mk(20000.0, 20100.0), "oil": mk(75.0, 76.0),
            }}


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = V.DATA_DIR
        V.DATA_DIR = self.tmp.name

    def tearDown(self):
        V.DATA_DIR = self.orig
        self.tmp.cleanup()

    def write(self, name, payload):
        with open(os.path.join(self.tmp.name, name), "w") as f:
            json.dump(payload, f)

    def test_missing_files_reported(self):
        problems = V.validate()
        self.assertTrue(any("macro.json" in p for p in problems))
        self.assertTrue(any("crypto.json" in p for p in problems))

    def test_healthy_macro_block_passes(self):
        self.write("macro.json", healthy_macro())
        problems = [p for p in V.validate() if p.startswith("macro.json")]
        self.assertEqual(problems, [])

    def test_stale_series_caught(self):
        doc = healthy_macro()
        doc["series"]["dgs10"] = {"dates": [today(-30)], "values": [4.2]}
        self.write("macro.json", doc)
        problems = V.validate()
        self.assertTrue(any("dgs10" in p and "stale" in p for p in problems))

    def test_implausible_value_caught(self):
        doc = healthy_macro()
        # a units bug like the TGA-in-millions one we actually hit
        doc["series"]["net_liquidity"]["values"] = [-870.0, -871.0]
        self.write("macro.json", doc)
        problems = V.validate()
        self.assertTrue(any("net_liquidity" in p and "implausible" in p for p in problems))

    def test_length_mismatch_caught(self):
        doc = healthy_macro()
        doc["series"]["vix"] = {"dates": [today(-1)], "values": [15.0, 16.0]}
        self.write("macro.json", doc)
        problems = V.validate()
        self.assertTrue(any("vix" in p and "mismatch" in p for p in problems))

    def test_bad_signal_enum_caught(self):
        self.write("signals.json", {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reads": {"x": {"value": 1, "signal": "bullish!!", "text": "hi"}},
            "gauges": {"liquidity_impulse": {"score": 50}, "risk_appetite": {"score": 50},
                       "crypto_cycle": {"score": 50}, "regime": {"name": "ok"}}})
        problems = V.validate()
        self.assertTrue(any("bad signal" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
