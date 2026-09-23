"""The Bull-Market Playbook: a live confirmation checklist and cycle-phase
tracker following the framework The DeFi Report (Michael Nadeau & Ryan Sean
Adams) uses on their weekly show — four phases: Early Bull, Wealth Creation,
Wealth Distribution, Wealth Destruction.

Attribution: the *framework and indicator selection* follow TDR's public
podcast discussion (TDR podcast, Sep 2026 episodes). All thresholds,
computations and text here are Waypoint's own, computed from free public data.
This is educational context, not investment advice.

Every check returns:
  {id, label, state, value, note, anchor}
  state: "pass" (supports the bull case) | "warn" (mixed) | "fail" | "na"
"""
from __future__ import annotations

from datetime import date, timedelta

from transform import last, last_date, pct_change_over, sma, value_asof


def _check(cid: str, label: str, state: str, value: str, note: str,
           anchor: str = "") -> dict:
    return {"id": cid, "label": label, "state": state, "value": value,
            "note": note, "anchor": anchor}


def _weekly_closes_above(price: dict, ma: dict, weeks: int = 6) -> int:
    """Consecutive weekly (Sunday UTC) closes above the reference line."""
    closes = []
    for i in range(len(price["dates"]) - 1, -1, -1):
        d = date.fromisoformat(price["dates"][i])
        if d.weekday() == 6:  # Sunday
            m = value_asof(ma, price["dates"][i])
            if m is None:
                break
            closes.append(price["values"][i] > m)
            if len(closes) >= weeks:
                break
    streak = 0
    for above in closes:
        if above:
            streak += 1
        else:
            break
    return streak


def _cross_state(fast: dict, slow: dict):
    """Is fast MA above slow MA, and how many days since the last cross?"""
    n = min(len(fast["values"]), len(slow["values"]))
    if n < 2:
        return None, None
    f, s = fast["values"][-n:], slow["values"][-n:]
    dates = fast["dates"][-n:]
    above = f[-1] > s[-1]
    days = None
    for i in range(n - 1, 0, -1):
        if (f[i] > s[i]) != (f[i - 1] > s[i - 1]):
            days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[i])).days
            break
    return above, days


