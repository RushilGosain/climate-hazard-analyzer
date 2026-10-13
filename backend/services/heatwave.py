"""Heatwave detection.

Definition used: a heatwave is a run of 3 or more consecutive days whose daily maximum
temperature exceeds the 95th percentile for that calendar day, where the percentile is
computed from a 1991-2020 baseline using a 15-day window centred on the day (this keeps
the threshold seasonal and removes the noise of a single-day percentile).
"""
import numpy as np
import pandas as pd

from services import trends

PHYSICAL_MIN_C, PHYSICAL_MAX_C = -60.0, 60.0
SPIKE_C = 25.0       # |value - 7 day rolling median| above this is treated as a sensor/model glitch
MAX_FILL_GAP = 2     # only gaps of up to 2 days are interpolated
LOW_COVERAGE = 0.90  # years with less valid data than this are flagged and kept out of the trend


def leap_doy(index: pd.DatetimeIndex) -> np.ndarray:
    """Day-of-year computed on a leap-year calendar so 1 Mar is always day 61 (29 Feb gets its own slot)."""
    frame = pd.DataFrame({"year": 2000, "month": index.month, "day": index.day})
    return pd.to_datetime(frame).dt.dayofyear.to_numpy()


def clean_series(raw: pd.Series):
    """Make a noisy daily series safe to analyse. Returns (series, report)."""
    s = raw.astype("float64").copy()
    s = s[~s.index.duplicated()].sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))  # expose missing days

    out_of_range = ((s < PHYSICAL_MIN_C) | (s > PHYSICAL_MAX_C)).fillna(False)
    s[out_of_range] = np.nan

    median = s.rolling(7, center=True, min_periods=3).median()
    spikes = ((s - median).abs() > SPIKE_C).fillna(False)
    s[spikes] = np.nan

    # Fill short gaps only. Long gaps stay missing: inventing data would bias the trend.
    isna = s.isna()
    run_id = isna.ne(isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("sum")
    fillable = isna & (run_len <= MAX_FILL_GAP)
    s[fillable] = s.interpolate(limit_area="inside")[fillable]

    report = {
        "outliers_removed": int(out_of_range.sum() + spikes.sum()),
        "short_gaps_filled": int((fillable & s.notna()).sum()),
    }
    return s, report


def daily_thresholds(s: pd.Series, base_start: int, base_end: int, pct: float = 95.0, window: int = 15) -> np.ndarray:
    """Percentile threshold for every calendar day. Returned array is indexed by leap-calendar day-of-year (1..366)."""
    base = s[(s.index.year >= base_start) & (s.index.year <= base_end)].dropna()
    if len(base) < 365 * 10:
        raise ValueError("Baseline period has too little valid data to compute percentiles.")
    base_doy, base_vals = leap_doy(base.index), base.to_numpy()
    half = window // 2
    thr = np.full(367, np.nan)
    for day in range(1, 367):
        diff = np.abs(base_doy - day)
        diff = np.minimum(diff, 366 - diff)  # wrap around the new year
        sample = base_vals[diff <= half]
        if sample.size >= 30:
            thr[day] = np.percentile(sample, pct)
    return thr


def detect_events(s: pd.Series, thr: np.ndarray, min_days: int = 3):
    """Find runs of >= min_days days above threshold. Missing days break a run (conservative)."""
    values = s.to_numpy()
    t = thr[leap_doy(s.index)]
    excess = values - t
    exceed = np.where(np.isnan(values) | np.isnan(t), False, values > t)

    edges = np.diff(np.concatenate([[0], exceed.astype(int), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]  # ends are exclusive

    events, in_event = [], np.zeros(len(s), dtype=bool)
    for a, b in zip(starts, ends):
        if b - a < min_days:
            continue
        in_event[a:b] = True
        events.append(
            {
                "start": s.index[a].date().isoformat(),
                "end": s.index[b - 1].date().isoformat(),
                "year": int(s.index[a].year),
                "duration": int(b - a),
                "peak_c": round(float(values[a:b].max()), 1),
                "mean_excess_c": round(float(np.nanmean(excess[a:b])), 2),
            }
        )
    return events, in_event, excess


def yearly_metrics(s, events, in_event, excess, start_year, end_year):
    """Per-year frequency and intensity. An event is attributed to the year it starts in."""
    values, years = s.to_numpy(), s.index.year.to_numpy()
    rows = []
    for year in range(start_year, end_year + 1):
        mask = years == year
        total = int(mask.sum())
        if total == 0:
            continue
        valid = int((~np.isnan(values[mask])).sum())
        year_events = [e for e in events if e["year"] == year]
        days = int(in_event[mask].sum())
        intensity = float(np.nanmean(excess[mask & in_event])) if days else None
        rows.append(
            {
                "year": year,
                "events": len(year_events),
                "heatwave_days": days,
                "max_duration": max((e["duration"] for e in year_events), default=0),
                "avg_duration": round(days / len(year_events), 1) if year_events else None,
                "mean_intensity_c": round(intensity, 2) if intensity is not None else None,
                "coverage_pct": round(100 * valid / total, 1),
                "low_coverage": valid / total < LOW_COVERAGE,
            }
        )
    return rows


# ---------------------------------------------------------------------------------------------
PERCENTILE, MIN_DAYS, WINDOW_DAYS = 95.0, 3, 15
CAVEATS = [
    "Thresholds come from the 1991-2020 baseline, so a window inside that period measures change within the baseline, not change against an older climate.",
    "Values are modelled reanalysis for one grid cell (about 10 km), not readings from a weather station.",
]


def analyze(raw: pd.Series, cfg, start_year: int, end_year: int) -> dict:
    s, cleaning = clean_series(raw)
    thr = daily_thresholds(s, cfg.BASELINE_START, cfg.BASELINE_END, PERCENTILE, WINDOW_DAYS)
    events, in_event, excess = detect_events(s, thr, MIN_DAYS)
    rows = yearly_metrics(s, events, in_event, excess, start_year, end_year)
    trend, insight = trends.summarise(rows, "heatwave_days", "Heatwave days", "days", CAVEATS)
    return {
        "hazard": "heatwave",
        "params": {
            "start_year": start_year, "end_year": end_year, "percentile": PERCENTILE,
            "min_consecutive_days": MIN_DAYS, "window_days": WINDOW_DAYS,
            "baseline": [cfg.BASELINE_START, cfg.BASELINE_END], "metric": "daily maximum 2 m temperature, deg C",
        },
        "quality": trends.quality_report(s[str(start_year) : str(end_year)], rows, cleaning),
        "yearly": rows,
        "events": [e for e in events if start_year <= e["year"] <= end_year][-300:],
        "trend": trend,
        "insight": insight,
        "display": {
            "id": "heatwave", "label": "Heatwave", "palette": "heat", "date_precision": "day",
            "primary": {"key": "heatwave_days", "label": "Heatwave days", "axis": "Days a year in a heatwave", "noun": "days in a heatwave"},
            "metrics": [
                {"key": "events", "label": "Heatwave events", "unit": "events a year"},
                {"key": "max_duration", "label": "Longest event", "unit": "days"},
                {"key": "mean_intensity_c", "label": "Intensity", "unit": "°C above the daily threshold"},
            ],
            "event_label": "heatwaves detected", "total_label": "days spent in a heatwave", "duration_unit": "days",
            "definition": "3 or more days above the 95th percentile",
            "events_title": "Longest heatwaves", "event_sort": "duration", "event_sort_label": "duration",
            "event_columns": [
                {"key": "peak_c", "label": "Peak °C", "prefix": ""},
                {"key": "mean_excess_c", "label": "Average °C above threshold", "prefix": "+"},
            ],
            "method": (
                "A day is hot when its maximum temperature is above the 95th percentile for that calendar day in 1991 to 2020, "
                "using a 15 day window around it. A heatwave is three or more hot days in a row, counted in the year it starts. "
                "Gaps of two days or less are filled by interpolation, impossible values and sudden spikes are removed, and longer gaps are left empty."
            ),
        },
        "context": {
            "type": "seasonal_line", "title": "What counts as unusually hot here",
            "caption": "The temperature a day must beat, for every day of the year, from 1991 to 2020.",
            "series_label": "95th percentile of daily maximum", "unit": "°C",
            "values": [None if np.isnan(t) else round(float(t), 1) for t in thr[1:]],
        },
    }
