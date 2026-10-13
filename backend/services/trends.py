"""Trend statistics. Implemented with numpy only so every step is easy to explain in an interview."""
import math

import numpy as np
import pandas as pd


def mann_kendall(y) -> dict:
    """Mann-Kendall trend test (tie-corrected) with Sen's slope. Non-parametric, so it copes with the
    zero-heavy, skewed counts that heatwave data produces."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 4:  # too few points for any test
        return {"s": 0, "z": 0.0, "p_value": 1.0, "tau": 0.0, "sens_slope": 0.0, "trend": "no clear trend", "significant": False}
    s = sum(np.sign(y[i + 1 :] - y[i]).sum() for i in range(n - 1))
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in counts)) / 18
    if var <= 0:
        z = 0.0
    else:
        z = (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var) if s < 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))  # two-sided
    slopes = [(y[j] - y[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)]
    direction = "no clear trend" if p >= 0.05 else ("increasing" if z > 0 else "decreasing")
    return {
        "s": int(s),
        "z": round(z, 3),
        "p_value": round(p, 4),
        "tau": round(float(s) / (n * (n - 1) / 2), 3),
        "sens_slope": round(float(np.median(slopes)), 4),
        "trend": direction,
        "significant": bool(p < 0.05),
    }


def linear_fit(x, y) -> dict:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < 2:
        return {"slope": 0.0, "intercept": 0.0, "r2": 0.0}
    slope, intercept = np.polyfit(x, y, 1)
    ss_res = float(((y - (slope * x + intercept)) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "slope": round(float(slope), 4),
        "intercept": round(float(intercept), 3),
        "r2": round(1 - ss_res / ss_tot, 3) if ss_tot else 0.0,
    }


def rolling_mean(y, window: int = 5):
    return pd.Series(y, dtype=float).rolling(window, center=True, min_periods=3).mean().round(2).tolist()


def build_insight(rows, mk, metric, noun, unit, caveats) -> dict:
    """Turn the numbers into an honest plain-language summary. `noun` is e.g. "Heatwave days", `unit` e.g. "days"."""
    caveats = list(caveats)
    usable = [r for r in rows if not r["low_coverage"]]
    if len(usable) < 10:
        return {
            "headline": "Not enough complete years to say anything reliable about the trend.",
            "detail": "At least 10 years with enough valid data are needed.",
            "direction": "unknown",
            "significant": False,
            "caveats": caveats,
        }

    k = min(10, len(usable) // 2)
    first, last = usable[:k], usable[-k:]
    f = float(np.mean([r[metric] for r in first]))
    l = float(np.mean([r[metric] for r in last]))
    p_first = f"{first[0]['year']}-{first[-1]['year']}"
    p_last = f"{last[0]['year']}-{last[-1]['year']}"
    pct = None if f == 0 else (l - f) / f * 100
    direction = "increased" if l > f else "decreased" if l < f else "stayed flat"

    if f == 0 and l == 0:
        headline = f"No {noun.lower()} were detected in either {p_first} or {p_last}."
    elif f == 0:
        headline = f"{noun} rose from none a year in {p_first} to {l:.1f} a year in {p_last}."
    elif mk["significant"]:
        headline = f"{noun} have {direction} by {abs(pct):.0f}% between {p_first} and {p_last}."
    else:
        headline = (
            f"{noun} {direction} by {abs(pct):.0f}% between {p_first} and {p_last}, "
            "but the trend is not statistically significant."
        )

    detail = (
        f"Average of {f:.1f} {noun.lower()} a year in {p_first} against {l:.1f} in {p_last}. "
        f"Sen's slope is {mk['sens_slope']:+.2f} {unit} per year (Mann-Kendall p = {mk['p_value']:.3f})."
    )
    if f and f < 3:
        caveats.append(f"The early average is only {f:.1f} {unit} a year, so the percentage change looks larger than it is in absolute terms.")
    excluded = len(rows) - len(usable)
    if excluded:
        caveats.append(f"{excluded} year(s) with too little valid data were left out of the trend.")
    return {
        "headline": headline,
        "detail": detail,
        "direction": direction,
        "significant": mk["significant"],
        "first_period": p_first,
        "last_period": p_last,
        "first_mean": round(f, 1),
        "last_mean": round(l, 1),
        "pct_change": None if pct is None else round(pct, 1),
        "caveats": caveats,
    }


def summarise(rows, metric, noun, unit, caveats):
    """Shared by every hazard: trend tests on the yearly metric, rolling mean and fit lines added to rows."""
    usable = [r for r in rows if not r["low_coverage"]]
    years, values = [r["year"] for r in usable], [r[metric] for r in usable]
    mk, fit = mann_kendall(values), linear_fit(years, values)
    for r, rm in zip(rows, rolling_mean([r[metric] for r in rows])):
        r["rolling_5y"] = None if pd.isna(rm) else rm
        r["trend_line"] = round(max(0.0, fit["slope"] * r["year"] + fit["intercept"]), 2)
    trend = {"metric": metric, "mann_kendall": mk, "linear": fit}
    return trend, build_insight(rows, mk, metric, noun, unit, caveats)


def quality_report(window: pd.Series, rows, cleaning) -> dict:
    return {
        "days_in_window": int(len(window)),
        "missing_days": int(window.isna().sum()),
        "coverage_pct": round(100 * float(window.notna().mean()), 1),
        "low_coverage_years": [r["year"] for r in rows if r["low_coverage"]],
        **cleaning,
    }
