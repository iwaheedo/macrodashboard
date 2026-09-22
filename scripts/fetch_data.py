"""Pipeline orchestrator: fetch every source → compute → write site/data/*.json.

Failure policy
  critical sources (FRED, Coin Metrics, Fear&Greed, DefiLlama):
      a failure keeps the previous JSON on disk and exits non-zero so CI alerts.
  best-effort sources (derivatives, calendar, news, spot, global mcap, gold/DXY):
      a failure keeps the previous JSON and is recorded in meta.json, run stays green
      unless the stale file is older than STALE_FAIL_DAYS.

Run:  python3 scripts/fetch_data.py [--only macro|crypto|derivs|newscal]
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import composites
import interpret as I
import sources as S
from transform import (downsample_weekly, last, last_date, log_regression_bands,
                       merge_series, ratio_asof, series, since, sma, tail,
                       to_daily, value_asof, yoy)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "data")
STALE_FAIL_DAYS = 7

MACRO_START = "2000-01-01"
CHART_START = "2015-01-01"     # what ships to the site for most macro charts


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(name: str, payload: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, path)
    print(f"  wrote {name} ({os.path.getsize(path)//1024} KB)")


def file_age_days(name: str) -> float | None:
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            fetched = json.load(f).get("fetched_at")
        dt = datetime.strptime(fetched, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


# ------------------------------------------------------------------ macro ---

def build_macro() -> dict:
    """FRED block → macro.json contents. Raises on failure (critical)."""
    daily = S.fred(["DGS10", "DGS2", "DGS3MO", "T10Y2Y", "T10Y3M", "VIXCLS",
                    "SP500", "NASDAQCOM", "DCOILWTICO", "DTWEXBGS",
                    "BAMLH0A0HYM2", "RRPONTSYD", "DEXJPUS", "DEXUSEU"],
                   start=MACRO_START)
    weekly = S.fred(["WALCL", "WTREGEN", "ECBASSETSW"], start="2003-01-01")
    monthly = S.fred(["M2SL", "CPIAUCSL", "CPILFESL", "UNRATE", "FEDFUNDS",
                      "JPNASSETS"], start="1990-01-01")

    walcl, tga, rrp = weekly["WALCL"], weekly["WTREGEN"], daily["RRPONTSYD"]
    # net liquidity in $T on WALCL (Wednesday) dates:
    #   WALCL ($ millions) − WTREGEN ($ millions) − RRPONTSYD ($ billions)
    nl_d, nl_v = [], []
    for dt, w in zip(walcl["dates"], walcl["values"]):
        t = value_asof(tga, dt)
        r = value_asof(rrp, dt)
        if t is None:
            continue
        nl_d.append(dt)
        nl_v.append(w / 1e6 - t / 1e6 - (r or 0.0) / 1e3)
    net_liq = series(nl_d, nl_v)

    # global big-3 balance sheets in $T (Fed $M, ECB €M × EURUSD, BoJ ¥100M / JPYUSD)
    gcb_d, gcb_v = [], []
    ecb, boj = weekly["ECBASSETSW"], monthly["JPNASSETS"]
    eur, jpy = daily["DEXUSEU"], daily["DEXJPUS"]
    for dt, w in zip(walcl["dates"], walcl["values"]):
        e, j = value_asof(ecb, dt), value_asof(boj, dt)
        eu, jp = value_asof(eur, dt), value_asof(jpy, dt)
        if None in (e, j, eu, jp) or not jp:
            continue
        gcb_d.append(dt)
        gcb_v.append(w / 1e6 + e * eu / 1e6 + j / (jp * 1e4))
    global_cb = series(gcb_d, gcb_v)

    m2_yoy = yoy(monthly["M2SL"])
    cpi_yoy = yoy(monthly["CPIAUCSL"])
    core_yoy = yoy(monthly["CPILFESL"])
    spx200 = sma(daily["SP500"], 200)
    ndx200 = sma(daily["NASDAQCOM"], 200)

    out = {
        "fetched_at": now_iso(),
        "series": {
            "net_liquidity": since(net_liq, "2011-01-01"),
            "global_cb": since(global_cb, "2011-01-01"),
            "m2_yoy": since(m2_yoy, "2000-01-01"),
            "cpi_yoy": since(cpi_yoy, "2000-01-01"),
            "core_cpi_yoy": since(core_yoy, "2000-01-01"),
            "unrate": since(monthly["UNRATE"], "2000-01-01"),
            "fedfunds": since(monthly["FEDFUNDS"], "2000-01-01"),
            "dgs10": since(daily["DGS10"], CHART_START),
            "dgs2": since(daily["DGS2"], CHART_START),
            "t10y2y": since(daily["T10Y2Y"], "2000-01-01"),
            "t10y3m": since(daily["T10Y3M"], "2000-01-01"),
            "hy_oas": since(daily["BAMLH0A0HYM2"], "2000-01-01"),
            "dxy_broad": since(daily["DTWEXBGS"], CHART_START),
            "vix": since(daily["VIXCLS"], CHART_START),
            "spx": since(daily["SP500"], CHART_START),
            "spx_200dma": since(spx200, CHART_START),
            "nasdaq": since(daily["NASDAQCOM"], CHART_START),
            "nasdaq_200dma": since(ndx200, CHART_START),
            "oil": since(daily["DCOILWTICO"], CHART_START),
        },
    }
    # best-effort Yahoo extras (classic DXY + gold futures)
    for key, sym in (("dxy", "DX-Y.NYB"), ("gold", "GC=F")):
        try:
            out["series"][key] = S.yahoo_chart(sym, range_="10y")
            out["series"][key]["source"] = "yahoo"
        except Exception as e:
            print(f"  note: yahoo {sym} unavailable ({e}); site falls back")
    if "gold" not in out["series"]:
        try:
            g = S.paxg_gold_proxy()
            g["source"] = "paxg"
            out["series"]["gold"] = g
        except Exception as e:
            print(f"  note: PAXG gold fallback also unavailable ({e})")
    return out


# ----------------------------------------------------------------- crypto ---

def build_crypto() -> dict:
    # BTC price: sampled full history + daily 1y, forward-filled to a daily grid
    price = to_daily(merge_series(S.blockchain_chart("market-price", "all"),
                                  S.blockchain_chart("market-price", "1year")))
    mcap = merge_series(S.blockchain_chart("market-cap", "all"),
                        S.blockchain_chart("market-cap", "1year"))
    hashrate = S.blockchain_chart("hash-rate", "5years")
    active = S.blockchain_chart("n-unique-addresses", "2years")

    # bitcoin-data.com rate-limits aggressively; salvage the previous file's
    # series if a call fails (validation allows these to lag up to 14 days)
    prev = _load("crypto.json") or {}
    mvrv = _fetch_or_salvage(lambda: S.bitcoin_data("mvrv"),
                             prev, "btc_mvrv", "MVRV")
    realized = _fetch_or_salvage(lambda: S.bitcoin_data("realized-price"),
                                 prev, "btc_realized", "realized price")

    ma200d = sma(price, 200)
    ma200w = sma(price, 1400)  # 200 weeks on daily data
    mayer = ratio_asof(price, ma200d)
    rainbow = log_regression_bands(price)

    eth = S.coinbase_candles("ETH-USD", 2016)
    ethbtc = S.coinbase_candles("ETH-BTC", 2017)

    fng = S.fear_greed()
    stables = S.stablecoin_mcap()

    spot = {}
    for coin, pair, hist in (("btc", "BTC-USD", price), ("eth", "ETH-USD", eth)):
        try:
            spot[coin] = S.coinbase_spot(pair)
        except Exception:
            spot[coin] = last(hist)
    try:
        spot.update(S.global_crypto())
    except Exception as e:
        print(f"  note: global mcap unavailable ({e})")
    majors, sectors = [], []
    try:
        majors = S.top_coins()
        sectors = S.sector_performance()
    except Exception as e:
        print(f"  note: majors/sectors unavailable ({e})")
    if not majors:
        majors = (prev.get("majors") or [])
        sectors = (prev.get("sectors") or [])

    # splice live spot onto slightly-lagged history so "current" reads match
    today = datetime.now(timezone.utc).date().isoformat()
    for s, key in ((price, "btc"), (eth, "eth")):
        if s["dates"] and s["dates"][-1] < today and key in spot:
            s["dates"].append(today)
            s["values"].append(spot[key])

    cut = "2013-01-01"
    ds = "2020-01-01"  # weekly sampling before this date to shrink JSON
    return {
        "fetched_at": now_iso(),
        "spot": spot,
        "majors": majors,
        "sectors": sectors,
        "rainbow": rainbow,
        "series": {
            "btc_price": downsample_weekly(since(price, cut), ds),
            "btc_200dma": downsample_weekly(since(ma200d, cut), ds),
            "btc_200wma": downsample_weekly(since(ma200w, cut), ds),
            "btc_realized": downsample_weekly(since(realized, cut), ds),
            "btc_mvrv": downsample_weekly(since(mvrv, cut), ds),
            "btc_mayer": downsample_weekly(since(mayer, cut), ds),
            "btc_mcap": downsample_weekly(since(mcap, cut), ds),
            "btc_hashrate": since(hashrate, "2021-09-01"),
            "btc_active_addr": since(active, "2024-09-01"),
            "eth_price": downsample_weekly(since(eth, "2016-06-01"), ds),
            "ethbtc": downsample_weekly(since(ethbtc, "2017-01-01"), ds),
            "fng": fng,
            "stablecoin_mcap": since(stables, "2019-01-01"),
        },
    }


def _fetch_or_salvage(fetch, prev: dict, key: str, label: str) -> dict:
    """Fetch a series; on failure fall back to the previous run's copy."""
    try:
        return fetch()
    except Exception as e:
        old = (prev.get("series") or {}).get(key)
        if old and old.get("values"):
            print(f"  note: {label} fetch failed ({e}); reusing previous data "
                  f"(last obs {old['dates'][-1]})")
            return {"dates": old["dates"], "values": old["values"]}
        raise


