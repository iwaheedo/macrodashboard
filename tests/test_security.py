"""Security regression tests: sanitizers, URL scheme guards, network caps.

These pin the defenses against a compromised upstream source — if any of
them regress, hostile feed content could reach the rendered page or blow up
the pipeline runner.
"""
import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import net
import sources as S


class TestSafeUrl(unittest.TestCase):
    def test_https_allowed(self):
        self.assertEqual(S.safe_url("https://example.com/a?b=1"), "https://example.com/a?b=1")

    def test_hostile_schemes_dropped(self):
        for bad in ("javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=",
                    "http://example.com/x", "file:///etc/passwd",
                    "https://exa mple.com",
                    'https://x.com/"><script>', "vbscript:x", None, 42, ""):
            self.assertEqual(S.safe_url(bad), "", f"allowed: {bad!r}")

    def test_padded_https_is_salvaged_clean(self):
        self.assertEqual(S.safe_url(" https://example.com "), "https://example.com")

    def test_overlong_dropped(self):
        self.assertEqual(S.safe_url("https://x.com/" + "a" * 600), "")


class TestCleanStr(unittest.TestCase):
    def test_strips_tags_and_control_chars(self):
        self.assertEqual(S.clean_str("<b>Hi</b>\x00\x1b there"), "Hi there")

    def test_caps_length_and_rejects_non_str(self):
        self.assertEqual(len(S.clean_str("x" * 999, 50)), 50)
        self.assertEqual(S.clean_str(None), "")
        self.assertEqual(S.clean_str({"a": 1}), "")


class TestNumCoercion(unittest.TestCase):
    def test_num(self):
        self.assertEqual(S._num("3.5"), 3.5)
        self.assertEqual(S._num(2), 2.0)
        for bad in ("abc", None, float("nan"), float("inf"), [1]):
            self.assertIsNone(S._num(bad), f"coerced: {bad!r}")


class TestFeedSanitization(unittest.TestCase):
    def test_hostile_feed_links_dropped(self):
        rss = (b"<?xml version='1.0'?><rss><channel>"
               b"<item><title>Evil</title><link>javascript:alert(1)</link></item>"
               b"<item><title>Good &amp; fine</title><link>https://ok.com/a</link></item>"
               b"</channel></rss>")
        with patch.object(S, "get", return_value=rss):
            items = S._parse_feed("Test", "macro", "https://feed", 10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://ok.com/a")
        self.assertEqual(items[0]["title"], "Good & fine")

    def test_calendar_impact_enum_enforced(self):
        rows = [{"title": "<i>CPI</i>", "country": "US", "date": "2026-01-01",
                 "impact": "<script>x</script>", "forecast": "3%", "previous": "2%"}]
        with patch.object(S, "get_json", return_value=rows):
            out = S.econ_calendar()
        self.assertEqual(out[0]["impact"], "Low")     # unknown value coerced
        self.assertEqual(out[0]["title"], "CPI")


class TestNetGuards(unittest.TestCase):
    def test_plain_http_refused(self):
        with self.assertRaises(net.FetchError):
            net.get("http://example.com/x", retries=1)
        with self.assertRaises(net.FetchError):
            net.post_json("http://example.com/x", {}, retries=1)

    def test_redirect_to_http_refused(self):
        h = net._HttpsOnlyRedirects()
        with self.assertRaises(net.FetchError):
            h.redirect_request(None, None, 302, "Found", {}, "http://evil.com/")

    def test_response_size_cap(self):
        class FakeResp:
            def __init__(self, size):
                self.buf = io.BytesIO(b"x" * size)
            def read(self, n):
                return self.buf.read(n)
        self.assertEqual(len(net._read_capped(FakeResp(10), cap=100)), 10)
        with self.assertRaises(net.FetchError):
            net._read_capped(FakeResp(300), cap=100)


if __name__ == "__main__":
    unittest.main()
