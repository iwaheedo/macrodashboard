"""Transparent composite gauges: Liquidity Impulse, Risk Appetite, Crypto Cycle,
and the overall Macro Regime quadrant.

Unlike black-box "alpha scores", every component and weight here is documented
and shipped to the site so the user can see exactly why a gauge reads what it
reads. All scores are 0–100.
"""
from __future__ import annotations

from transform import (change_over, last, last_date, pct_change_over,
                       percentile_rank, trailing_window, value_asof)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pct_of_changes(s: dict, days: int, years: float = 5.0) -> float | None:
    """Percentile of the latest `days`-change vs the same change historically."""
    if len(s["values"]) < 30:
        return None
    ch = change_over(s, days)
    if ch is None:
        return None
    # build historical distribution of rolling changes
    vals, dates = s["values"], s["dates"]
    window = trailing_window(s, years)
    n = len(window)
    if n < 30:
        return None
    offset = len(vals) - n
    # approximate index distance for `days` using median spacing
    span = max(1, round(days / max(1, (_avg_spacing(dates)))))
    changes = [vals[i] - vals[i - span] for i in range(offset + span, len(vals))]
    if not changes:
        return None
    return percentile_rank(changes, ch)


def _avg_spacing(dates: list[str]) -> float:
    from datetime import date
    if len(dates) < 2:
        return 1.0
    total = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    return max(0.5, total / (len(dates) - 1))


def component(name: str, score: float | None, note: str) -> dict:
    return {"name": name, "score": None if score is None else round(score),
            "note": note}


def gauge(score_components: list[dict], label_bands: list[tuple]) -> dict:
    scores = [c["score"] for c in score_components if c["score"] is not None]
    score = round(sum(scores) / len(scores)) if scores else None
    label = ""
    if score is not None:
        for limit, name in label_bands:
            if score <= limit:
                label = name
                break
    return {"score": score, "label": label, "components": score_components}


def liquidity_impulse(net_liq: dict, global_cb: dict, m2_yoy: dict) -> dict:
    comps = [
        component("Fed net liquidity, 13-week change",
                  _pct_of_changes(net_liq, 91),
                  "Is the Fed adding or draining dollars vs its own recent history?"),
        component("Global central bank assets, 13-week change",
                  _pct_of_changes(global_cb, 91),
                  "Are the Fed, ECB and BoJ collectively expanding?"),
        component("US M2 growth, 6-month direction",
                  _pct_of_changes(m2_yoy, 183, years=10),
                  "Is money-supply growth accelerating or decelerating?"),
    ]
    return gauge(comps, [(19, "Draining fast"), (39, "Draining"),
                         (60, "Neutral"), (80, "Expanding"), (100, "Expanding fast")])


def risk_appetite(vix: dict, hy_oas: dict, spx: dict, spx200: dict) -> dict:
    v_pct = percentile_rank(trailing_window(vix, 5), last(vix)) if vix["values"] else None
    h_pct = percentile_rank(trailing_window(hy_oas, 5), last(hy_oas)) if hy_oas["values"] else None
    trend = None
    if spx["values"]:
        ma = value_asof(spx200, last_date(spx))
        if ma:
            dist = (last(spx) / ma - 1) * 100          # −10% → 0, +10% → 100
            trend = _clamp((dist + 10) * 5)
    comps = [
        component("Volatility (VIX, 5-yr percentile, inverted)",
                  None if v_pct is None else 100 - v_pct,
                  "Calm markets = higher appetite."),
        component("Credit spreads (HY OAS, 5-yr percentile, inverted)",
                  None if h_pct is None else 100 - h_pct,
                  "Tight spreads = credit investors are confident."),
        component("S&P 500 vs 200-day trend",
                  trend, "Price above trend = equity investors are risk-on."),
    ]
    return gauge(comps, [(19, "Fear"), (39, "Defensive"), (60, "Neutral"),
                         (80, "Risk-on"), (100, "Exuberant")])


