"""Bull-market playbook logic tests: crosses, weekly closes, phase inference."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import playbook as P


def daily(vals, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return {"dates": [(d0 + timedelta(days=i)).isoformat() for i in range(len(vals))],
            "values": list(vals)}


class TestCross(unittest.TestCase):
    def test_cross_state_detects_recent_cross(self):
        fast = daily([1] * 10 + [3] * 5)   # crosses above at index 10
        slow = daily([2] * 15)
        above, days = P._cross_state(fast, slow)
        self.assertTrue(above)
        self.assertEqual(days, 4)          # last date minus cross date

    def test_cross_state_below(self):
        above, _ = P._cross_state(daily([1] * 20), daily([2] * 20))
        self.assertFalse(above)


class TestWeeklyCloses(unittest.TestCase):
    def test_streak_counts_consecutive_sundays_above(self):
        # 2024-01-01 is a Monday; Sundays at indices 6, 13, 20, 27...
        vals = [100.0] * 28
        price = daily(vals)
        ma = daily([90.0] * 28)
        self.assertGreaterEqual(P._weekly_closes_above(price, ma), 3)
        # last Sunday below breaks the streak immediately
        vals2 = [100.0] * 27 + [80.0]
        self.assertEqual(P._weekly_closes_above(daily(vals2), ma), 0)


class TestPhase(unittest.TestCase):
    def mk_checks(self, **states):
        base = {"ma_200d": "pass", "sth_basis": "pass", "stables": "pass",
                "leverage": "pass", "onchain": "pass"}
        base.update(states)
        return [{"id": k, "state": v, "label": k, "value": "", "note": ""}
                for k, v in base.items()]

    def test_wealth_destruction_when_trend_and_sth_broken(self):
        ph = P.infer_phase(self.mk_checks(ma_200d="fail", sth_basis="fail"),
                           30, daily([50000] * 10), 0.5)
        self.assertEqual(ph["key"], "wealth_destruction")

    def test_early_bull_far_from_highs(self):
        ph = P.infer_phase(self.mk_checks(), 55, daily([80000] * 10), 0.7)
        self.assertEqual(ph["key"], "early_bull")

    def test_wealth_creation_near_highs_expanding(self):
        ph = P.infer_phase(self.mk_checks(), 65, daily([120000] * 10), 0.95)
        self.assertEqual(ph["key"], "wealth_creation")

    def test_distribution_when_euphoric_at_highs(self):
        ph = P.infer_phase(self.mk_checks(), 85, daily([150000] * 10), 0.99)
        self.assertEqual(ph["key"], "wealth_distribution")

    def test_output_shape(self):
        ph = P.infer_phase(self.mk_checks(), 55, daily([80000] * 10), 0.7)
        self.assertIn("guide", ph)
        self.assertEqual(len(ph["phases"]), 4)
        self.assertTrue(ph["why"])


class TestBuildChecks(unittest.TestCase):
    def test_integration_on_synthetic_bull(self):
        n = 500
        price = daily([50000 + i * 100 for i in range(n)], start="2024-06-01")
        cs = {
            "btc_price": price,
            "btc_sth_realized": daily([45000 + i * 80 for i in range(n)], start="2024-06-01"),
            "btc_dominance_proxy": daily([55 + i * 0.02 for i in range(200)], start="2025-06-01"),
            "stablecoin_mcap": daily([200 + i * 0.3 for i in range(300)], start="2025-01-01"),
            "dex_volume": daily([5.0] * 300 + [9.0] * 60, start="2024-12-01"),
        }
        derivs = {"open_interest": {"btc": daily([3.0 + i * 0.01 for i in range(120)],
                                                 start="2025-05-01")},
                  "funding": {"btc": daily([0.01] * 60, start="2025-07-01")}}
        checks = P.build_checks(cs, derivs, {})
        by_id = {c["id"]: c for c in checks}
        self.assertEqual(by_id["ma_200d"]["state"], "pass")
        self.assertEqual(by_id["sth_basis"]["state"], "pass")
        self.assertEqual(by_id["dominance"]["state"], "pass")
        self.assertEqual(by_id["stables"]["state"], "pass")
        self.assertEqual(by_id["onchain"]["state"], "pass")
        for c in checks:
            self.assertIn(c["state"], ("pass", "warn", "fail", "na"))
            self.assertTrue(c["note"] or c["state"] == "na")


if __name__ == "__main__":
    unittest.main()