# ------------------------------------------------------------ derivatives ---

def build_derivs() -> dict:
    out = {"fetched_at": now_iso(), "funding": {}, "open_interest": {}, "long_short": {}}
    prev = _load("derivs.json") or {}
    ok = False

    def attempt(group: str, key: str, fetch):
        nonlocal ok
        try:
            out[group][key] = fetch()
            ok = True
            return
        except Exception as e:
            print(f"  note: {group}/{key} unavailable ({e})")
        old = (prev.get(group) or {}).get(key)
        if old and old.get("values"):
            print(f"  note: {group}/{key} reusing previous data (last obs {old['dates'][-1]})")
            out[group][key] = old

    attempt("funding", "btc", lambda: S.funding_history("BTC"))
    attempt("funding", "eth", lambda: S.funding_history("ETH"))
    attempt("open_interest", "btc", lambda: S.open_interest_history("BTC"))
    attempt("long_short", "btc", lambda: S.long_short_ratio("BTC"))
    if not ok:
        raise S.FetchError("every derivatives endpoint failed")
    return out


# ------------------------------------------------------------- war risk ----

DISPLAY_SINCE = "2023-01-01"     # what ships to the chart

# Per-chokepoint PRE-WAR baseline windows: (fetch_since, base_start, base_end,
# label). Each strait is measured against its own last-normal period, not a
# global year — 2023 is already war-affected for the Black Sea, and includes
# the start of the Houthi campaign for the Red Sea.
BASELINE_WINDOWS = {
    "hormuz":         ("2023-01-01", "2024-11-01", "2025-10-31", "pre-crisis year (Nov ’24–Oct ’25)"),
    "bab_el_mandeb":  ("2023-01-01", "2023-01-01", "2023-10-31", "pre-Houthi campaign (Jan–Oct ’23)"),
    "suez":           ("2023-01-01", "2023-01-01", "2023-10-31", "pre-Houthi campaign (Jan–Oct ’23)"),
    "cape_good_hope": ("2023-01-01", "2023-01-01", "2023-10-31", "pre-rerouting (Jan–Oct ’23)"),
    "bosporus":       ("2019-01-01", "2019-01-01", "2022-01-31", "pre-invasion (2019–Jan ’22)"),
    "kerch":          ("2019-01-01", "2019-01-01", "2022-01-31", "pre-invasion (2019–Jan ’22)"),
    "taiwan_strait":  ("2023-01-01", "2024-01-01", "2025-12-31", "recent calm norm (2024–25)"),
}


