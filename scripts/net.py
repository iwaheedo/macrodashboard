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

# Hard caps so a compromised or broken source cannot blow up the runner:
# responses are read in chunks and abandoned beyond this size (largest
# legitimate payload today is a ~2MB FRED zip / DefiLlama chart).
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024


class FetchError(Exception):
    """A source could not be fetched after all retries."""


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that leave HTTPS — blocks MITM downgrade tricks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise FetchError(f"refusing redirect to non-HTTPS URL: {newurl[:80]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_HttpsOnlyRedirects())


def _read_capped(resp, cap: int = MAX_RESPONSE_BYTES) -> bytes:
    chunks, total = [], 0
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > cap:
            raise FetchError(f"response exceeded {cap} bytes — refusing to buffer it")
        chunks.append(chunk)


def _gunzip_capped(data: bytes) -> bytes:
    gz = gzip.GzipFile(fileobj=io.BytesIO(data))
    out = gz.read(MAX_DECOMPRESSED_BYTES + 1)
    if len(out) > MAX_DECOMPRESSED_BYTES:
        raise FetchError("gzip payload decompressed past the safety cap")
    return out


def get(url: str, *, headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES, backoff: float = 2.0) -> bytes:
    """GET a URL, retrying on transient failures. Returns raw bytes."""
    if not url.lower().startswith("https://"):
        raise FetchError(f"non-HTTPS URL refused: {url[:80]}")
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"}
    if headers:
        hdrs.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with _OPENER.open(req, timeout=timeout) as resp:
                data = _read_capped(resp)
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = _gunzip_capped(data)
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


def post_json(url: str, payload: dict, *, timeout: int = DEFAULT_TIMEOUT,
              retries: int = DEFAULT_RETRIES) -> dict:
    """POST a JSON body, return parsed JSON. Same policy/caps as get()."""
    if not url.lower().startswith("https://"):
        raise FetchError(f"non-HTTPS URL refused: {url[:80]}")
    body = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"User-Agent": UA, "Content-Type": "application/json",
                         "Accept": "application/json"})
            with _OPENER.open(req, timeout=timeout) as resp:
                data = _read_capped(resp)
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = _gunzip_capped(data)
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(2.0 * (2 ** attempt) + random.uniform(0, 1))
    raise FetchError(f"POST {url} failed: {last_err}") from last_err


def get_text(url: str, **kw) -> str:
    return get(url, **kw).decode("utf-8", errors="replace")
