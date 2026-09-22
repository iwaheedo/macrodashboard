"""Threshold/signal logic tests — the interpretation layer must stay honest."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import composites
import interpret as I


def mk(dates, values):
    return {"dates": list(dates), "values": list(values)}


def daily(vals, start="2024-01-01"):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return mk([(d0 + timedelta(days=i)).isoformat() for i in range(len(vals))], vals)


class TestMacroReads(unittest.TestCase):
    def test_yield_curve_inverted_is_caution(self):
        r = I.read_yield_curve(daily([-0.5] * 10), daily([-0.8] * 10))
        self.assertEqual(r["signal"], "caution")
        self.assertIn("inverted", r["text"])

    def test_yield_curve_steep_is_good(self):
        r = I.read_yield_curve(daily([1.2] * 10), daily([1.5] * 10))
        self.assertEqual(r["signal"], "good")

    def test_hy_oas_bands(self):
        self.assertEqual(I.read_hy_oas(daily([3.0] * 5))["signal"], "good")
        self.assertEqual(I.read_hy_oas(daily([4.2] * 5))["signal"], "neutral")
        self.assertEqual(I.read_hy_oas(daily([6.5] * 5))["signal"], "caution")

    def test_vix_bands(self):
        self.assertEqual(I.read_vix(daily([12.0] * 5))["signal"], "neutral")
        self.assertEqual(I.read_vix(daily([17.0] * 5))["signal"], "good")
        self.assertEqual(I.read_vix(daily([35.0] * 5))["signal"], "caution")

    def test_unrate_sahm_style_rise_is_caution(self):
        # rises 0.6pp off its 12-month low
        r = I.read_unrate(daily([3.5] * 8 + [3.6, 3.8, 3.9, 4.1]))
        self.assertEqual(r["signal"], "caution")
        self.assertIn("rising", r["text"])

    def test_net_liquidity_direction(self):
        rising = I.read_net_liquidity(daily([5.0 + i * 0.005 for i in range(200)]))
        self.assertEqual(rising["signal"], "good")
        falling = I.read_net_liquidity(daily([6.0 - i * 0.005 for i in range(200)]))
        self.assertEqual(falling["signal"], "caution")
        flat = I.read_net_liquidity(daily([5.5] * 200))
        self.assertEqual(flat["signal"], "neutral")


class TestCryptoReads(unittest.TestCase):
    def test_mvrv_zones(self):
        self.assertEqual(I.read_mvrv(daily([0.8] * 50))["signal"], "good")
        self.assertEqual(I.read_mvrv(daily([2.0] * 50))["signal"], "neutral")
        self.assertEqual(I.read_mvrv(daily([3.8] * 50))["signal"], "caution")

    def test_mayer_zones(self):
        self.assertEqual(I.read_mayer(daily([0.7] * 5))["signal"], "good")
        self.assertEqual(I.read_mayer(daily([1.3] * 5))["signal"], "neutral")
        self.assertEqual(I.read_mayer(daily([2.6] * 5))["signal"], "caution")

    def test_fng_extremes(self):
        self.assertEqual(I.read_fng(daily([15] * 5))["signal"], "good")     # contrarian
        self.assertEqual(I.read_fng(daily([50] * 5))["signal"], "neutral")
        self.assertEqual(I.read_fng(daily([85] * 5))["signal"], "caution")

    def test_funding_crowded_longs(self):
        self.assertEqual(I.read_funding(daily([0.08] * 5))["signal"], "caution")
        self.assertEqual(I.read_funding(daily([-0.02] * 5))["signal"], "good")

    def test_btc_above_all_lines_good(self):
        price = daily([100_000] * 30)
        r = I.read_btc(price, daily([80_000] * 30), daily([60_000] * 30))
        self.assertEqual(r["signal"], "good")
        r2 = I.read_btc(price, daily([120_000] * 30), daily([60_000] * 30))
        self.assertEqual(r2["signal"], "caution")


class TestComposites(unittest.TestCase):
    def test_regime_quadrants(self):
        up, down = {"score": 70}, {"score": 30}
        self.assertIn("tailwind", composites.regime(up, up)["name"])
        self.assertIn("drain", composites.regime(down, down)["name"].lower())
        r = composites.regime({"score": 50}, {"score": 50})
        self.assertEqual(r["name"], "Transition")

    def test_gauge_averages_components(self):
        g = composites.gauge(
            [composites.component("a", 40, ""), composites.component("b", 60, ""),
             composites.component("c", None, "")],
            [(50, "low"), (100, "high")])
        self.assertEqual(g["score"], 50)
        self.assertEqual(g["label"], "low")

    def test_risk_appetite_high_when_calm(self):
        vix = daily([12.0] * 400 + [40.0] * 5)   # ends stressed
        hy = daily([3.0] * 405)
        spx = daily([5000.0] * 405)
        spx200 = daily([4500.0] * 405)
        calm = composites.risk_appetite(daily([12.0] * 405), hy, spx, spx200)
        stressed = composites.risk_appetite(vix, hy, spx, spx200)
        self.assertGreater(calm["score"], stressed["score"])


if __name__ == "__main__":
    unittest.main()