def _window_mean(dates: list[str], vals: list, start: str, end: str) -> float | None:
    xs = [v for d, v in zip(dates, vals) if start <= d <= end]
    return sum(xs) / len(xs) if xs else None


def _ma(vals: list[float], window: int) -> list[float | None]:
    out, acc = [], 0.0
    for i, v in enumerate(vals):
        acc += v
        if i >= window:
            acc -= vals[i - window]
        out.append(round(acc / window, 1) if i >= window - 1 else None)
    return out


def build_war() -> dict:
    prev = _load("war.json") or {}
    brent = S.fred(["DCOILBRENTEU"], start=DISPLAY_SINCE)["DCOILBRENTEU"]

    chokepoints = {}
    for key, (portid, label) in S.CHOKEPOINTS.items():
        fetch_since, base_start, base_end, base_label = BASELINE_WINDOWS[key]
        try:
            raw = S.portwatch_chokepoint(portid, since=fetch_since)
        except Exception as e:
            old = (prev.get("chokepoints") or {}).get(key)
            if old:
                print(f"  note: portwatch {key} failed ({e}); reusing previous data")
                if "baseline" not in old and "baseline_2023" in old:  # pre-rename files
                    old["baseline"] = old.pop("baseline_2023")
                    old["baseline_label"] = "2023 average"
                chokepoints[key] = old
                continue
            raise
        # baseline over the pre-war window, computed BEFORE slicing to display
        baseline = _window_mean(raw["dates"], raw["tankers"], base_start, base_end)
        cut = next((i for i, d in enumerate(raw["dates"]) if d >= DISPLAY_SINCE), 0)
        dates = raw["dates"][cut:]
        tankers = raw["tankers"][cut:]
        ma14 = _ma(tankers, 14)
        ma_last = next((v for v in reversed(ma14) if v is not None), None)
        dev = None
        if baseline and ma_last is not None:
            dev = (ma_last / baseline - 1.0) * 100.0
        chokepoints[key] = {
            "label": label,
            "dates": dates,
            "tankers": tankers,
            "tankers_ma14": ma14,
            "dwt_ma14": _ma(raw["dwt"][cut:], 14),
            "baseline": None if baseline is None else round(baseline, 1),
            "baseline_label": base_label,
            "ma14_last": ma_last,
            "dev_pct": None if dev is None else round(dev, 1),
        }

    reads = {}
    for key, cp in chokepoints.items():
        reads[key] = I.read_chokepoint(cp["label"], cp.get("dev_pct"), cp.get("ma14_last"),
                                       cp.get("baseline"),
                                       reroute=(key == "cape_good_hope"))
    reads["brent"] = I.read_brent(brent)

    corridor_devs = [chokepoints[k].get("dev_pct") for k in ("hormuz", "bab_el_mandeb", "suez")
                     if chokepoints.get(k, {}).get("dev_pct") is not None]
    corridor_dev = sum(corridor_devs) / len(corridor_devs) if corridor_devs else None
    from transform import pct_change_over
    divergence = I.flow_price_divergence(corridor_dev, pct_change_over(brent, 30),
                                         last(brent) if brent["values"] else None)
    divergence["corridor_dev_pct"] = None if corridor_dev is None else round(corridor_dev, 1)
    divergence["brent_chg30_pct"] = (None if pct_change_over(brent, 30) is None
                                     else round(pct_change_over(brent, 30), 1))

    news = S.war_news()
    if not news:
        news = prev.get("news") or []

    return {"fetched_at": now_iso(), "brent": brent, "chokepoints": chokepoints,
            "divergence": divergence, "reads": reads, "news": news}