def build_checks(cs: dict, derivs: dict, spot: dict) -> list[dict]:
    """cs = crypto.json's series dict (needs btc_price at daily resolution)."""
    checks = []
    price = cs["btc_price"]
    px = last(price)

    ma50 = sma(price, 50)
    ma200 = cs.get("btc_200dma") or sma(price, 200)
    ma350 = sma(price, 350)  # ~50-week line

    # 1. Golden cross ------------------------------------------------------
    above, days = _cross_state(ma50, ma200)
    if above is None:
        checks.append(_check("golden_cross", "Golden cross (50d > 200d)", "na", "–", ""))
    else:
        val = f"50d {'above' if above else 'below'} 200d" + (f" for {days}d" if days else "")
        note = ("The medium-term trend has turned up through the long-term trend — "
                "the classic trend-change confirmation TDR waits for."
                if above else
                "No golden cross yet — the trend change is unconfirmed.")
        checks.append(_check("golden_cross", "Golden cross (50d > 200d)",
                             "pass" if above else "fail", val, note, "card-btc"))

    # 2. Reclaim of the 50-week line --------------------------------------
    m350 = value_asof(ma350, last_date(price))
    if m350:
        above_50w = px > m350
        streak = _weekly_closes_above(price, ma350)
        val = (f"${px:,.0f} vs ${m350:,.0f} · {streak} weekly close{'s' if streak != 1 else ''} above"
               if above_50w else f"${px:,.0f} below ${m350:,.0f}")
        if above_50w and streak >= 3:
            st, note = "pass", "Price has held above the 50-week line for several weekly closes — TDR's bar for a confirmed regime change."
        elif above_50w:
            st, note = "warn", "Price is above the 50-week line but TDR wants a few weekly closes above it before calling it confirmed — a retest of this line is normal."
        else:
            st, note = "fail", "Below the 50-week moving average — bear-market structure until reclaimed."
        checks.append(_check("ma_50w", "Reclaim the 50-week average", st, val, note, "card-btc"))

    # 3. Holding the 200-day ----------------------------------------------
    m200 = value_asof(ma200, last_date(price))
    if m200:
        st = "pass" if px > m200 else "fail"
        checks.append(_check("ma_200d", "Hold the 200-day as support",
                             st, f"${px:,.0f} vs ${m200:,.0f}",
                             "The line the early bull must defend — losing it voids the setup." if st == "pass"
                             else "Below the 200-day — the early-bull thesis is on hold.",
                             "card-btc"))

    # 4. New money in profit (price vs STH cost basis) ---------------------
    sth = cs.get("btc_sth_realized")
    if sth and sth.get("values"):
        sv = last(sth)
        st = "pass" if px > sv else "fail"
        checks.append(_check("sth_basis", "New money in profit (price > STH cost basis)",
                             st, f"${px:,.0f} vs ${sv:,.0f}",
                             "Recent buyers are in profit, so dips find buyers — the market-structure foundation TDR's cohort work tracks." if st == "pass"
                             else "Recent buyers are underwater — rallies get sold by trapped holders until this flips.",
                             "card-costbasis"))

    # 5. Dominance rising off the low --------------------------------------
    dom = cs.get("btc_dominance_proxy")
    if dom and len(dom["values"]) > 130:
        cur = last(dom)
        low120 = min(dom["values"][-120:])
        chg30 = (pct_change_over(dom, 30) or 0)
        off_low = cur - low120
        if off_low > 1.0 and chg30 > 0:
            st, note = "pass", "BTC dominance has turned up off its cycle low — the pattern TDR associates with the start of an early bull (BTC leads first)."
        elif off_low > 0.3:
            st, note = "warn", "Dominance is stabilizing near its low — watch for a clear upturn."
        else:
            st, note = "fail", "Dominance is still falling — no early-bull rotation into BTC yet."
        checks.append(_check("dominance", "BTC dominance turning up",
                             st, f"{cur:.1f}% (+{off_low:.1f}pp off 120d low)", note,
                             "card-dominance"))

    # 6. Stablecoin supply rebuilding --------------------------------------
    stables = cs.get("stablecoin_mcap")
    if stables and stables.get("values"):
        chg90 = pct_change_over(stables, 90)
        if chg90 is not None:
            st = "pass" if chg90 > 2 else ("warn" if chg90 > -1 else "fail")
            checks.append(_check("stables", "Stablecoin supply rebuilding",
                                 st, f"${last(stables):,.0f}B ({chg90:+.1f}% / 90d)",
                                 "Fresh dollars are entering crypto — TDR treats this as the market's own money supply expanding." if st == "pass"
                                 else "No new dollars yet — the wealth-creation fuel tank isn't filling.",
                                 "card-stables"))

    # 7. Leverage rebuilding (but not frothy) -------------------------------
    oi = (derivs.get("open_interest") or {}).get("btc")
    fu = (derivs.get("funding") or {}).get("btc")
    if oi and oi.get("values"):
        chg60 = pct_change_over(oi, 60)
        f_last = last(fu) if fu and fu.get("values") else None
        if chg60 is not None:
            frothy = f_last is not None and f_last > 0.05
            if frothy:
                st, note = "warn", "Leverage is rebuilding fast and funding is hot — supportive but crowded."
            elif chg60 > 10:
                st, note = "pass", "Credit and leverage are coming back after the reset — early wealth-creation behavior."
            elif chg60 > -10:
                st, note = "warn", "Leverage is flat — conviction hasn't returned yet."
            else:
                st, note = "fail", "Leverage is still being flushed out."
            checks.append(_check("leverage", "Leverage rebuilding after the reset",
                                 st, f"OI {chg60:+.0f}% / 60d" +
                                 (f" · funding {f_last:+.3f}%/8h" if f_last is not None else ""),
                                 note, "card-open_interest"))

    # 8. On-chain activity inflecting ---------------------------------------
    dex = cs.get("dex_volume")
    if dex and len(dex["values"]) > 200:
        recent = sum(dex["values"][-30:]) / 30
        base = sum(dex["values"][-210:-30]) / 180
        chg = (recent / base - 1) * 100 if base else 0
        st = "pass" if chg > 15 else ("warn" if chg > -10 else "fail")
        checks.append(_check("onchain", "On-chain activity inflecting",
                             st, f"DEX vol ${recent:.1f}B/day ({chg:+.0f}% vs 6m base)",
                             "Real usage is picking up with price — the reflexive loop TDR wants to see behind a rally." if st == "pass"
                             else "Activity isn't confirming the move yet — rallies without usage are lower quality.",
                             "card-dex"))

    # 9. Institutional bid (spot ETF flows) ---------------------------------
    etf = cs.get("etf_flows")
    if etf and etf.get("values"):
        last7 = sum(etf["values"][-7:])
        last30 = sum(etf["values"][-30:])
        st = "pass" if last7 > 0 and last30 > 0 else ("warn" if last30 > 0 else "fail")
        checks.append(_check("etf", "Institutional bid (spot ETF flows)",
                             st, f"7d {last7:+,.0f}M · 30d {last30:+,.0f}M",
                             "The ETF pipe is net-buying — the structural demand this cycle has that earlier ones didn't." if st == "pass"
                             else "ETF money is leaving — the marginal institutional buyer is absent.",
                             "card-etf"))

    return checks


