"""HTTP helpers — stdlib only, with retries, backoff, and a browser-like UA.

Every fetcher in this project goes through `get()` so retry/timeout policy
lives in exactly one place.
"""
from __future__ import annotations

import gzip
import io
import json
import random
import time
import urllib.error
import urllib.request

# An honest tool UA. Sites with bot detection (e.g. FRED's CDN) actively
# reject browser UAs sent from non-browser TLS stacks, so do NOT "upgrade"
# this to a Chrome string — that breaks more sources than it fixes.
UA = "MacroDashboard/1.0 (personal data pipeline; contact via github)"

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3


class FetchError(Exception):
    """A source could not be fetched after all retries."""


def get(url: str, *, headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES, backoff: float = 2.0) -> bytes:
    """GET a URL, retrying on transient failures. Returns raw bytes."""
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return data
        except urllib.error.HTTPError as e:
            last_err = e
            # 4xx other than 408/429 will not get better by retrying
            if e.code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:  # URLError, timeout, IncompleteRead, ...
            last_err = e
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt) + random.uniform(0, 1))
    raise FetchError(f"GET {url} failed: {last_err}") from last_err


def get_json(url: str, **kw):
    return json.loads(get(url, **kw).decode("utf-8"))


def get_text(url: str, **kw) -> str:
    return get(url, **kw).decode("utf-8", errors="replace")
