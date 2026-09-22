"""Series math on parallel (dates, values) lists — stdlib only.

A "series" throughout this project is a dict: {"dates": [ISO strings], "values": [floats]}
with dates ascending and no None values (fetchers drop blanks).
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date, timedelta


def series(dates: list[str], values: list[float]) -> dict:
    assert len(dates) == len(values)
    return {"dates": list(dates), "values": [round_sig(v) for v in values]}


def round_sig(v: float, digits: int = 6) -> float:
    """Round to significant digits so JSON stays small without losing shape."""
    if v == 0 or not math.isfinite(v):
        return 0.0
    return float(f"{v:.{digits}g}")


def last(s: dict) -> float:
    return s["values"][-1]


def last_date(s: dict) -> str:
    return s["dates"][-1]


def tail(s: dict, n: int) -> dict:
    return {"dates": s["dates"][-n:], "values": s["values"][-n:]}


def since(s: dict, start_iso: str) -> dict:
    i = bisect_right(s["dates"], start_iso)
    # include the point at start if exact match
    if i > 0 and s["dates"][i - 1] == start_iso:
        i -= 1
    return {"dates": s["dates"][i:], "values": s["values"][i:]}


def sma(s: dict, window: int) -> dict:
    """Simple moving average; emitted only where a full window exists."""
    dates, values = s["dates"], s["values"]
    out_d, out_v = [], []
    acc = 0.0
    for i, v in enumerate(values):
        acc += v
        if i >= window:
            acc -= values[i - window]
        if i >= window - 1:
            out_d.append(dates[i])
            out_v.append(acc / window)
    return series(out_d, out_v)


def yoy(s: dict, months: int = 12) -> dict:
    """Year-over-year % change for a monthly series (matches by index offset)."""
    d, v = s["dates"], s["values"]
    out_d, out_v = [], []
    for i in range(months, len(v)):
        if v[i - months]:
            out_d.append(d[i])
            out_v.append((v[i] / v[i - months] - 1.0) * 100.0)
    return series(out_d, out_v)


def change_over(s: dict, days: int) -> float | None:
    """Absolute change between the last value and the value ~`days` earlier."""
    if not s["values"]:
        return None
    target = (date.fromisoformat(s["dates"][-1]) - timedelta(days=days)).isoformat()
    i = bisect_right(s["dates"], target) - 1
    if i < 0:
        return None
    return s["values"][-1] - s["values"][i]


def pct_change_over(s: dict, days: int) -> float | None:
    if not s["values"]:
        return None
    target = (date.fromisoformat(s["dates"][-1]) - timedelta(days=days)).isoformat()
    i = bisect_right(s["dates"], target) - 1
    if i < 0 or s["values"][i] == 0:
        return None
    return (s["values"][-1] / s["values"][i] - 1.0) * 100.0


def value_asof(s: dict, iso: str) -> float | None:
    """Latest value at or before `iso` (forward-fill lookup)."""
    i = bisect_right(s["dates"], iso) - 1
    return s["values"][i] if i >= 0 else None


def combine_asof(base_dates: list[str], parts: list[dict],
                 weights: list[float] | None = None) -> dict:
    """Sum several series (forward-filled) onto `base_dates`.

    A date is emitted only once every part has at least one observation at or
    before it, so the combined series never mixes a partial sum.
    """
    weights = weights or [1.0] * len(parts)
    out_d, out_v = [], []
    for dt in base_dates:
        vals = [value_asof(p, dt) for p in parts]
        if any(v is None for v in vals):
            continue
        out_d.append(dt)
        out_v.append(sum(v * w for v, w in zip(vals, weights)))
    return series(out_d, out_v)


def ratio_asof(a: dict, b: dict) -> dict:
    """a / b forward-filling b onto a's dates."""
    out_d, out_v = [], []
    for dt, av in zip(a["dates"], a["values"]):
        bv = value_asof(b, dt)
        if bv:
            out_d.append(dt)
            out_v.append(av / bv)
    return series(out_d, out_v)


