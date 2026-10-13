"""Heavy rainfall, following the ETCCDI convention (R95p): a heavy rainfall day is a *wet* day (at least 1 mm)
whose rainfall is above the 95th percentile of all wet days in the 1991-2020 baseline. Consecutive heavy days
are merged into one spell."""
import numpy as np
import pandas as pd

from services import trends

WET_MM, PERCENTILE, LOW_COVERAGE = 1.0, 95.0, 0.90
MAX_DAILY_MM = 1500.0  # above any recorded 24 h rainfall, so certainly a data error
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def clean_precip(raw: pd.Series):
    """Rain is not continuous like temperature, so missing days are never interpolated, only counted."""
    s = raw.astype("float64").copy()
    s = s[~s.index.duplicated()].sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
    invalid = ((s < 0) | (s > MAX_DAILY_MM)).fillna(False)
    s[invalid] = np.nan
    return s, {"outliers_removed": int(invalid.sum()), "short_gaps_filled": 0}


def analyze(raw: pd.Series, cfg, start_year: int, end_year: int) -> dict:
    s, cleaning = clean_precip(raw)
    base = s[(s.index.year >= cfg.BASELINE_START) & (s.index.year <= cfg.BASELINE_END)]
    wet = base[base >= WET_MM].dropna()
    if len(wet) < 150:
        raise ValueError("This place is too dry for a heavy rainfall analysis: the 1991-2020 baseline has too few wet days.")
    thr = float(np.percentile(wet, PERCENTILE))

    v = s.to_numpy()
    heavy = np.where(np.isnan(v), False, v > thr)
    edges = np.diff(np.concatenate([[0], heavy.astype(int), [0]]))
    events = []
    for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        events.append({
            "start": s.index[a].date().isoformat(), "end": s.index[b - 1].date().isoformat(),
            "year": int(s.index[a].year), "duration": int(b - a),
            "peak_mm": round(float(v[a:b].max()), 1), "total_mm": round(float(v[a:b].sum()), 1),
        })

    years = s.index.year.to_numpy()
    roll5 = s.rolling(5, min_periods=5).sum()
    rx5 = roll5.groupby(roll5.index.year).max()
    rows = []
    for y in range(start_year, end_year + 1):
        m = years == y
        total = int(m.sum())
        if total == 0:
            continue
        valid = int((~np.isnan(v[m])).sum())
        ys = [e for e in events if e["year"] == y]
        total_mm = float(np.nansum(v[m]))
        heavy_mm = float(np.nansum(v[m & heavy]))
        rows.append({
            "year": y,
            "events": len(ys),
            "heavy_rain_days": int(heavy[m].sum()),
            "max_duration": max((e["duration"] for e in ys), default=0),
            "rx1day": round(float(np.nanmax(v[m])), 1) if valid else None,
            "rx5day": round(float(rx5.get(y, np.nan)), 1) if valid and not np.isnan(rx5.get(y, np.nan)) else None,
            "heavy_share_pct": round(100 * heavy_mm / total_mm, 1) if total_mm > 0 else 0.0,
            "total_mm": round(total_mm),
            "coverage_pct": round(100 * valid / total, 1),
            "low_coverage": valid / total < LOW_COVERAGE,
        })

    caveats = [
        f"A heavy rainfall day here means more than {thr:.1f} mm in 24 hours, the 95th percentile of wet days in 1991-2020.",
        "Gridded reanalysis smooths out local cloudbursts, so the most extreme short downpours are understated compared with rain gauges.",
    ]
    trend, insight = trends.summarise(rows, "heavy_rain_days", "Heavy rainfall days", "days", caveats)

    in_range = [e for e in events if start_year <= e["year"] <= end_year]
    by_month = [0] * 12
    for e in in_range:
        by_month[int(e["start"][5:7]) - 1] += e["duration"]

    return {
        "hazard": "heavy_rain",
        "params": {
            "start_year": start_year, "end_year": end_year, "percentile": PERCENTILE, "wet_day_mm": WET_MM,
            "threshold_mm": round(thr, 1), "baseline": [cfg.BASELINE_START, cfg.BASELINE_END], "metric": "daily precipitation sum, mm",
        },
        "quality": trends.quality_report(s[str(start_year) : str(end_year)], rows, cleaning),
        "yearly": rows,
        "events": in_range[-300:],
        "trend": trend,
        "insight": insight,
        "display": {
            "id": "heavy_rain", "label": "Heavy rainfall", "palette": "rain", "date_precision": "day",
            "primary": {"key": "heavy_rain_days", "label": "Heavy rainfall days", "axis": "Heavy rainfall days a year", "noun": "heavy rainfall days"},
            "metrics": [
                {"key": "rx1day", "label": "Wettest day", "unit": "mm"},
                {"key": "rx5day", "label": "Wettest 5 days", "unit": "mm"},
                {"key": "heavy_share_pct", "label": "Rain from heavy days", "unit": "% of the year's rainfall"},
            ],
            "event_label": "heavy rainfall spells detected", "total_label": "heavy rainfall days", "duration_unit": "days",
            "definition": f"days above the 95th percentile of wet days ({thr:.1f} mm)",
            "events_title": "Heaviest rainfall spells", "event_sort": "total_mm", "event_sort_label": "total rainfall",
            "event_columns": [
                {"key": "peak_mm", "label": "Wettest day mm", "prefix": ""},
                {"key": "total_mm", "label": "Total mm", "prefix": ""},
            ],
            "method": (
                f"A wet day has at least 1 mm of rain. A heavy rainfall day is a wet day above the 95th percentile of wet days in 1991 to 2020, "
                f"which is {thr:.1f} mm at this location. Back-to-back heavy days are merged into one spell. Wettest day and wettest 5 days "
                "are the standard Rx1day and Rx5day indices. Missing days are never filled in, because rain does not change smoothly from day to day."
            ),
        },
        "context": {
            "type": "month_bars", "title": "When heavy rain falls",
            "caption": "Heavy rainfall days by month of the year, added up across the chosen range.",
            "labels": MONTHS, "values": by_month, "unit": "days",
        },
    }
