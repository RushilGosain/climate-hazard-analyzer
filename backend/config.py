"""Central configuration. Every value can be overridden with an environment variable."""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def max_year() -> int:
    """Last *complete* calendar year; the archive lags real time by a few days."""
    return date.today().year - 1


class Config:
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB = os.getenv("MONGODB_DB", "climate_hazards")
    # Set USE_MOCK_DB=1 to run without MongoDB (in-memory, resets on restart).
    USE_MOCK_DB = os.getenv("USE_MOCK_DB", "0") == "1"

    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
    RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "300 per hour")
    RATE_LIMIT_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "20 per minute")
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

    # Optional. Only needed for commercial use of Open-Meteo.
    OPEN_METEO_API_KEY = os.getenv("OPEN_METEO_API_KEY", "")

    # Climate logic
    BASELINE_START = 1991  # WMO standard normal period
    BASELINE_END = 2020
    MIN_YEAR = 1950
    MIN_SPAN_YEARS = 10  # fewer points make a trend statistically meaningless
    MAX_SPAN_YEARS = 45
    MAX_BBOX_DEG = 5.0