# ---------------------------------------------------------- news/calendar ---

def build_newscal() -> dict:
    out = {"fetched_at": now_iso(), "news": [], "calendar": []}
    try:
        out["calendar"] = S.econ_calendar()
    except Exception as e:
        print(f"  note: calendar unavailable ({e})")
    out["news"] = S.news()
    if not out["news"] and not out["calendar"]:
        raise S.FetchError("both news and calendar failed")
    return out


# ---------------------------------------------------------------- signals ---

def build_signals(macro: dict, crypto: dict, derivs: dict, war: dict | None = None) -> dict:
    ms, cs = macro["series"], crypto["series"]
    reads = {}

    def safe(key, fn, *args):
        try:
            reads[key] = fn(*args)
        except Exception as e:
            print(f"  note: read '{key}' skipped ({e})")

    safe("net_liquidity", I.read_net_liquidity, ms["net_liquidity"])
    safe("global_cb", I.read_global_cb, ms["global_cb"])
    safe("m2_yoy", I.read_m2_yoy, ms["m2_yoy"])
    safe("yield_curve", I.read_yield_curve, ms["t10y2y"], ms["t10y3m"])
    safe("hy_oas", I.read_hy_oas, ms["hy_oas"])
    dollar = ms.get("dxy") or ms["dxy_broad"]
    safe("dollar", I.read_dollar, dollar,
         "DXY" if "dxy" in ms else "The broad dollar index")
    safe("cpi", I.read_cpi, ms["cpi_yoy"], ms["core_cpi_yoy"])
    safe("unrate", I.read_unrate, ms["unrate"])
    safe("fedfunds", I.read_fedfunds, ms["fedfunds"], ms["dgs10"])
    safe("spx", I.read_spx, ms["spx"], ms["spx_200dma"])
    safe("nasdaq", I.read_spx, ms["nasdaq"], ms["nasdaq_200dma"])
    safe("vix", I.read_vix, ms["vix"])
    if "gold" in ms:
        safe("gold", I.read_gold, ms["gold"])
    safe("oil", I.read_oil, ms["oil"])

    safe("btc", I.read_btc, cs["btc_price"], cs["btc_200dma"], cs["btc_200wma"])
    safe("mvrv", I.read_mvrv, cs["btc_mvrv"])
    safe("mayer", I.read_mayer, cs["btc_mayer"])
    safe("rainbow", I.read_rainbow, cs["btc_price"], crypto["rainbow"])
    safe("realized", I.read_realized, cs["btc_price"], cs["btc_realized"])
    safe("fng", I.read_fng, cs["fng"])
    safe("stables", I.read_stables, cs["stablecoin_mcap"])
    safe("hashrate", I.read_hashrate, cs["btc_hashrate"])
    safe("ethbtc", I.read_ethbtc, cs["ethbtc"])

    if derivs.get("funding", {}).get("btc"):
        safe("funding", I.read_funding, derivs["funding"]["btc"])
    if derivs.get("open_interest", {}).get("btc"):
        btc_px = crypto.get("spot", {}).get("btc") or last(cs["btc_price"])
        safe("open_interest", I.read_oi, derivs["open_interest"]["btc"], btc_px)
    if derivs.get("long_short", {}).get("btc"):
        safe("long_short", I.read_long_short, derivs["long_short"]["btc"])

    liq = composites.liquidity_impulse(ms["net_liquidity"], ms["global_cb"], ms["m2_yoy"])
    risk = composites.risk_appetite(ms["vix"], ms["hy_oas"], ms["spx"], ms["spx_200dma"])
    cyc = composites.crypto_cycle(cs["btc_mvrv"], cs["btc_mayer"], cs["fng"],
                                  cs["btc_price"], cs["btc_200wma"])
    reg = composites.regime(liq, risk)

    out = {"generated_at": now_iso(), "reads": reads,
           "gauges": {"liquidity_impulse": liq, "risk_appetite": risk,
                      "crypto_cycle": cyc, "regime": reg}}
    if war and war.get("divergence"):
        d = war["divergence"]
        out["war"] = {k: d.get(k) for k in ("state", "signal", "title",
                                            "corridor_dev_pct", "brent_chg30_pct")}
    return out


