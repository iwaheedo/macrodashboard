"""Parsing-logic tests with in-memory fixtures — no network calls.

These pin down the exact quirks we discovered in the real endpoints:
FRED zipping large downloads and splitting series across CSV members,
\r\n line endings, funding prints aggregating to daily, RSS structure.
"""
import io
import json
import os
import sys
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sources as S


class TestFredParsing(unittest.TestCase):
    def test_plain_csv_with_crlf_and_blanks(self):
        csv_bytes = (b"observation_date,DGS10,DGS2\r\n"
                     b"2024-01-01,4.00,\r\n"
                     b"2024-01-02,.,4.30\r\n"
                     b"2024-01-03,4.10,4.35\r\n")
        with patch.object(S, "get", return_value=csv_bytes):
            out = S.fred(["DGS10", "DGS2"])
        self.assertEqual(out["DGS10"]["dates"], ["2024-01-01", "2024-01-03"])
        self.assertEqual(out["DGS2"]["values"], [4.30, 4.35])

    def test_zip_with_multiple_members_and_readme(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("README.txt", "----\nnot data\n")
            z.writestr("daily.csv", "observation_date,DGS10\n2024-01-01,4.0\n")
            z.writestr("daily,_close.csv", "observation_date,SP500\n2024-01-01,5000\n")
        with patch.object(S, "get", return_value=buf.getvalue()):
            out = S.fred(["DGS10", "SP500"])
        self.assertEqual(out["DGS10"]["values"], [4.0])
        self.assertEqual(out["SP500"]["values"], [5000.0])

    def test_missing_series_raises(self):
        csv_bytes = b"observation_date,DGS10\n2024-01-01,4.0\n"
        with patch.object(S, "get", return_value=csv_bytes):
            with self.assertRaises(AssertionError):
                S.fred(["DGS10", "NOPE"])

    def test_chunking_never_exceeds_fred_limit(self):
        calls = []

        def fake_get(url, **kw):
            ids = url.split("id=")[1].split("&")[0].split(",")
            calls.append(len(ids))
            header = "observation_date," + ",".join(ids)
            row = "2024-01-01," + ",".join("1.0" for _ in ids)
            return (header + "\n" + row + "\n").encode()

        with patch.object(S, "get", side_effect=fake_get):
            out = S.fred([f"S{i}" for i in range(20)])
        self.assertEqual(len(out), 20)
        self.assertTrue(all(n <= 8 for n in calls), f"chunk too big: {calls}")


class TestBlockchainChart(unittest.TestCase):
    def test_dedup_same_day_keeps_last(self):
        payload = {"values": [
            {"x": 1704067200, "y": 1.0},      # 2024-01-01
            {"x": 1704100000, "y": 2.0},      # 2024-01-01 later
            {"x": 1704153600, "y": 3.0},      # 2024-01-02
        ]}
        with patch.object(S, "get_json", return_value=payload):
            out = S.blockchain_chart("market-price")
        self.assertEqual(out["dates"], ["2024-01-01", "2024-01-02"])
        self.assertEqual(out["values"], [2.0, 3.0])


class TestBitcoinData(unittest.TestCase):
    def test_field_mapping_and_sort(self):
        payload = [{"d": "2024-01-02", "mvrv": "2.1"},
                   {"d": "2024-01-01", "mvrv": 2.0},
                   {"d": "2024-01-03", "mvrv": None}]
        with patch.object(S, "get_json", return_value=payload):
            out = S.bitcoin_data("mvrv")
        self.assertEqual(out["dates"], ["2024-01-01", "2024-01-02"])
        self.assertEqual(out["values"], [2.0, 2.1])


class TestFunding(unittest.TestCase):
    def test_daily_aggregation_averages_prints(self):
        day = 1704067200000  # 2024-01-01 UTC
        pts = [(day, 0.01), (day + 8 * 3600_000, 0.02), (day + 16 * 3600_000, 0.03),
               (day + 24 * 3600_000, 0.05)]
        out = S._funding_daily(pts, "test")
        self.assertEqual(out["dates"], ["2024-01-01", "2024-01-02"])
        self.assertAlmostEqual(out["values"][0], 0.02)
        self.assertAlmostEqual(out["values"][1], 0.05)
        self.assertEqual(out["source"], "test")


class TestNews(unittest.TestCase):
    def test_rss_parse_and_per_feed_isolation(self):
        rss = (b"<?xml version='1.0'?><rss><channel>"
               b"<item><title>Alpha &amp; beta</title><link>https://x/a</link>"
               b"<pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>"
               b"</channel></rss>")

        def fake_get(url, **kw):
            if "coindesk" in url:
                return rss
            raise S.FetchError("boom")

        with patch.object(S, "get", side_effect=fake_get):
            items = S.news()
        self.assertTrue(any(i["title"] == "Alpha & beta" for i in items))
        # other feeds failing must not raise
        self.assertTrue(all(i["source"] == "CoinDesk" for i in items))


if __name__ == "__main__":
    unittest.main()
