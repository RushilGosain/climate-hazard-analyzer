"""Thin, defensive client for the Open-Meteo APIs (no API key needed for non-commercial use).

Safety notes: hosts are hard-coded (no user-controlled URLs, so no SSRF), every call has a
timeout, transient failures are retried with backoff, and raw upstream errors never reach clients.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
PAID_ARCHIVE_URL = "https://customer-archive-api.open-meteo.com/v1/archive"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class UpstreamError(Exception):
    """The weather provider failed or returned something unusable."""


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "climate-hazard-analyzer/1.0"
    return session


SESSION = _make_session()


ALLOWED_VARIABLES = {"temperature_2m_max", "precipitation_sum"}  # allow-list: never forward arbitrary names


def fetch_daily(lat, lon, start, end, variable, api_key=""):
    """One daily variable between two dates (temperature_2m_max in deg C, precipitation_sum in mm)."""
    if variable not in ALLOWED_VARIABLES:
        raise ValueError("Unsupported weather variable")
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": variable,
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "timezone": "auto",
    }
    url = ARCHIVE_URL
    if api_key:
        url, params["apikey"] = PAID_ARCHIVE_URL, api_key
    try:
        resp = SESSION.get(url, params=params, timeout=(5, 60))
        resp.raise_for_status()
        daily = resp.json().get("daily") or {}
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError("The weather data provider is unavailable. Try again shortly.") from exc
    times, values = daily.get("time"), daily.get(variable)
    if not times or values is None or len(times) != len(values):
        raise UpstreamError("The weather data provider returned an unexpected response.")
    return times, values


def geocode(query, count=6):
    try:
        resp = SESSION.get(
            GEOCODE_URL,
            params={"name": query, "count": count, "language": "en", "format": "json"},
            timeout=(5, 10),
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError("Place search is unavailable. Try again shortly.") from exc
    return [
        {
            "name": r.get("name"),
            "admin1": r.get("admin1"),
            "country": r.get("country"),
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
        }
        for r in results
        if r.get("latitude") is not None and r.get("longitude") is not None
    ]
