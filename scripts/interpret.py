"""Turns raw series into signals and plain-English current reads.

Every chart on the site gets a "read": {value, signal, text}. Signals are one of
  good     — historically supportive for risk assets
  neutral  — no strong lean
  caution  — historically a headwind / elevated risk
  info     — purely informational, no directional lean

Thresholds are defined here, in one place, and are deliberately simple and
documented. This is educational context based on historical patterns — not
investment advice, and the site says so.
"""
from __future__ import annotations

from transform import (band_position, change_over, last, last_date,
                       pct_change_over, percentile_rank, trailing_window,
                       value_asof)


def _fmt(v: float, nd: int = 2) -> str:
    return f"{v:,.{nd}f}"


def read(value, signal: str, text: str, extra: dict | None = None) -> dict:
    r = {"value": value, "signal": signal, "text": text}
    if extra:
        r.update(extra)
    return r


# ------------------------------------------------------------ macro reads ---

def read_net_liquidity(s):
    v = last(s)
    ch = change_over(s, 91)  # ~13 weeks, in $T
    if ch is None:
        return read(v, "info", f"Fed net liquidity is ${_fmt(v)}T.")
    if ch > 0.05:
        sig, verdict = "good", "expanding — historically a tailwind for stocks and crypto"
    elif ch < -0.05:
        sig, verdict = "caution", "draining — historically a headwind for risk assets"
    else:
        sig, verdict = "neutral", "roughly flat — neither pushing markets up nor down"
    return read(v, sig, f"Net liquidity is ${_fmt(v)}T, {'+' if ch >= 0 else ''}{_fmt(ch)}T over ~3 months: {verdict}.")


def read_global_cb(s):
    v = last(s)
    ch = change_over(s, 91)
    if ch is None:
        return read(v, "info", f"Big-3 central bank assets total ${_fmt(v, 1)}T.")
    pct = ch / (v - ch) * 100 if v != ch else 0
    if pct > 0.7:
        sig, verdict = "good", "the world's money printers are expanding — supportive for all assets, especially crypto and gold"
    elif pct < -0.7:
        sig, verdict = "caution", "central banks are shrinking balance sheets — a global liquidity drain"
    else:
        sig, verdict = "neutral", "global liquidity is moving sideways"
    return read(v, sig, f"Fed + ECB + BoJ hold ${_fmt(v, 1)}T ({'+' if pct >= 0 else ''}{_fmt(pct, 1)}% in ~3 months): {verdict}.")


def read_m2_yoy(s):
    v = last(s)
    ch = change_over(s, 183)
    trend = "accelerating" if (ch or 0) > 0.3 else ("decelerating" if (ch or 0) < -0.3 else "steady")
    if v > 6:
        sig, verdict = "good", "money supply growing fast — plenty of fuel for asset prices (and, eventually, inflation)"
    elif v < 0:
        sig, verdict = "caution", "money supply is shrinking — rare and historically restrictive"
    else:
        sig, verdict = "neutral", "moderate money growth"
    return read(v, sig, f"US M2 is growing {_fmt(v, 1)}% per year and {trend}: {verdict}.")


def read_yield_curve(s10_2, s10_3m):
    v = last(s10_2)
    v3m = last(s10_3m) if s10_3m["values"] else None
    if v < 0:
        sig = "caution"
        verdict = "inverted — this has preceded every US recession since the 1970s, usually by 6–18 months"
    elif v < 0.25:
        sig = "neutral"
        verdict = "barely positive — the bond market is undecided about growth"
    else:
        sig = "good"
        verdict = "positively sloped — the bond market is not pricing a recession"
    extra = f" (10Y−3M: {_fmt(v3m)}%)" if v3m is not None else ""
    return read(v, sig, f"The 10Y−2Y spread is {_fmt(v)}%{extra}: {verdict}.")


def read_hy_oas(s):
    v = last(s)
    if v < 3.5:
        sig, verdict = "good", "credit markets are calm — investors see low default risk. Complacency risk if this stays extreme"
    elif v < 5.0:
        sig, verdict = "neutral", "credit stress is moderate"
    else:
        sig, verdict = "caution", "credit markets are stressed — historically a serious risk-off warning"
    return read(v, sig, f"High-yield spreads are at {_fmt(v)}%: {verdict}.")


def read_dollar(s, label="the dollar"):
    v = last(s)
    ch = pct_change_over(s, 91)
    if ch is None:
        return read(v, "info", f"{label} index is at {_fmt(v)}.")
    if ch < -2:
        sig, verdict = "good", "a weakening dollar — historically a tailwind for crypto, gold, and global risk assets"
    elif ch > 2:
        sig, verdict = "caution", "a strengthening dollar — tightens global financial conditions and pressures risk assets"
    else:
        sig, verdict = "neutral", "the dollar is range-bound — not a major force either way right now"
    return read(v, sig, f"{label} is at {_fmt(v)} ({'+' if ch >= 0 else ''}{_fmt(ch, 1)}% in 3 months): {verdict}.")


