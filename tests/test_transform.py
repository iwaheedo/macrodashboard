"""Unit tests for series math — pure functions, no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import transform as T


def mk(dates, values):
    return {"dates": list(dates), "values": list(values)}


class TestBasics(unittest.TestCase):
    def test_sma_window(self):
        s = mk([f"2024-01-{d:02d}" for d in range(1, 8)], [1, 2, 3, 4, 5, 6, 7])
        out = T.sma(s, 3)
        self.assertEqual(out["dates"][0], "2024-01-03")
        self.assertAlmostEqual(out["values"][0], 2.0)
        self.assertAlmostEqual(out["values"][-1], 6.0)
        self.assertEqual(len(out["values"]), 5)

    def test_yoy(self):
        dates = [f"{y}-{m:02d}-01" for y in (2023, 2024) for m in range(1, 13)]
        values = [100] * 12 + [110] * 12
        out = T.yoy(mk(dates, values))
        self.assertEqual(len(out["values"]), 12)
        self.assertAlmostEqual(out["values"][0], 10.0)

    def test_change_over_uses_calendar_days(self):
        s = mk(["2024-01-01", "2024-06-01", "2024-12-31"], [10.0, 15.0, 30.0])
        self.assertAlmostEqual(T.change_over(s, 365), 20.0)   # vs Jan 1
        self.assertAlmostEqual(T.change_over(s, 30), 15.0)    # vs Jun 1 (asof)

    def test_value_asof(self):
        s = mk(["2024-01-01", "2024-02-01"], [1.0, 2.0])
        self.assertEqual(T.value_asof(s, "2024-01-15"), 1.0)
        self.assertEqual(T.value_asof(s, "2024-02-01"), 2.0)
        self.assertIsNone(T.value_asof(s, "2023-12-31"))

    def test_merge_series_later_wins(self):
        a = mk(["2024-01-01", "2024-01-03"], [1.0, 3.0])
        b = mk(["2024-01-03", "2024-01-04"], [30.0, 40.0])
        out = T.merge_series(a, b)
        self.assertEqual(out["dates"], ["2024-01-01", "2024-01-03", "2024-01-04"])
        self.assertEqual(out["values"], [1.0, 30.0, 40.0])

    def test_to_daily_forward_fills(self):
        s = mk(["2024-01-01", "2024-01-04"], [1.0, 4.0])
        out = T.to_daily(s)
        self.assertEqual(out["dates"], ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
        self.assertEqual(out["values"], [1.0, 1.0, 1.0, 4.0])

    def test_percentile_rank(self):
        self.assertAlmostEqual(T.percentile_rank([1, 2, 3, 4], 5), 100.0)
        self.assertAlmostEqual(T.percentile_rank([1, 2, 3, 4], 0), 0.0)
        self.assertAlmostEqual(T.percentile_rank([1, 2, 3, 4], 2.5), 50.0)

    def test_ratio_asof(self):
        a = mk(["2024-01-02", "2024-01-03"], [10.0, 20.0])
        b = mk(["2024-01-01"], [2.0])
        out = T.ratio_asof(a, b)
        self.assertEqual(out["values"], [5.0, 10.0])


class TestRegression(unittest.TestCase):
    def test_log_regression_recovers_powerlaw(self):
        # synthesize price = 10^(-10) * days^3 exactly; fit must recover a and b
        from datetime import date, timedelta
        g = date(2009, 1, 3)
        dates, values = [], []
        for i in range(200, 3000, 5):
            d = g + timedelta(days=i)
            dates.append(d.isoformat())
            values.append(10 ** (-10 + 3 * __import__("math").log10(i)))
        fit = T.log_regression_bands(mk(dates, values))
        self.assertAlmostEqual(fit["b"], 3.0, places=3)
        self.assertAlmostEqual(fit["a"], -10.0, places=2)
        self.assertLess(fit["sigma"], 0.01)
        self.assertEqual(len(fit["bands"]), len(fit["ks"]))
        # band values must be increasing across ks at any date index
        mid = len(fit["dates"]) // 2
        col = [band[mid] for band in fit["bands"]]
        self.assertEqual(col, sorted(col))

    def test_band_position_zero_on_trend(self):
        from datetime import date, timedelta
        g = date(2009, 1, 3)
        dates, values = [], []
        for i in range(200, 2000, 5):
            d = g + timedelta(days=i)
            dates.append(d.isoformat())
            values.append(10 ** (-5 + 2 * __import__("math").log10(i)))
        fit = T.log_regression_bands(mk(dates, values))
        k = T.band_position(values[-1], dates[-1], fit)
        self.assertAlmostEqual(k, 0.0, places=1)


if __name__ == "__main__":
    unittest.main()