# ------------------------------------------------------------------- main ---

STAGES = {
    "macro": (build_macro, "macro.json", True),
    "crypto": (build_crypto, "crypto.json", True),
    "derivs": (build_derivs, "derivs.json", False),
    "newscal": (build_newscal, "newscal.json", False),
    "war": (build_war, "war.json", False),
}


def main(argv: list[str]) -> int:
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    results, meta_sources, hard_fail = {}, {}, False

    for name, (builder, filename, critical) in STAGES.items():
        if only and name != only:
            continue
        print(f"[{name}] fetching…")
        try:
            payload = builder()
            write_json(filename, payload)
            results[name] = payload
            meta_sources[name] = {"ok": True, "fetched_at": payload["fetched_at"], "error": None}
        except Exception as e:
            traceback.print_exc()
            age = file_age_days(filename)
            meta_sources[name] = {"ok": False, "fetched_at": None,
                                  "error": f"{type(e).__name__}: {e}",
                                  "stale_days": None if age is None else round(age, 1)}
            if critical or age is None or age > STALE_FAIL_DAYS:
                hard_fail = True
                print(f"[{name}] FAILED (critical={critical}, stale={age})")
            else:
                print(f"[{name}] failed; keeping {age:.1f}-day-old data (non-critical)")

    if not only or only in ("macro", "crypto"):
        # signals need macro + crypto; load from disk for stages not re-run
        try:
            macro = results.get("macro") or _load("macro.json")
            crypto = results.get("crypto") or _load("crypto.json")
            derivs = results.get("derivs") or _load("derivs.json") or {}
            war = results.get("war") or _load("war.json")
            if not macro or not crypto:
                raise RuntimeError("signals skipped: macro/crypto data unavailable")
            signals = build_signals(macro, crypto, derivs, war)
            write_json("signals.json", signals)
            meta_sources["signals"] = {"ok": True, "fetched_at": signals["generated_at"], "error": None}
        except Exception as e:
            traceback.print_exc()
            meta_sources["signals"] = {"ok": False, "error": str(e)}
            hard_fail = True

    write_json("meta.json", {"generated_at": now_iso(), "sources": meta_sources,
                             "version": 1})
    print("PIPELINE:", "FAILED" if hard_fail else "OK")
    return 1 if hard_fail else 0


def _load(name: str):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