def read_cpi(headline, core):
    v = last(headline)
    c = last(core) if core["values"] else None
    ch = change_over(headline, 183)
    trend = "falling" if (ch or 0) < -0.2 else ("rising" if (ch or 0) > 0.2 else "flat")
    if v < 2.5 and trend != "rising":
        sig, verdict = "good", "near the Fed's 2% target — gives the Fed room to cut rates"
    elif v > 4 or (trend == "rising" and v > 3):
        sig, verdict = "caution", "too hot — keeps the Fed hawkish, which pressures both bonds and risk assets"
    else:
        sig, verdict = "neutral", "above target but not alarming — the Fed stays data-dependent"
    extra = f" (core: {_fmt(c, 1)}%)" if c is not None else ""
    return read(v, sig, f"Inflation is {_fmt(v, 1)}%{extra} and {trend}: {verdict}.")


def read_unrate(s):
    v = last(s)
    vals = s["values"]
    low_12m = min(vals[-12:]) if len(vals) >= 12 else v
    rise = v - low_12m
    if rise >= 0.5:
        sig, verdict = "caution", "unemployment is rising off its lows — the classic early-recession pattern (Sahm rule territory)"
    elif v <= 4.2:
        sig, verdict = "good", "the labor market is strong — supports spending and earnings"
    else:
        sig, verdict = "neutral", "the labor market is cooling but not cracking"
    return read(v, sig, f"Unemployment is {_fmt(v, 1)}% (+{_fmt(rise, 1)}pp off the 12-month low): {verdict}.")


def read_fedfunds(ff, dgs10):
    v = last(ff)
    ten = last(dgs10)
    if ten < v - 0.5:
        stance = "the bond market is pricing meaningful rate cuts ahead"
    elif ten > v + 0.5:
        stance = "long rates sit well above the Fed — markets expect rates to stay high or growth/inflation to run hot"
    else:
        stance = "long rates trade close to the Fed's rate — no strong easing or tightening bet"
    return read(v, "info", f"The Fed's policy rate is {_fmt(v)}% vs {_fmt(ten)}% on the 10Y: {stance}.")


def read_spx(price, ma200):
    v = last(price)
    ma = value_asof(ma200, last_date(price))
    if ma is None:
        return read(v, "info", f"S&P 500 at {_fmt(v, 0)}.")
    dist = (v / ma - 1) * 100
    if dist > 0:
        sig = "good"
        verdict = "in an uptrend — trend-followers stay invested above this line"
        if dist > 12:
            verdict = "well above trend — momentum is strong but stretched; pullbacks from here are normal"
    else:
        sig = "caution"
        verdict = "below its 200-day average — historically where the worst drawdowns happen"
    return read(v, sig, f"S&P 500 is {_fmt(abs(dist), 1)}% {'above' if dist > 0 else 'below'} its 200-day average: {verdict}.")


def read_vix(s):
    v = last(s)
    if v < 14:
        sig, verdict = "neutral", "very calm — cheap to hedge, but complacency builds when this persists"
    elif v < 20:
        sig, verdict = "good", "normal — markets are functioning without stress"
    elif v < 28:
        sig, verdict = "caution", "elevated fear — expect bigger daily swings"
    else:
        sig, verdict = "caution", "panic territory — historically these extremes happen near tradeable bottoms"
    return read(v, sig, f"VIX is at {_fmt(v, 1)}: {verdict}.")


def read_gold(s):
    v = last(s)
    ch = pct_change_over(s, 365)
    if ch is None:
        return read(v, "info", f"Gold is at ${_fmt(v, 0)}.")
    if ch > 15:
        verdict = "in a strong uptrend — markets are paying up for debasement/geopolitical insurance"
        sig = "info"
    elif ch < -10:
        verdict = "falling — confidence in real yields and the dollar is crowding out the safe-haven bid"
        sig = "info"
    else:
        verdict = "moving with real rates and the dollar, as usual"
        sig = "info"
    return read(v, sig, f"Gold is ${_fmt(v, 0)}/oz ({'+' if ch >= 0 else ''}{_fmt(ch, 1)}% in 1 year): {verdict}.")


