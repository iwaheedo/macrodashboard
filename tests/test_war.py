"""War-risk feature tests: PortWatch parsing, divergence logic, news filter."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import interpret as I
import sources as S


class TestPortwatchParsing(unittest.TestCase):
    def test_pagination_and_normalization(self):
        page1 = {"features": [
            {"attributes": {"date": "2024-01-02", "n_tanker": 5, "capacity_tanker": 100}},
            {"attributes": {"date": "2024-01-01", "n_tanker": 3, "capacity_tanker": None}},
        ] + [{"attributes": {"date": f"2024-02-{i%28+1:02d}", "n_tanker": 1,
                             "capacity_tanker": 1}} for i in range(998)]}
        page2 = {"features": [
            {"attributes": {"date": "2024-06-01", "n_tanker": 7, "capacity_tanker": 200}},
        ]}
        with patch.object(S, "get_json", side_effect=[page1, page2]):
            out = S.portwatch_chokepoint("chokepoint6")
        self.assertEqual(out["dates"][0], "2024-01-01")
        self.assertEqual(out["tankers"][0], 3)
        self.assertEqual(out["dwt"][0], 0)          # None capacity → 0
        self.assertEqual(out["dates"][-1], "2024-06-01")
        self.assertEqual(out["tankers"][-1], 7)

    def test_arcgis_error_raises(self):
        with patch.object(S, "get_json", return_value={"error": {"code": 400}}):
            with self.assertRaises(S.FetchError):
                S.portwatch_chokepoint("chokepoint6")


class TestDivergence(unittest.TestCase):
    def test_four_states(self):
        f = I.flow_price_divergence
        self.assertEqual(f(-60.0, 3.0, 100.0)["state"], "disruption_underpriced")
        self.assertEqual(f(-60.0, 40.0, 130.0)["state"], "disruption_priced")
        self.assertEqual(f(-5.0, 22.0, 95.0)["state"], "premium_no_disruption")
        self.assertEqual(f(-5.0, 2.0, 75.0)["state"], "aligned")
        self.assertEqual(f(None, 2.0, 75.0)["state"], "unknown")

    def test_underpriced_is_caution_with_ais_caveat(self):
        r = I.flow_price_divergence(-70.0, 1.0, 80.0)
        self.assertEqual(r["signal"], "caution")
        self.assertIn("AIS", r["text"])


class TestChokepointReads(unittest.TestCase):
    def test_severe_disruption_mentions_ais(self):
        r = I.read_chokepoint("Strait of Hormuz", -95.0, 1.0, 55.0)
        self.assertEqual(r["signal"], "caution")
        self.assertIn("AIS", r["text"])

    def test_normal_flow_good(self):
        r = I.read_chokepoint("Suez Canal", -3.0, 25.0, 26.0)
        self.assertEqual(r["signal"], "good")

    def test_cape_reroute_inverted(self):
        surge = I.read_chokepoint("Cape of Good Hope", 80.0, 17.0, 9.0, reroute=True)
        self.assertEqual(surge["signal"], "caution")
        calm = I.read_chokepoint("Cape of Good Hope", 2.0, 9.5, 9.3, reroute=True)
        self.assertEqual(calm["signal"], "good")


class TestBaselineWindows(unittest.TestCase):
    def test_window_mean_respects_bounds(self):
        import fetch_data as F
        dates = ["2021-12-31", "2022-01-01", "2022-01-02", "2022-02-01"]
        vals = [100, 10, 20, 999]
        self.assertEqual(F._window_mean(dates, vals, "2022-01-01", "2022-01-31"), 15.0)
        self.assertIsNone(F._window_mean(dates, vals, "2030-01-01", "2030-12-31"))

    def test_every_chokepoint_has_a_prewar_window(self):
        import fetch_data as F
        self.assertEqual(set(F.BASELINE_WINDOWS), set(S.CHOKEPOINTS))
        for key, (fetch_since, start, end, label) in F.BASELINE_WINDOWS.items():
            self.assertLessEqual(fetch_since, start, key)   # window must be fetched
            self.assertLess(start, end, key)
            self.assertTrue(label, key)
        # Black Sea baselines must predate the Feb 2022 invasion
        self.assertLess(F.BASELINE_WINDOWS["kerch"][2], "2022-02-24")
        self.assertLess(F.BASELINE_WINDOWS["bosporus"][2], "2022-02-24")
        # Red Sea baselines must predate the Nov 2023 Houthi campaign
        self.assertLess(F.BASELINE_WINDOWS["bab_el_mandeb"][2], "2023-11-19")


class TestWarNewsFilter(unittest.TestCase):
    def test_keyword_matching(self):
        self.assertTrue(S.is_war_headline("Iran warns over Strait of Hormuz transit"))
        self.assertTrue(S.is_war_headline("Houthi drone strikes tanker in Red Sea"))
        self.assertTrue(S.is_war_headline("Russia escalates strikes on Kyiv energy grid"))
        self.assertFalse(S.is_war_headline("Apple unveils new iPhone lineup"))
        self.assertFalse(S.is_war_headline("Fed holds rates steady as inflation cools"))


if __name__ == "__main__":
    unittest.main()
