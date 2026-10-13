import numpy as np
import pandas as pd
import pytest

import db as dbmod
from app import create_app
from config import Config
from services import drought, heatwave, openmeteo, rainfall, trends


def synthetic(trend=0.03, start="1991-01-01", end="2025-12-31", seed=0):
    idx = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    doy = idx.dayofyear.to_numpy()
    vals = 25 + 10 * np.sin(2 * np.pi * (doy - 100) / 365.25) + rng.normal(0, 2, len(idx)) + trend * (idx.year.to_numpy() - 1991)
    return pd.Series(vals, index=idx)


def synthetic_precip(start="1991-01-01", end="2025-12-31", seed=1):
    idx = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    season = np.sin(2 * np.pi * (idx.dayofyear.to_numpy() - 150) / 365.25)
    wet = rng.random(len(idx)) < 0.3 + 0.2 * season
    return pd.Series(rng.gamma(0.8, 8, len(idx)) * wet, index=idx)


def test_cleaning_removes_spikes_and_fills_only_short_gaps():
    s = synthetic()
    s.iloc[100] = 99.0
    s.iloc[200:202] = np.nan
    s.iloc[300:310] = np.nan
    cleaned, report = heatwave.clean_series(s)
    assert report["outliers_removed"] >= 1
    assert cleaned.iloc[100] < 60 and not np.isnan(cleaned.iloc[100])
    assert not cleaned.iloc[200:202].isna().any()
    assert cleaned.iloc[300:310].isna().all()


def test_injected_heatwave_is_detected_and_short_runs_are_ignored():
    s = synthetic()
    s.loc["2010-06-10":"2010-06-15"] += 12
    s.loc["2005-07-01":"2005-07-02"] += 12
    cleaned, _ = heatwave.clean_series(s)
    thr = heatwave.daily_thresholds(cleaned, 1991, 2020)
    events, _, _ = heatwave.detect_events(cleaned, thr)
    assert any(e["start"] <= "2010-06-12" <= e["end"] and e["duration"] >= 6 for e in events)
    assert all(e["duration"] >= 3 for e in events)


def test_mann_kendall_detects_trend_and_ignores_noise():
    rng = np.random.default_rng(3)
    rising = np.arange(30) * 0.5 + rng.normal(0, 1, 30)
    assert trends.mann_kendall(rising)["trend"] == "increasing"
    assert trends.mann_kendall(rng.normal(0, 1, 30))["significant"] is False


def test_drought_detected_for_injected_dry_spell():
    p = synthetic_precip()
    p.loc["2003-03-01":"2003-10-31"] = 0.0
    res = drought.analyze(p, Config, 1991, 2025)
    row = next(r for r in res["yearly"] if r["year"] == 2003)
    assert row["drought_months"] >= 3 and row["worst_spi"] <= -1.5
    assert any(e["year"] == 2003 and e["duration"] >= 3 for e in res["events"])
    assert res["context"]["type"] == "timeline_bars"


def test_heavy_rain_spell_is_detected():
    p = synthetic_precip()
    p.loc["2012-07-10":"2012-07-12"] = 200.0
    res = rainfall.analyze(p, Config, 1991, 2025)
    assert any(e["start"] <= "2012-07-10" and e["end"] >= "2012-07-12" and e["peak_mm"] >= 200 for e in res["events"])
    assert next(r for r in res["yearly"] if r["year"] == 2012)["rx1day"] == 200.0


def test_too_dry_place_is_rejected_cleanly():
    with pytest.raises(ValueError):
        rainfall.analyze(pd.Series(0.0, index=pd.date_range("1991-01-01", "2025-12-31")), Config, 1991, 2025)


@pytest.fixture
def client(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(lat, lon, start, end, variable, api_key=""):
        calls["n"] += 1
        if variable == "temperature_2m_max":
            s = synthetic(trend=0.08, start=start.isoformat(), end=end.isoformat())
        else:
            s = synthetic_precip(start=start.isoformat(), end=end.isoformat())
        return [d.date().isoformat() for d in s.index], s.tolist()

    monkeypatch.setattr(openmeteo, "fetch_daily", fake_fetch)
    dbmod._client = None

    class TestConfig(Config):
        USE_MOCK_DB = True
        RATE_LIMIT_ANALYZE = "1000 per minute"

    app = create_app(TestConfig)
    app.testing = True
    c = app.test_client()
    c.calls = calls
    return c


def test_full_pipeline_and_database_cache(client):
    url = "/api/hazards/heatwave?lat=28.61&lon=77.21&start=1990&end=2025"
    first = client.get(url)
    assert first.status_code == 200
    body = first.get_json()
    assert len(body["yearly"]) == 36 and body["trend"]["mann_kendall"]["trend"] == "increasing"
    assert body["insight"]["headline"]

    again = client.get(url + "&name=Somewhere")  # new HTTP cache key, same analysis in MongoDB
    assert again.status_code == 200 and client.calls["n"] == 1

    csv = client.get("/api/hazards/heatwave/export.csv?lat=28.61&lon=77.21&start=1990&end=2025")
    assert csv.status_code == 200 and csv.mimetype == "text/csv"


def test_bounding_box_accepted(client):
    r = client.get("/api/hazards/heatwave?south=28&west=76&north=30&east=78&start=2000&end=2020")
    assert r.status_code == 200 and r.get_json()["region"]["bbox"] == [28.0, 76.0, 30.0, 78.0]


@pytest.mark.parametrize(
    "query",
    [
        "lat=999&lon=77&start=1990&end=2020",
        "lat=28&lon=77&start=2015&end=2020",
        "lat=28&lon=77&start=abcd&end=2020",
        "south=0&west=0&north=40&east=40&start=1990&end=2020",
        "lat=nan&lon=77&start=1990&end=2020",
    ],
)
def test_bad_input_is_rejected(client, query):
    assert client.get(f"/api/hazards/heatwave?{query}").status_code == 400


@pytest.mark.parametrize("hazard", ["heatwave", "drought", "heavy_rain"])
def test_every_hazard_returns_the_common_shape(client, hazard):
    r = client.get(f"/api/hazards/{hazard}?lat=28.61&lon=77.21&start=1990&end=2025")
    assert r.status_code == 200
    body = r.get_json()
    assert body["display"]["id"] == hazard and len(body["yearly"]) == 36
    assert body["display"]["primary"]["key"] in body["yearly"][0]
    assert body["context"]["type"] and body["insight"]["headline"]
    assert client.get(f"/api/hazards/{hazard}/export.csv?lat=28.61&lon=77.21&start=1990&end=2025").status_code == 200


def test_precipitation_is_fetched_once_for_drought_and_rain(client):
    q = "lat=10&lon=20&start=1995&end=2020"
    client.get(f"/api/hazards/drought?{q}")
    client.get(f"/api/hazards/heavy_rain?{q}")
    assert client.calls["n"] == 1  # both hazards share the cached precipitation series


def test_unknown_hazard(client):
    assert client.get("/api/hazards/tornado?lat=1&lon=1&start=1990&end=2020").status_code == 404