def read_oil(s):
    v = last(s)
    ch = pct_change_over(s, 365)
    if ch is None:
        return read(v, "info", f"WTI crude is ${_fmt(v)}.")
    if ch > 25:
        sig, verdict = "caution", "an oil spike — acts like a tax on consumers and pushes inflation back up"
    elif ch < -20:
        sig, verdict = "good", "much cheaper oil — disinflationary, and a boost to real incomes"
    else:
        sig, verdict = "neutral", "oil is not a macro problem right now"
    return read(v, sig, f"WTI crude is ${_fmt(v, 0)} ({'+' if ch >= 0 else ''}{_fmt(ch, 0)}% in 1 year): {verdict}.")


# ----------------------------------------------------------- crypto reads ---

def read_btc(price, ma200d, ma200w):
    v = last(price)
    d200 = value_asof(ma200d, last_date(price))
    w200 = value_asof(ma200w, last_date(price))
    parts = []
    sig = "neutral"
    if d200:
        above = v > d200
        parts.append(f"{'above' if above else 'below'} the 200-day (${_fmt(d200, 0)})")
        sig = "good" if above else "caution"
    if w200:
        parts.append(f"{'above' if v > w200 else 'below'} the 200-week (${_fmt(w200, 0)})")
        if v < w200:
            sig = "caution"
    tail = ("bull-market structure intact" if sig == "good"
            else "trend is broken — bear-market rules apply" if sig == "caution"
            else "trend unclear")
    return read(v, sig, f"BTC ${_fmt(v, 0)} is {' and '.join(parts)}: {tail}.")


def read_mvrv(s):
    v = last(s)
    pct = percentile_rank(s["values"], v)
    since_yr = s["dates"][0][:4]
    if v < 1.0:
        sig, verdict = "good", "the market trades below its aggregate cost basis — historically the deep-value zone where cycle bottoms form"
    elif v < 1.6:
        sig, verdict = "good", "holders are modestly in profit — historically an accumulation zone"
    elif v < 2.5:
        sig, verdict = "neutral", "mid-cycle territory — profitable, but not extreme"
    elif v < 3.2:
        sig, verdict = "caution", "holders sit on large unrealized gains — the temptation to sell grows"
    else:
        sig, verdict = "caution", "historically the euphoria zone where cycle tops have formed (2013, 2017, 2021 all peaked above ~3.5)"
    return read(v, sig, f"MVRV is {_fmt(v)} ({pct:.0f}th percentile since {since_yr}): {verdict}.")


def read_mayer(s):
    v = last(s)
    if v < 0.8:
        sig, verdict = "good", "deeply below trend — historically among the best accumulation zones"
    elif v < 1.0:
        sig, verdict = "good", "below its 200-day trend — historically favorable for patient buyers"
    elif v < 1.8:
        sig, verdict = "neutral", "above trend but within normal bull-market range"
    elif v < 2.4:
        sig, verdict = "caution", "stretched well above trend — overheating"
    else:
        sig, verdict = "caution", "extreme stretch — past readings here marked blow-off tops"
    return read(v, sig, f"Mayer Multiple is {_fmt(v)} (price ÷ 200-day average): {verdict}.")


def read_rainbow(price_s, fit):
    v = last(price_s)
    k = band_position(v, last_date(price_s), fit)
    zones = [(-1.25, "good", "in the lower bands — historically where accumulating has paid off best"),
             (-0.5, "good", "below the long-term trend line — cheap relative to Bitcoin's own history"),
             (0.25, "neutral", "near fair value on the long-term growth path"),
             (1.0, "neutral", "above trend — bull market, but no longer cheap"),
             (1.75, "caution", "in the upper bands — historically frothy"),
             (99.0, "caution", "in the top band — past visits here were bubble peaks")]
    for limit, sig, verdict in zones:
        if k < limit:
            return read(v, sig, f"BTC sits {_fmt(k, 1)}σ from its long-term log growth path: {verdict}.", {"k": round(k, 2)})
    return read(v, "info", "", {"k": round(k, 2)})


def read_realized(price_s, realized_s):
    v = last(price_s)
    r = value_asof(realized_s, last_date(price_s))
    if not r:
        return read(v, "info", "")
    prem = (v / r - 1) * 100
    if prem < 0:
        sig, verdict = "good", "price is below the network's aggregate cost basis — historically capitulation, and where bottoms formed"
    elif prem < 60:
        sig, verdict = "neutral", "the average coin is in profit, but not euphorically so"
    else:
        sig, verdict = "caution", "the average coin holds large paper gains — fuel for profit-taking"
    return read(v, sig, f"BTC trades {_fmt(prem, 0)}% above the realized price (${_fmt(r, 0)}): {verdict}.")


