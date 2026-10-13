"""Ingest -> cache -> detect -> trend -> store -> read back, for every hazard.

The API never returns freshly computed numbers directly: it makes sure the analysis document
exists in MongoDB (computing and storing it once if not) and then returns what it reads from the DB.
"""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from services import drought, heatwave, openmeteo, rainfall

# hazard id -> (Open-Meteo variable, analysis module). Adding a hazard means adding one line and one module.
HAZARDS = {
    "heatwave": ("temperature_2m_max", heatwave),
    "drought": ("precipitation_sum", drought),
    "heavy_rain": ("precipitation_sum", rainfall),
}
METHOD = "v2"


def snap(value: float, step: float = 0.25) -> float:
    return round(round(value / step) * step, 2)


def _load_series(db, cfg, cell, variable, lat_c, lon_c, start_year, end_year):
    need_start, need_end = date(min(cfg.BASELINE_START, start_year), 1, 1), date(end_year, 12, 31)
    where = {"cell": cell, "variable": variable}
    doc = db.series_cache.find_one(where)
    if doc:
        have_start = date.fromisoformat(doc["start"])
        have_end = have_start + timedelta(days=len(doc["values"]) - 1)
        if have_start <= need_start and have_end >= need_end:
            return doc  # cache hit: no network call at all
        need_start, need_end = min(need_start, have_start), max(need_end, have_end)

    times, values = openmeteo.fetch_daily(lat_c, lon_c, need_start, need_end, variable, cfg.OPEN_METEO_API_KEY)
    series = pd.Series(np.array(values, dtype=float), index=pd.to_datetime(times))
    series = series.reindex(pd.date_range(need_start, need_end, freq="D"))
    doc = {
        **where,
        "lat": lat_c,
        "lon": lon_c,
        "start": need_start.isoformat(),
        "values": [None if np.isnan(v) else float(v) for v in series.to_numpy()],
        "source": "open-meteo-archive",
        "fetched_at": datetime.now(timezone.utc),
    }
    db.series_cache.replace_one(where, doc, upsert=True)
    return doc


def get_analysis(db, cfg, hazard, lat, lon, start_year, end_year):
    variable, module = HAZARDS[hazard]
    lat_c, lon_c = snap(lat), snap(lon)
    cell = f"{lat_c:.2f},{lon_c:.2f}"
    key = f"{hazard}|{cell}|{start_year}|{end_year}|b{cfg.BASELINE_START}-{cfg.BASELINE_END}|{METHOD}"

    if db.analyses.find_one({"key": key}, {"_id": 1}) is None:
        doc = _load_series(db, cfg, cell, variable, lat_c, lon_c, start_year, end_year)
        raw = pd.Series(
            np.array(doc["values"], dtype=float),
            index=pd.date_range(doc["start"], periods=len(doc["values"]), freq="D"),
        )
        analysis = module.analyze(raw, cfg, start_year, end_year)
        analysis.update({"key": key, "cell": {"lat": lat_c, "lon": lon_c}, "created_at": datetime.now(timezone.utc)})
        db.analyses.replace_one({"key": key}, analysis, upsert=True)

    return db.analyses.find_one({"key": key}, {"_id": 0, "key": 0, "created_at": 0})
