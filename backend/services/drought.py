"""Meteorological drought using a non-parametric Standardised Precipitation Index (SPI-3).

Monthly rainfall is summed over a rolling 3 month window. Each value is ranked against the same calendar
month's windows in the 1991-2020 baseline, and that percentile is converted to a z-score with the standard
normal curve. A month at or below -1 is in drought (WMO "moderate or worse"), and a drought event is at
least 2 such months in a row. Ranking instead of fitting a gamma distribution keeps this dependency-free and
robust in places with many dry months."""
from statistics import NormalDist

import numpy as np
import pandas as pd

from services import trends
from services.rainfall import clean_precip

SCALE, THRESHOLD, MIN_MONTHS = 3, -1.0, 2
MIN_MONTH_COVERAGE, LOW_COVERAGE = 0.90, 0.75


def monthly_totals(s: pd.Series) -> pd.Series:
    grouped = s.resample("MS")
    total = grouped.sum(min_count=1)
    coverage = grouped.count() / grouped.size()
    total[coverage < MIN_MONTH_COVERAGE] = np.nan
    return total / coverage  # scale up months that were up to 10% incomplete


def spi_series(monthly: pd.Series, base_start: int, base_end: int) -> pd.Series:
    acc = monthly.rolling(SCALE, min_periods=SCALE).sum()  # NaN if any month in the window is missing
    out = pd.Series(np.nan, index=acc.index)
    norm = NormalDist()
    for month in range(1, 13):
        same = acc[acc.index.month == month]
        base = same[(same.index.year >= base_start) & (same.index.year <= base_end)].dropna().to_numpy()
        if base.size < 20 or np.mean(base == 0) > 0.5:  # too short, or a season that is nearly always dry
            continue
        for ts, x in same.dropna().items():
            p = ((base < x).sum() + 0.5 * (base == x).sum()) / base.size
            out.at[ts] = norm.inv_cdf(min(max(p, 1 / (base.size + 1)), base.size / (base.size + 1)))
    return out


def analyze(raw: pd.Series, cfg, start_year: int, end_year: int) -> dict:
    s, cleaning = clean_precip(raw)
    spi = spi_series(monthly_totals(s), cfg.BASELINE_START, cfg.BASELINE_END)
    if spi.notna().sum() == 0:
        raise ValueError("This place is too dry for a drought index: rainfall is zero in most baseline months.")

    vals = spi.to_numpy()
    dry = np.where(np.isnan(vals), False, vals <= THRESHOLD)
    edges = np.diff(np.concatenate([[0], dry.astype(int), [0]]))
    events = []
    for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        if b - a < MIN_MONTHS:
            continue
        events.append({
            "start": spi.index[a].date().isoformat(), "end": spi.index[b - 1].date().isoformat(),
            "year": int(spi.index[a].year), "duration": int(b - a),
            "min_spi": round(float(vals[a:b].min()), 2), "mean_spi": round(float(vals[a:b].mean()), 2),
        })
    in_event = np.zeros(len(spi), dtype=bool)
    for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        if b - a >= MIN_MONTHS:
            in_event[a:b] = True

    years = spi.index.year.to_numpy()
    rows = []
    for y in range(start_year, end_year + 1):
        m = years == y
        if not m.any():
            continue
        valid = int((~np.isnan(vals[m])).sum())
        ys = [e for e in events if e["year"] == y]
        months = int(in_event[m].sum())
        rows.append({
            "year": y,
            "events": len(ys),
            "drought_months": months,
            "max_duration": max((e["duration"] for e in ys), default=0),
            "mean_severity": round(float(np.mean(-vals[m & in_event])), 2) if months else None,
            "worst_spi": round(float(np.nanmin(vals[m])), 2) if valid else None,
            "coverage_pct": round(100 * valid / int(m.sum()), 1),
            "low_coverage": valid / int(m.sum()) < LOW_COVERAGE,
        })

    caveats = [
        "SPI uses rainfall only. It cannot see drought caused by heat and evaporation, so it can understate dryness in a warming climate.",
        "SPI-3 measures 3 month rainfall deficits. It is not a measure of river flow, soil moisture or groundwater.",
        "Each month is ranked against 1991-2020, so a window inside that period measures change within the baseline.",
    ]
    trend, insight = trends.summarise(rows, "drought_months", "Drought months", "months", caveats)

    window = spi[str(start_year) : str(end_year)]
    return {
        "hazard": "drought",
        "params": {
            "start_year": start_year, "end_year": end_year, "index": f"SPI-{SCALE}", "drought_below": THRESHOLD,
            "min_consecutive_months": MIN_MONTHS, "baseline": [cfg.BASELINE_START, cfg.BASELINE_END], "metric": "monthly precipitation sum, mm",
        },
        "quality": trends.quality_report(s[str(start_year) : str(end_year)], rows, cleaning),
        "yearly": rows,
        "events": [e for e in events if start_year <= e["year"] <= end_year][-300:],
        "trend": trend,
        "insight": insight,
        "display": {
            "id": "drought", "label": "Drought", "palette": "dry", "date_precision": "month",
            "primary": {"key": "drought_months", "label": "Drought months", "axis": "Months a year in drought", "noun": "months in drought"},
            "metrics": [
                {"key": "events", "label": "Drought events", "unit": "events a year"},
                {"key": "max_duration", "label": "Longest event", "unit": "months"},
                {"key": "mean_severity", "label": "Severity", "unit": "SPI points below zero"},
            ],
            "event_label": "droughts detected", "total_label": "months spent in drought", "duration_unit": "months",
            "definition": "SPI-3 at or below -1 for 2 or more months",
            "events_title": "Longest droughts", "event_sort": "duration", "event_sort_label": "duration",
            "event_columns": [
                {"key": "min_spi", "label": "Lowest SPI", "prefix": ""},
                {"key": "mean_spi", "label": "Average SPI", "prefix": ""},
            ],
            "method": (
                "Rainfall is added up over each rolling 3 month window and compared with the same calendar months in 1991 to 2020. "
                "That rank becomes the Standardised Precipitation Index: 0 is normal, below -1 is drought, below -2 is extreme. "
                "A drought event is two or more such months in a row, counted in the year it starts."
            ),
        },
        "context": {
            "type": "timeline_bars", "title": "Rainfall deficit index through time",
            "caption": "The 3 month SPI for every month. Bars at or below -1 count as drought.",
            "labels": [ts.strftime("%Y-%m") for ts in window.index],
            "values": [None if np.isnan(x) else round(float(x), 2) for x in window.to_numpy()],
            "threshold": THRESHOLD, "unit": "SPI",
        },
    }