def read_fng(s):
    v = last(s)
    if v <= 25:
        sig, verdict = "good", "extreme fear — contrarians note that crowds are usually fearful near bottoms, not tops"
    elif v <= 45:
        sig, verdict = "neutral", "fearful — sentiment is a mild contrarian positive"
    elif v <= 55:
        sig, verdict = "neutral", "balanced sentiment — no edge either way"
    elif v <= 75:
        sig, verdict = "neutral", "greedy — fine in an uptrend, but chasing gets expensive"
    else:
        sig, verdict = "caution", "extreme greed — historically when the crowd is all-in, upside is borrowed from the future"
    return read(v, sig, f"Crypto Fear & Greed is {v:.0f}/100: {verdict}.")


def read_stables(s):
    v = last(s)
    ch = pct_change_over(s, 91)
    if ch is None:
        return read(v, "info", f"Stablecoin supply is ${_fmt(v, 0)}B.")
    if ch > 3:
        sig, verdict = "good", "growing — new dollars are parking inside crypto, ready to buy (fresh dry powder)"
    elif ch < -2:
        sig, verdict = "caution", "shrinking — capital is leaving the crypto ecosystem entirely"
    else:
        sig, verdict = "neutral", "flat — no fresh inflows, rallies must be funded by rotation"
    return read(v, sig, f"Stablecoin supply is ${_fmt(v, 0)}B ({'+' if ch >= 0 else ''}{_fmt(ch, 1)}% in 3 months): {verdict}.")


def read_hashrate(s):
    v = last(s)
    peak = max(s["values"])
    frac = v / peak * 100
    if frac > 92:
        sig, verdict = "good", "at/near all-time highs — miners keep investing, maximum network security"
    elif frac > 80:
        sig, verdict = "neutral", "off its highs — some miner stress, worth watching"
    else:
        sig, verdict = "caution", "well below peak — miner capitulation, historically near cycle bottoms"
    return read(v, sig, f"Hashrate is at {_fmt(frac, 0)}% of its all-time high: {verdict}.")


def read_funding(s, coin="BTC"):
    v = last(s)                      # daily-average 8h rate in %
    ann = v * 3 * 365                # approx annualized
    if v > 0.05:
        sig, verdict = "caution", "longs pay heavily to stay levered — crowded positioning, vulnerable to long squeezes"
    elif v > 0.005:
        sig, verdict = "neutral", "mildly positive — normal bull-market lean, nothing extreme"
    elif v >= -0.005:
        sig, verdict = "neutral", "near zero — leverage is balanced"
    else:
        sig, verdict = "good", "negative — shorts pay longs; historically a setup for short squeezes"
    return read(v, sig, f"{coin} funding averages {v:+.3f}% per 8h (~{ann:+.0f}% annualized): {verdict}.")


def read_oi(s, price: float, coin="BTC"):
    v = last(s)
    usd = v * price / 1e9
    ch = pct_change_over(s, 30)
    if ch is None:
        return read(usd, "info", f"{coin} open interest ≈ ${_fmt(usd, 1)}B.")
    if ch > 20:
        sig, verdict = "caution", "leverage is building fast — moves get amplified in both directions, liquidation-cascade risk rises"
    elif ch < -20:
        sig, verdict = "neutral", "a big deleveraging just happened — positioning is cleaner now"
    else:
        sig, verdict = "neutral", "leverage is stable"
    return read(usd, sig, f"{coin} open interest ≈ ${_fmt(usd, 1)}B ({'+' if ch >= 0 else ''}{_fmt(ch, 0)}% in 30 days): {verdict}.")


def read_long_short(s):
    v = last(s)
    if v > 1.5:
        sig, verdict = "caution", "retail accounts lean heavily long — crowded trades unwind painfully"
    elif v < 0.8:
        sig, verdict = "good", "the crowd leans short — squeezes upward become easier"
    else:
        sig, verdict = "neutral", "positioning is balanced"
    return read(v, sig, f"{_fmt(v)} long accounts per short account on OKX: {verdict}.")


def read_ethbtc(s):
    v = last(s)
    ch = pct_change_over(s, 91)
    if ch is None:
        return read(v, "info", f"ETH/BTC is {_fmt(v, 4)}.")
    if ch > 8:
        verdict = "ETH is outperforming — risk appetite is broadening beyond Bitcoin (typical mid/late bull phase)"
    elif ch < -8:
        verdict = "BTC is outperforming — capital is huddling in the safest crypto asset (defensive or early-cycle behavior)"
    else:
        verdict = "no decisive rotation between the two majors"
    return read(v, "info", f"ETH/BTC is {_fmt(v, 4)} ({'+' if ch >= 0 else ''}{_fmt(ch, 1)}% in 3 months): {verdict}.")
