"""Validates the generated site/data/*.json files.

Checks three layers:
  1. structure  — files exist, parse, and contain the expected keys
  2. freshness  — each series' last observation is recent enough for its cadence
  3. sanity     — latest values sit inside wide plausibility ranges, so a
                  silently-broken source (unit change, wrong column, garbage)
                  fails loudly instead of publishing a nonsense chart

Exit code 0 = healthy, 1 = problems (printed). Used by CI and by tests.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "data")

# key → (max_staleness_days_for_last_observation, min_plausible, max_plausible)
MACRO_RULES = {
    "net_liquidity": (16, 1.0, 12.0),        # $T
    "global_cb": (16, 8.0, 40.0),            # $T
    "m2_yoy": (100, -8.0, 30.0),             # % (M2 publishes ~2 months behind)
    "cpi_yoy": (75, -3.0, 20.0),             # %
    "core_cpi_yoy": (75, -2.0, 15.0),        # %
    "unrate": (75, 2.0, 15.0),               # %
    "fedfunds": (75, 0.0, 12.0),             # %
    "dgs10": (7, 0.0, 12.0),                 # %
    "t10y2y": (7, -3.0, 4.0),                # %
    "t10y3m": (7, -3.0, 5.0),                # %
    "hy_oas": (7, 1.5, 25.0),                # %
    "dxy_broad": (10, 80.0, 150.0),          # index
    "vix": (7, 8.0, 90.0),                   # index
    "spx": (7, 2000.0, 20000.0),             # index
    "nasdaq": (7, 5000.0, 60000.0),          # index
    "oil": (10, 5.0, 250.0),                 # $/bbl
}

CRYPTO_RULES = {
    "btc_price": (3, 5000.0, 1_000_000.0),   # $
    "btc_mvrv": (14, 0.3, 10.0),             # bitcoin-data.com lags ~1 week
    "btc_mayer": (5, 0.2, 5.0),
    "btc_realized": (14, 5000.0, 500_000.0),
    "eth_price": (3, 100.0, 100_000.0),
    "ethbtc": (5, 0.005, 0.3),
    "fng": (4, 0.0, 100.0),
    "stablecoin_mcap": (6, 50.0, 3000.0),    # $B
    "btc_hashrate": (7, 1e7, 1e12),          # TH-scale, wide
}


class Problems(list):
    def check(self, cond: bool, msg: str):
        if not cond:
            self.append(msg)


def _load(name: str, problems: Problems):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        problems.append(f"{name}: file missing")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        problems.append(f"{name}: unparseable ({e})")
        return None


def _staleness_days(iso_date: str) -> float:
    d = date.fromisoformat(iso_date[:10])
    return (datetime.now(timezone.utc).date() - d).days


def check_series_block(doc: dict, rules: dict, fname: str, problems: Problems):
    series = doc.get("series", {})
    for key, (max_stale, lo, hi) in rules.items():
        s = series.get(key)
        if not s or not s.get("values"):
            problems.append(f"{fname}:{key} missing/empty")
            continue
        if len(s["dates"]) != len(s["values"]):
            problems.append(f"{fname}:{key} dates/values length mismatch")
            continue
        stale = _staleness_days(s["dates"][-1])
        if stale > max_stale:
            problems.append(f"{fname}:{key} stale — last obs {s['dates'][-1]} ({stale:.0f}d > {max_stale}d)")
        v = s["values"][-1]
        if not (lo <= v <= hi):
            problems.append(f"{fname}:{key} implausible latest value {v} (expected {lo}–{hi})")
        if s["dates"] != sorted(s["dates"]):
            problems.append(f"{fname}:{key} dates not sorted")


def validate() -> Problems:
    problems = Problems()

    macro = _load("macro.json", problems)
    if macro:
        check_series_block(macro, MACRO_RULES, "macro.json", problems)

    crypto = _load("crypto.json", problems)
    if crypto:
        check_series_block(crypto, CRYPTO_RULES, "crypto.json", problems)
        rb = crypto.get("rainbow", {})
        problems.check(bool(rb.get("bands")) and len(rb.get("bands", [])) == len(rb.get("ks", [])),
                       "crypto.json: rainbow bands malformed")
        problems.check(0.0 < rb.get("sigma", 0) < 2.0,
                       f"crypto.json: rainbow sigma implausible ({rb.get('sigma')})")
        spot = crypto.get("spot", {})
        problems.check(spot.get("btc", 0) > 5000, "crypto.json: spot btc implausible")

    signals = _load("signals.json", problems)
    if signals:
        reads = signals.get("reads", {})
        problems.check(len(reads) >= 15, f"signals.json: only {len(reads)} reads (expected ≥15)")
        for k, r in reads.items():
            problems.check(r.get("signal") in ("good", "neutral", "caution", "info"),
                           f"signals.json:{k} bad signal '{r.get('signal')}'")
            problems.check(bool(r.get("text")), f"signals.json:{k} empty text")
        g = signals.get("gauges", {})
        for name in ("liquidity_impulse", "risk_appetite", "crypto_cycle"):
            score = g.get(name, {}).get("score")
            problems.check(score is not None and 0 <= score <= 100,
                           f"signals.json: gauge {name} score invalid ({score})")
        problems.check(bool(g.get("regime", {}).get("name")), "signals.json: regime missing")

    derivs = _load("derivs.json", problems)
    if derivs is not None and derivs:
        has_any = any(derivs.get(k) for k in ("funding", "open_interest", "long_short"))
        problems.check(has_any, "derivs.json: no derivative series at all")

    newscal = _load("newscal.json", problems)
    if newscal:
        problems.check(len(newscal.get("news", [])) >= 5,
                       f"newscal.json: only {len(newscal.get('news', []))} news items")

    war = _load("war.json", problems)
    if war:
        b = war.get("brent", {})
        problems.check(bool(b.get("values")), "war.json: brent missing")
        if b.get("values"):
            problems.check(15.0 <= b["values"][-1] <= 400.0,
                           f"war.json: brent implausible ({b['values'][-1]})")
            problems.check(_staleness_days(b["dates"][-1]) <= 8, "war.json: brent stale")
        cps = war.get("chokepoints", {})
        for key in ("hormuz", "bab_el_mandeb", "suez"):
            cp = cps.get(key)
            if not cp or not cp.get("dates"):
                problems.append(f"war.json: chokepoint {key} missing")
                continue
            problems.check(_staleness_days(cp["dates"][-1]) <= 8,
                           f"war.json: {key} flows stale (last {cp['dates'][-1]})")
            problems.check(len(cp["dates"]) == len(cp["tankers"]),
                           f"war.json: {key} length mismatch")
            problems.check(all(0 <= v <= 200 for v in cp["tankers"][-30:]),
                           f"war.json: {key} implausible tanker counts")
        div = war.get("divergence", {})
        problems.check(div.get("state") in ("disruption_underpriced", "disruption_priced",
                                            "premium_no_disruption", "aligned", "unknown"),
                       f"war.json: bad divergence state '{div.get('state')}'")

    meta = _load("meta.json", problems)
    if meta:
        gen = meta.get("generated_at", "1970-01-01")
        problems.check(_staleness_days(gen) <= 2, f"meta.json: pipeline last ran {gen}")

    return problems


def main() -> int:
    problems = validate()
    if problems:
        print(f"VALIDATION: {len(problems)} problem(s)")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("VALIDATION: OK — all files healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
