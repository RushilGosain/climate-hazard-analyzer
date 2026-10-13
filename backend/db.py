"""MongoDB access. Two collections:

series_cache  one document per (0.25 degree grid cell, weather variable) holding the raw daily array (the cache)
analyses      one document per (cell, range, method version) holding computed hazard results
"""
import logging

from pymongo import ASCENDING, MongoClient

log = logging.getLogger("hazards.db")
_client = None


def get_db(cfg):
    global _client
    if _client is None:
        if cfg.USE_MOCK_DB:
            import mongomock

            _client = mongomock.MongoClient()
        else:
            _client = MongoClient(cfg.MONGODB_URI, serverSelectionTimeoutMS=5000)
    return _client[cfg.MONGODB_DB]


def ensure_indexes(db):
    try:
        db.series_cache.create_index([("cell", ASCENDING), ("variable", ASCENDING)], unique=True)
        db.analyses.create_index([("key", ASCENDING)], unique=True)
        # Drop stale analyses after 90 days so method changes never serve ancient results.
        db.analyses.create_index("created_at", expireAfterSeconds=90 * 24 * 3600)
    except Exception as exc:  # index creation must never stop the API from booting
        log.warning("Could not create indexes: %s", exc)