def percentile_rank(window_values: list[float], x: float) -> float:
    """0–100 rank of x within window_values."""
    if not window_values:
        return 50.0
    below = sum(1 for v in window_values if v < x)
    equal = sum(1 for v in window_values if v == x)
    return 100.0 * (below + 0.5 * equal) / len(window_values)


def trailing_window(s: dict, years: float) -> list[float]:
    if not s["dates"]:
        return []
    cutoff = (date.fromisoformat(s["dates"][-1]) - timedelta(days=int(years * 365.25))).isoformat()
    i = bisect_right(s["dates"], cutoff)
    return s["values"][i:]


def merge_series(*parts: dict) -> dict:
    """Union several series by date; later parts override earlier ones."""
    m: dict[str, float] = {}
    for p in parts:
        for dt, v in zip(p["dates"], p["values"]):
            m[dt] = v
    dates = sorted(m)
    return series(dates, [m[d] for d in dates])


def to_daily(s: dict) -> dict:
    """Forward-fill onto a full daily calendar (needed before index-based SMAs
    when the source is sampled at mixed frequencies)."""
    from datetime import date, timedelta
    if not s["dates"]:
        return {"dates": [], "values": []}
    out_d, out_v = [], []
    cur = date.fromisoformat(s["dates"][0])
    end = date.fromisoformat(s["dates"][-1])
    i = 0
    lastv = s["values"][0]
    while cur <= end:
        iso = cur.isoformat()
        while i < len(s["dates"]) and s["dates"][i] <= iso:
            lastv = s["values"][i]
            i += 1
        out_d.append(iso)
        out_v.append(lastv)
        cur += timedelta(days=1)
    return series(out_d, out_v)


def downsample_weekly(s: dict, before_iso: str) -> dict:
    """Keep ~weekly points before a cutoff date, daily after (shrinks JSON)."""
    out_d, out_v = [], []
    last_kept: date | None = None
    for dt, v in zip(s["dates"], s["values"]):
        d = date.fromisoformat(dt)
        if dt >= before_iso or last_kept is None or (d - last_kept).days >= 7:
            out_d.append(dt)
            out_v.append(v)
            last_kept = d
    return series(out_d, out_v)


def log_regression_bands(s: dict, genesis: str = "2009-01-03",
                         ks: tuple = (-2.0, -1.25, -0.5, 0.25, 1.0, 1.75, 2.5),
                         extend_days: int = 365, sample_days: int = 7) -> dict:
    """Fit log10(price) = a + b*log10(days since genesis); return band lines.

    Returns {"dates": [...], "bands": [[...] per k], "a": a, "b": b, "sigma": s}.
    Bands are the fitted line offset by k * sigma (residual std) in log space.
    """
    g = date.fromisoformat(genesis)
    xs, ys = [], []
    for dt, v in zip(s["dates"], s["values"]):
        if v and v > 0:
            days = (date.fromisoformat(dt) - g).days
            if days > 0:
                xs.append(math.log10(days))
                ys.append(math.log10(v))
    n = len(xs)
    if n < 100:
        raise ValueError("not enough history for regression")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sigma = math.sqrt(sum(r * r for r in resid) / (n - 2))

    start = date.fromisoformat(s["dates"][0])
    end = date.fromisoformat(s["dates"][-1]) + timedelta(days=extend_days)
    out_dates, band_rows = [], [[] for _ in ks]
    d = start
    while d <= end:
        days = (d - g).days
        if days > 0:
            lx = math.log10(days)
            out_dates.append(d.isoformat())
            for i, k in enumerate(ks):
                band_rows[i].append(round_sig(10 ** (a + b * lx + k * sigma), 5))
        d += timedelta(days=sample_days)
    return {"dates": out_dates, "bands": band_rows, "ks": list(ks),
            "a": round_sig(a), "b": round_sig(b), "sigma": round_sig(sigma)}


def band_position(price: float, dt: str, fit: dict, genesis: str = "2009-01-03") -> float:
    """Where today's price sits in band units (k of sigma) — for interpretation."""
    days = (date.fromisoformat(dt) - date.fromisoformat(genesis)).days
    expected = fit["a"] + fit["b"] * math.log10(days)
    return (math.log10(price) - expected) / fit["sigma"]
