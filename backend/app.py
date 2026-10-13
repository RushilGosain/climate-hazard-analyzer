"""Flask API for the Climate Hazard Trend Analyzer."""
import csv
import io
import logging
import math
import re

from flask import Flask, Response, jsonify, request
from flask_caching import Cache
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import db as dbmod
from config import Config, max_year
from services import openmeteo, pipeline

log = logging.getLogger("hazards")

HAZARDS = [
    {"id": "heatwave", "label": "Heatwave", "enabled": True},
    {"id": "drought", "label": "Drought", "enabled": True},
    {"id": "heavy_rain", "label": "Heavy rainfall", "enabled": True},
]


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def _number(name, lo, hi):
    raw = request.args.get(name)
    if raw is None:
        raise ApiError(f"Missing parameter: {name}")
    try:
        value = float(raw)
    except ValueError:
        raise ApiError(f"{name} must be a number")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ApiError(f"{name} must be between {lo} and {hi}")
    return value


def _year(name, lo, hi):
    raw = request.args.get(name, "")
    if not re.fullmatch(r"\d{4}", raw):
        raise ApiError(f"{name} must be a four digit year")
    year = int(raw)
    if not lo <= year <= hi:
        raise ApiError(f"{name} must be between {lo} and {hi}")
    return year


def parse_query(cfg):
    """Validate every user-supplied value before it gets near the database or an upstream API."""
    bbox = None
    if any(k in request.args for k in ("south", "west", "north", "east")):
        s, w = _number("south", -90, 90), _number("west", -180, 180)
        n, e = _number("north", -90, 90), _number("east", -180, 180)
        if n <= s or e <= w:
            raise ApiError("The box must have north above south and east right of west")
        if n - s > cfg.MAX_BBOX_DEG or e - w > cfg.MAX_BBOX_DEG:
            raise ApiError(f"The box may be at most {cfg.MAX_BBOX_DEG} degrees on each side")
        lat, lon, bbox = (s + n) / 2, (w + e) / 2, [s, w, n, e]
    else:
        lat, lon = _number("lat", -90, 90), _number("lon", -180, 180)

    top = max_year()
    start, end = _year("start", cfg.MIN_YEAR, top), _year("end", cfg.MIN_YEAR, top)
    if end - start + 1 < cfg.MIN_SPAN_YEARS:
        raise ApiError(f"Choose at least {cfg.MIN_SPAN_YEARS} years so a trend can be measured")
    if end - start + 1 > cfg.MAX_SPAN_YEARS:
        raise ApiError(f"Choose at most {cfg.MAX_SPAN_YEARS} years")

    name = re.sub(r"[^\w\s,.()'\-]", "", request.args.get("name", "")).strip()[:80]
    return {"lat": lat, "lon": lon, "bbox": bbox, "start": start, "end": end, "name": name or f"{lat:.2f}, {lon:.2f}"}


def create_app(config=Config, database=None):
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)  # trust one proxy hop (Render, Cloud Run) for real client IPs
    cfg = config
    app.config["JSON_SORT_KEYS"] = False

    CORS(app, origins=cfg.CORS_ORIGINS, methods=["GET"])
    cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": cfg.CACHE_TTL_SECONDS})
    limiter = Limiter(get_remote_address, app=app, default_limits=[cfg.RATE_LIMIT_DEFAULT], storage_uri="memory://")

    def database_handle():
        return database if database is not None else dbmod.get_db(cfg)

    if database is None:
        dbmod.ensure_indexes(database_handle())

    def run_analysis(hazard, q):
        if hazard not in pipeline.HAZARDS:
            raise ApiError("Unknown hazard. Use heatwave, drought or heavy_rain.", 404)
        doc = pipeline.get_analysis(database_handle(), cfg, hazard, q["lat"], q["lon"], q["start"], q["end"])
        doc["region"] = {"name": q["name"], "lat": q["lat"], "lon": q["lon"], "bbox": q["bbox"]}
        return doc

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return resp

    @app.get("/api/health")
    @limiter.exempt
    def health():
        return jsonify(status="ok")

    @app.get("/api/meta")
    def meta():
        return jsonify(
            hazards=HAZARDS,
            min_year=cfg.MIN_YEAR,
            max_year=max_year(),
            min_span_years=cfg.MIN_SPAN_YEARS,
            max_span_years=cfg.MAX_SPAN_YEARS,
            max_bbox_deg=cfg.MAX_BBOX_DEG,
            baseline=[cfg.BASELINE_START, cfg.BASELINE_END],
        )

    @app.get("/api/geocode")
    @limiter.limit("30 per minute")
    @cache.cached(timeout=24 * 3600, query_string=True)
    def geocode():
        query = re.sub(r"\s+", " ", request.args.get("q", "")).strip()
        if len(query) < 2 or len(query) > 80:
            raise ApiError("Type between 2 and 80 characters to search for a place")
        return jsonify(results=openmeteo.geocode(query))

    @app.get("/api/hazards/<hazard>")
    @limiter.limit(cfg.RATE_LIMIT_ANALYZE)
    @cache.cached(query_string=True)
    def hazard_analysis(hazard):
        return jsonify(run_analysis(hazard, parse_query(cfg)))

    @app.get("/api/hazards/<hazard>/export.csv")
    @limiter.limit(cfg.RATE_LIMIT_ANALYZE)
    @cache.cached(query_string=True)
    def hazard_csv(hazard):
        doc = run_analysis(hazard, parse_query(cfg))
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(doc["yearly"][0].keys()))
        writer.writeheader()
        writer.writerows(doc["yearly"])
        filename = f"{hazard}_{doc['params']['start_year']}_{doc['params']['end_year']}.csv"
        return Response(out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(error=err.message), err.status

    @app.errorhandler(openmeteo.UpstreamError)
    def handle_upstream(err):
        return jsonify(error=str(err)), 502

    @app.errorhandler(ValueError)
    def handle_value_error(err):
        return jsonify(error=str(err)), 422

    @app.errorhandler(PyMongoError)
    def handle_db(err):
        log.exception("Database error")
        return jsonify(error="The database is unavailable. Try again shortly."), 503

    @app.errorhandler(HTTPException)
    def handle_http(err):
        message = "Too many requests. Wait a moment and try again." if err.code == 429 else err.description
        return jsonify(error=message), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        log.exception("Unhandled error")
        return jsonify(error="Something went wrong on our side."), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=5000, debug=False)
