"""All data-source fetchers. Every function returns normalized series/records.

Sources (all free, no API keys):
  FRED          fredgraph.csv keyless endpoint — rates, curve, VIX, SPX, CPI, Fed b/s ...
  Coin Metrics  community CSV on GitHub — BTC/ETH daily history, MVRV, hashrate ...
  Coinbase      spot BTC/ETH price
  CoinGecko     total crypto mcap + BTC dominance (fallback: CoinPaprika)
  alternative.me  Crypto Fear & Greed index
  DefiLlama     total stablecoin supply history
  Yahoo v8      classic DXY + gold futures (fallbacks: FRED broad USD, PAXG)
  OKX/Bybit/Binance  funding rate + open interest (multi-exchange fallback)
  ForexFactory  weekly economic calendar JSON
  RSS           CoinDesk, Cointelegraph, Decrypt, WSJ Markets, MarketWatch
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from net import get, get_json, get_text, FetchError
from transform import series

# ---------------------------------------------------------------- FRED ------

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"


def fred(ids: list[str], start: str | None = None) -> dict[str, dict]:
    """Fetch FRED series via the keyless CSV endpoint, chunking requests.

    fredgraph.csv silently DROPS series beyond ~12 per request, so never raise
    the chunk size near that. Returns {series_id: {"dates": [...], "values":
    [...]}} with blank cells dropped per column (mixed frequencies are sparse).
    """
    out: dict[str, dict] = {}
    CHUNK = 8
    for i in range(0, len(ids), CHUNK):
        out.update(_fred_one(ids[i:i + CHUNK], start))
    missing = [i for i in ids if i not in out or not out[i]["values"]]
    assert not missing, f"FRED returned no data for {missing}"
    return out


def _fred_one(ids: list[str], start: str | None) -> dict[str, dict]:
    url = FRED_CSV.format(ids=",".join(ids))
    if start:
        url += f"&cosd={start}"
    raw = get(url, timeout=180)  # multi-decade multi-series CSVs are slow
    texts = []
    if raw[:4] == b"PK\x03\x04":
        # FRED zips large downloads and may split series across several CSVs
        # (one per frequency/aggregation) plus a README — parse every CSV.
        import zipfile
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    texts.append(z.read(name).decode("utf-8", errors="replace"))
    else:
        texts.append(raw.decode("utf-8", errors="replace"))

    out: dict[str, dict] = {}
    for text in texts:
        rows = list(csv.reader(text.splitlines()))  # handles \r\n endings
        if not rows:
            continue
        header = rows[0]
        assert header[0] in ("observation_date", "DATE"), \
            f"unexpected FRED header {header[:2]}"
        cols: dict[str, tuple[list, list]] = {sid: ([], []) for sid in header[1:]}
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            dt = row[0]
            for j, sid in enumerate(header[1:], start=1):
                cell = row[j].strip() if j < len(row) else ""
                if cell and cell != ".":
                    try:
                        v = float(cell)
                    except ValueError:
                        continue
                    cols[sid][0].append(dt)
                    cols[sid][1].append(v)
        for sid, (d, v) in cols.items():
            # zip member columns can carry suffixes like "SP500_CLOSE"
            key = sid.split("_")[0] if sid.split("_")[0] in ids else sid
            out[key] = series(d, v)
    return out


# -------------------------------------------- BTC history & on-chain data ---

def blockchain_chart(name: str, timespan: str = "all") -> dict:
    """blockchain.info charts API (market-price, market-cap, hash-rate, ...).

    Long timespans come back sampled (non-daily); callers merge a fresh short
    timespan on top and forward-fill to daily before any moving averages.
    """
    j = get_json(f"https://api.blockchain.info/charts/{name}"
                 f"?timespan={timespan}&format=json", timeout=60)
    d, v = [], []
    for p in j["values"]:
        d.append(datetime.fromtimestamp(int(p["x"]), tz=timezone.utc).date().isoformat())
        v.append(float(p["y"]))
    dd, vv = [], []
    for dt, val in zip(d, v):
        if dd and dd[-1] == dt:
            vv[-1] = val
        else:
            dd.append(dt)
            vv.append(val)
    return series(dd, vv)


BITCOIN_DATA_FIELDS = {"mvrv": "mvrv", "realized-price": "realizedPrice"}


def bitcoin_data(metric: str) -> dict:
    """bitcoin-data.com free on-chain API (MVRV, realized price). ~1 week lag."""
    field = BITCOIN_DATA_FIELDS[metric]
    j = get_json(f"https://bitcoin-data.com/v1/{metric}",
                 headers={"Accept": "application/json"}, timeout=60)
    pts = []
    for r in j:
        try:
            pts.append((r["d"], float(r[field])))
        except (KeyError, TypeError, ValueError):
            continue
    pts.sort()
    return series([p[0] for p in pts], [p[1] for p in pts])


def coinbase_candles(product: str, start_year: int) -> dict:
    """Daily closes from Coinbase Exchange, paginated (300 candles per call)."""
    from datetime import date, timedelta
    import time as _time
    out: dict[str, float] = {}
    cur = date(start_year, 1, 1)
    today = datetime.now(timezone.utc).date()
    while cur <= today:
        end = min(cur + timedelta(days=290), today + timedelta(days=1))
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles"
               f"?granularity=86400&start={cur.isoformat()}T00:00:00Z"
               f"&end={end.isoformat()}T00:00:00Z")
        try:
            rows = get_json(url)
            for r in rows:  # [ts, low, high, open, close, vol]
                dt = datetime.fromtimestamp(int(r[0]), tz=timezone.utc).date().isoformat()
                out[dt] = float(r[4])
        except FetchError:
            pass  # product may not exist that far back
        cur = end
        _time.sleep(0.15)  # stay far under Coinbase's public rate limit
    dates = sorted(out)
    return series(dates, [out[d] for d in dates])


# ------------------------------------------------------------- spot etc -----

def coinbase_spot(pair: str) -> float:
    j = get_json(f"https://api.coinbase.com/v2/prices/{pair}/spot")
    return float(j["data"]["amount"])


def global_crypto() -> dict:
    """Total crypto market cap (USD) + BTC dominance. CoinGecko → CoinPaprika."""
    try:
        j = get_json("https://api.coingecko.com/api/v3/global")["data"]
        return {
            "total_mcap": float(j["total_market_cap"]["usd"]),
            "btc_dominance": float(j["market_cap_percentage"]["btc"]),
            "mcap_change_24h": float(j.get("market_cap_change_percentage_24h_usd", 0.0)),
            "source": "coingecko",
        }
    except Exception:
        j = get_json("https://api.coinpaprika.com/v1/global")
        return {
            "total_mcap": float(j["market_cap_usd"]),
            "btc_dominance": float(j["bitcoin_dominance_percentage"]),
            "mcap_change_24h": float(j.get("market_cap_change_24h", 0.0)),
            "source": "coinpaprika",
        }


def top_coins(n: int = 10) -> list[dict]:
    """Top coins by market cap (CoinGecko, keyless)."""
    j = get_json("https://api.coingecko.com/api/v3/coins/markets"
                 f"?vs_currency=usd&order=market_cap_desc&per_page={n}&page=1"
                 "&price_change_percentage=24h,7d")
    out = []
    for c in j:
        out.append({
            "symbol": (c.get("symbol") or "").upper(),
            "name": c.get("name") or "",
            "price": c.get("current_price"),
            "mcap": c.get("market_cap"),
            "chg24h": c.get("price_change_percentage_24h_in_currency"),
            "chg7d": c.get("price_change_percentage_7d_in_currency"),
        })
    return out


def sector_performance(min_mcap: float = 2e9, n: int = 10) -> list[dict]:
    """Crypto sector (category) 24h performance from CoinGecko."""
    j = get_json("https://api.coingecko.com/api/v3/coins/categories")
    rows = [c for c in j
            if (c.get("market_cap") or 0) >= min_mcap
            and c.get("market_cap_change_24h") is not None
            and c.get("name")]
    rows.sort(key=lambda c: c["market_cap_change_24h"], reverse=True)
    picked = rows[:n // 2] + rows[-(n - n // 2):] if len(rows) > n else rows
    seen, out = set(), []
    for c in picked:
        if c["name"] in seen:
            continue
        seen.add(c["name"])
        out.append({"name": c["name"][:40],
                    "chg24h": c["market_cap_change_24h"],
                    "mcap": c.get("market_cap")})
    return out


def fear_greed(limit: int = 730) -> dict:
    j = get_json(f"https://api.alternative.me/fng/?limit={limit}")
    pts = [(datetime.fromtimestamp(int(r["timestamp"]), tz=timezone.utc).date().isoformat(),
            float(r["value"])) for r in j["data"]]
    pts.sort()
    return series([p[0] for p in pts], [p[1] for p in pts])


def stablecoin_mcap() -> dict:
    j = get_json("https://stablecoins.llama.fi/stablecoincharts/all", timeout=60)
    d, v = [], []
    for r in j:
        usd = r.get("totalCirculatingUSD", {}).get("peggedUSD")
        if usd is not None:
            d.append(datetime.fromtimestamp(int(r["date"]), tz=timezone.utc).date().isoformat())
            v.append(float(usd) / 1e9)  # billions USD
    return series(d, v)


# ---------------------------------------------------------------- Yahoo -----

def yahoo_chart(symbol: str, range_: str = "10y", interval: str = "1d") -> dict:
    from urllib.parse import quote
    j = get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
        f"?range={range_}&interval={interval}", retries=4)
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    closes = res["indicators"]["quote"][0]["close"]
    d, v = [], []
    for t, c in zip(ts, closes):
        if c is not None:
            d.append(datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat())
            v.append(float(c))
    # de-dup dates (intraday last point can share the last daily date)
    dd, vv = [], []
    for dt, val in zip(d, v):
        if dd and dd[-1] == dt:
            vv[-1] = val
        else:
            dd.append(dt)
            vv.append(val)
    return series(dd, vv)


def paxg_gold_proxy(days: int = 365) -> dict:
    """Gold price proxy via PAXG token (tracks LBMA gold closely)."""
    j = get_json("https://api.coingecko.com/api/v3/coins/pax-gold/market_chart"
                 f"?vs_currency=usd&days={days}&interval=daily")
    d, v = [], []
    for t, p in j["prices"]:
        d.append(datetime.fromtimestamp(t / 1000, tz=timezone.utc).date().isoformat())
        v.append(float(p))
    dd, vv = [], []
    for dt, val in zip(d, v):
        if dd and dd[-1] == dt:
            vv[-1] = val
        else:
            dd.append(dt)
            vv.append(val)
    return series(dd, vv)


# ---------------------------------------------------- derivatives (multi) ---

def funding_history(coin: str) -> dict:
    """Perp funding-rate history (8h rates, %). Tries OKX → Bybit → Binance."""
    errors = []
    try:
        rows = []
        before = ""
        for _ in range(4):  # 4 pages x 100 = ~133 days
            url = ("https://www.okx.com/api/v5/public/funding-rate-history"
                   f"?instId={coin}-USDT-SWAP&limit=100" + (f"&after={before}" if before else ""))
            j = get_json(url)
            data = j.get("data", [])
            if not data:
                break
            rows.extend(data)
            before = data[-1]["fundingTime"]
        pts = sorted((int(r["fundingTime"]), float(r.get("realizedRate") or r["fundingRate"]) * 100)
                     for r in rows)
        if pts:
            return _funding_daily(pts, "okx")
    except Exception as e:
        errors.append(f"okx: {e}")
    try:
        j = get_json("https://api.bybit.com/v5/market/funding/history"
                     f"?category=linear&symbol={coin}USDT&limit=200")
        pts = sorted((int(r["fundingRateTimestamp"]), float(r["fundingRate"]) * 100)
                     for r in j["result"]["list"])
        if pts:
            return _funding_daily(pts, "bybit")
    except Exception as e:
        errors.append(f"bybit: {e}")
    try:
        j = get_json(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={coin}USDT&limit=1000")
        pts = sorted((int(r["fundingTime"]), float(r["fundingRate"]) * 100) for r in j)
        if pts:
            return _funding_daily(pts, "binance")
    except Exception as e:
        errors.append(f"binance: {e}")
    raise FetchError("funding failed on all exchanges: " + " | ".join(errors))


def _funding_daily(pts: list[tuple[int, float]], source: str) -> dict:
    """Average the (usually 3/day) 8h funding prints into one daily value."""
    by_day: dict[str, list[float]] = {}
    for ts, rate in pts:
        day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
        by_day.setdefault(day, []).append(rate)
    days = sorted(by_day)
    s = series(days, [sum(by_day[d]) / len(by_day[d]) for d in days])
    s["source"] = source
    return s


def open_interest_history(coin: str) -> dict:
    """Daily open interest. OKX (USD, US-accessible) → Bybit → Binance (base units).

    The result carries "unit": "usd" or "base" — consumers must check it.
    """
    errors = []
    try:
        j = get_json("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume"
                     f"?ccy={coin}&period=1D")
        pts = sorted((int(r[0]), float(r[1])) for r in j["data"])
        if pts:
            d = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).date().isoformat() for t, _ in pts]
            s = series(d, [v for _, v in pts])
            s["source"] = "okx"
            s["unit"] = "usd"
            return s
    except Exception as e:
        errors.append(f"okx: {e}")
    try:
        rows = []
        cursor = ""
        for _ in range(2):  # 2 pages x 200 days
            url = ("https://api.bybit.com/v5/market/open-interest"
                   f"?category=linear&symbol={coin}USDT&intervalTime=1d&limit=200"
                   + (f"&cursor={cursor}" if cursor else ""))
            j = get_json(url)
            rows.extend(j["result"]["list"])
            cursor = j["result"].get("nextPageCursor") or ""
            if not cursor:
                break
        pts = sorted((int(r["timestamp"]), float(r["openInterest"])) for r in rows)
        if pts:
            d = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).date().isoformat() for t, _ in pts]
            s = series(d, [v for _, v in pts])
            s["source"] = "bybit"
            s["unit"] = "base"
            return s
    except Exception as e:
        errors.append(f"bybit: {e}")
    try:
        j = get_json("https://fapi.binance.com/futures/data/openInterestHist"
                     f"?symbol={coin}USDT&period=1d&limit=200")
        pts = sorted((int(r["timestamp"]), float(r["sumOpenInterest"])) for r in j)
        if pts:
            d = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).date().isoformat() for t, _ in pts]
            s = series(d, [v for _, v in pts])
            s["source"] = "binance"
            s["unit"] = "base"
            return s
    except Exception as e:
        errors.append(f"binance: {e}")
    raise FetchError("open interest failed on all exchanges: " + " | ".join(errors))


def long_short_ratio(coin: str = "BTC") -> dict:
    """OKX account long/short ratio, daily."""
    j = get_json("https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
                 f"?ccy={coin}&period=1D")
    pts = sorted((int(t), float(v)) for t, v in j["data"])
    d = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).date().isoformat() for t, _ in pts]
    s = series(d, [v for _, v in pts])
    s["source"] = "okx"
    return s


# ------------------------------------------------------- calendar & news ----

def econ_calendar() -> list[dict]:
    j = get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    out = []
    for r in j:
        out.append({
            "title": r.get("title", ""),
            "country": r.get("country", ""),
            "date": r.get("date", ""),
            "impact": r.get("impact", ""),
            "forecast": r.get("forecast", ""),
            "previous": r.get("previous", ""),
        })
    return out


NEWS_FEEDS = [
    ("CoinDesk", "crypto", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "crypto", "https://cointelegraph.com/rss"),
    ("Decrypt", "crypto", "https://decrypt.co/feed"),
    ("WSJ Markets", "macro", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("MarketWatch", "macro", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
]

_TAG_RE = re.compile(r"<[^>]+>")


def news(max_per_feed: int = 8) -> list[dict]:
    """Headlines + links from RSS feeds. Per-feed failures are skipped."""
    items = []
    for source, kind, url in NEWS_FEEDS:
        try:
            root = ET.fromstring(get(url).decode("utf-8", errors="replace"))
            for item in root.iter("item"):
                title = html.unescape(_TAG_RE.sub("", (item.findtext("title") or "").strip()))
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                iso = ""
                if pub:
                    try:
                        iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
                    except Exception:
                        pass
                if title and link:
                    items.append({"title": title[:200], "link": link, "source": source,
                                  "kind": kind, "published": iso})
                if sum(1 for i in items if i["source"] == source) >= max_per_feed:
                    break
        except Exception:
            continue
    items.sort(key=lambda i: i["published"], reverse=True)
    return items