PHASES = [
    ("early_bull", "Early Bull"),
    ("wealth_creation", "Wealth Creation"),
    ("wealth_distribution", "Wealth Distribution"),
    ("wealth_destruction", "Wealth Destruction"),
]

PHASE_GUIDE = {
    "early_bull": {
        "signature": "Trend reclaimed (golden cross, 50-week), BTC leads and dominance rises, recent buyers back in profit, first pockets of speculation return while the crowd is still skeptical.",
        "playbook": "Historically the phase where patient positioning in majors and high-conviction themes paid best — accumulation into strength, wide stops, no chasing. TDR's framing: build positions before the crowd believes it.",
        "exit_tell": "Graduates into Wealth Creation when stablecoins, credit and on-chain activity expand together and price approaches old highs.",
    },
    "wealth_creation": {
        "signature": "Stablecoin supply, DeFi credit and leverage all expanding — crypto's own money multiplier turning. New highs print, activity goes reflexive, rotation broadens beyond BTC.",
        "playbook": "Ride winners but begin disciplined trimming into strength; watch for sector charts peaking early — the hot money rotates before the index tops.",
        "exit_tell": "Late signs: funding persistently hot, extreme greed sustained, peak-speculation moments (mania launches), dominance rolling over hard.",
    },
    "wealth_distribution": {
        "signature": "Price still elevated but coins transfer from smart money to late buyers at high cost bases; speculative pockets have already peaked; breadth narrows while headlines peak.",
        "playbook": "The phase for selling into strength and cutting the long tail — TDR's own discipline last cycle was going risk-off months before the top, at peak speculation.",
        "exit_tell": "Rolls into Wealth Destruction when the 200-day fails and recent buyers go underwater en masse.",
    },
    "wealth_destruction": {
        "signature": "Trend broken, leverage flushed, late buyers capitulate over months — cost bases consolidate downward into strong hands.",
        "playbook": "Capital preservation, then patient accumulation near capitulation signals (deep-value bands, max fear). This is where the next cycle's foundation forms.",
        "exit_tell": "Ends when the market-structure reset completes and the Early Bull checklist starts passing again.",
    },
}


def infer_phase(checks: list[dict], crypto_cycle_score: int | None,
                price: dict, ath_frac: float) -> dict:
    """Simple, documented phase rules on top of the checklist."""
    by_id = {c["id"]: c for c in checks}
    passing = sum(1 for c in checks if c["state"] == "pass")
    total = sum(1 for c in checks if c["state"] != "na")

    trend_ok = by_id.get("ma_200d", {}).get("state") == "pass"
    sth_ok = by_id.get("sth_basis", {}).get("state") == "pass"
    hot = (crypto_cycle_score or 0) >= 80
    expanding = sum(1 for k in ("stables", "leverage", "onchain")
                    if by_id.get(k, {}).get("state") == "pass")

    if not trend_ok and not sth_ok:
        key = "wealth_destruction"
        why = "Price is below its long-term trend and recent buyers are underwater — the reset is still running."
    elif hot and ath_frac > 0.95:
        key = "wealth_distribution"
        why = "Cycle gauges are in the euphoria zone near all-time highs — historically when coins migrate to late buyers."
    elif trend_ok and ath_frac > 0.9 and expanding >= 2:
        key = "wealth_creation"
        why = "Trend is up, price is near highs, and crypto's internal money supply (stables, credit, activity) is expanding together."
    elif trend_ok:
        key = "early_bull"
        why = f"Trend reclaimed and {passing} of {total} early-bull checks are passing, while price is still {100 - ath_frac * 100:.0f}% below the prior high — the early phase profile."
    else:
        key = "wealth_destruction"
        why = "Mixed signals with a broken trend — treated as late reset until the checklist improves."

    return {"key": key, "name": dict(PHASES)[key], "why": why,
            "checks_passing": passing, "checks_total": total,
            "guide": PHASE_GUIDE[key],
            "phases": [{"key": k, "name": n} for k, n in PHASES]}