def crypto_cycle(mvrv: dict, mayer: dict, fng: dict, price: dict, ma200w: dict) -> dict:
    m_pct = percentile_rank(mvrv["values"], last(mvrv)) if mvrv["values"] else None
    y_pct = percentile_rank(mayer["values"], last(mayer)) if mayer["values"] else None
    f_val = last(fng) if fng["values"] else None
    stretch = None
    if price["values"]:
        w = value_asof(ma200w, last_date(price))
        if w:
            ratios = []
            for dt, v in zip(price["dates"], price["values"]):
                wv = value_asof(ma200w, dt)
                if wv:
                    ratios.append(v / wv)
            if ratios:
                stretch = percentile_rank(ratios, last(price) / w)
    comps = [
        component("MVRV percentile (full history)", m_pct,
                  "How large are aggregate unrealized profits?"),
        component("Mayer Multiple percentile", y_pct,
                  "How stretched is price vs its 200-day trend?"),
        component("Fear & Greed index", f_val, "Crowd sentiment right now."),
        component("Price vs 200-week trend, percentile", stretch,
                  "How far into the cycle is price vs its long-term base?"),
    ]
    return gauge(comps, [(19, "Deep winter"), (39, "Early cycle"),
                         (60, "Mid cycle"), (80, "Late cycle"), (100, "Euphoria")])


REGIME_MATRIX = {
    # (liquidity_bucket, risk_bucket): (name, summary, playbook)
    ("up", "up"): ("Liquidity tailwind · Risk-on",
                   "Central banks are adding liquidity and markets are embracing risk. Historically the most rewarding regime for risk assets — and where crypto has done its best work.",
                   ["Historically favored: equities, crypto, high-beta assets",
                    "Historically lagged: cash, defensive sectors",
                    "Classic mistake: being under-invested and chasing late"]),
    ("up", "down"): ("Liquidity tailwind · Risk-off",
                     "Liquidity is improving but markets are still defensive — the setup that has often preceded durable bottoms.",
                     ["Historically favored: quality bonds, gold, starting to average into risk",
                      "Historically lagged: panic selling into strength of safe assets",
                      "Classic mistake: waiting for 'all clear' news that arrives after the low"]),
    ("down", "up"): ("Liquidity drain · Risk-on",
                     "Markets are risk-on while liquidity quietly drains — rallies in this regime run on borrowed time and narrow leadership.",
                     ["Historically favored: staying invested but trimming leverage and froth",
                      "Historically lagged: maximum-risk positioning",
                      "Classic mistake: mistaking a liquidity-starved melt-up for a new cycle"]),
    ("down", "down"): ("Liquidity drain · Risk-off",
                       "Liquidity is draining and risk appetite is gone. Historically the regime where capital preservation beats everything.",
                       ["Historically favored: cash/T-bills, patience, shopping lists",
                        "Historically lagged: catching falling knives with leverage",
                        "Classic mistake: assuming the first bounce is the bottom"]),
    ("flat", "flat"): ("Transition",
                       "Neither liquidity nor risk appetite has a clear direction. Markets chop until one of them commits.",
                       ["Historically favored: balanced allocation, patience",
                        "Historically lagged: over-trading the chop",
                        "Classic mistake: extrapolating each swing into a new regime"]),
}


def regime(liq: dict, risk: dict) -> dict:
    def bucket(score):
        if score is None:
            return "flat"
        return "up" if score >= 55 else ("down" if score <= 45 else "flat")

    lb, rb = bucket(liq.get("score")), bucket(risk.get("score"))
    key = (lb, rb)
    if key not in REGIME_MATRIX:
        # mixed/flat combos: fall back to the dominant axis, else transition
        key = ("flat", "flat") if lb == "flat" and rb == "flat" else (
            (lb if lb != "flat" else "up" if rb == "up" else "down",
             rb if rb != "flat" else "up" if lb == "up" else "down"))
    name, summary, playbook = REGIME_MATRIX.get(key, REGIME_MATRIX[("flat", "flat")])
    return {"liquidity_bucket": lb, "risk_bucket": rb, "name": name,
            "summary": summary, "playbook": playbook}
