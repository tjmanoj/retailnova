"""Lazily created Firestore / BigQuery / Gemini clients, small TTL caches and logging."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from . import config

# ---------------------------------------------------------------------------
# Structured JSON logging (one line per record; Cloud Logging parses it)
# ---------------------------------------------------------------------------

_logger = logging.getLogger("retailnova")
if not _logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def log(severity: str = "INFO", msg: str = "", **fields: Any) -> None:
    rec = {"severity": severity, "message": msg, "time": now_iso(), **fields}
    try:
        _logger.info(json.dumps(rec, default=str, ensure_ascii=False))
    except Exception:  # never let logging break a request
        pass


# ---------------------------------------------------------------------------
# Time / ids
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat().replace("+00:00", "Z")


def iso(v: Any) -> Any:
    """Serialise Firestore timestamps / datetimes to ISO-8601 UTC strings."""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return v


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def clean_doc(d: dict | None) -> dict:
    """Convert Firestore values to JSON-friendly values (timestamps -> ISO, drop vectors)."""
    if not d:
        return {}
    out = {}
    for k, v in d.items():
        if k == "embedding":
            continue
        if isinstance(v, dict):
            out[k] = clean_doc(v)
        elif isinstance(v, list):
            out[k] = [clean_doc(x) if isinstance(x, dict) else iso(x) for x in v]
        else:
            out[k] = iso(v)
    return out


# ---------------------------------------------------------------------------
# Clients (lazy)
# ---------------------------------------------------------------------------

_fs = None
_bq = None
_genai = None


def fs():
    """Async Firestore client."""
    global _fs
    if _fs is None:
        from google.cloud import firestore

        _fs = firestore.AsyncClient(project=config.PROJECT)
    return _fs


def bq():
    global _bq
    if _bq is None:
        from google.cloud import bigquery

        _bq = bigquery.Client(project=config.PROJECT, location=config.BQ_LOCATION)
    return _bq


def genai_client():
    global _genai
    if _genai is None:
        from google import genai
        from google.genai import types

        _genai = genai.Client(
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(
                    attempts=3, initial_delay=0.6, max_delay=4, exp_base=2, http_status_codes=[429, 503]
                ),
            )
        )
    return _genai


# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------

class TTLCache:
    def __init__(self) -> None:
        self._data: dict[Any, tuple[float, Any]] = {}
        self._locks: dict[Any, asyncio.Lock] = {}

    def get(self, key: Any) -> Any:
        hit = self._data.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        return None

    def set(self, key: Any, value: Any, ttl: float) -> None:
        self._data[key] = (time.monotonic() + ttl, value)

    async def get_or_load(self, key: Any, ttl: float, loader: Callable[[], Awaitable[Any]]) -> Any:
        v = self.get(key)
        if v is not None:
            return v
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            v = self.get(key)
            if v is not None:
                return v
            v = await loader()
            self.set(key, v, ttl)
            return v

    def invalidate(self, prefix: Any = None) -> None:
        if prefix is None:
            self._data.clear()
            return
        for k in list(self._data.keys()):
            if (isinstance(k, tuple) and k and k[0] == prefix) or k == prefix:
                del self._data[k]


cache = TTLCache()


# ---------------------------------------------------------------------------
# BigQuery helper (runs in a thread; missing tables are reported, not raised)
# ---------------------------------------------------------------------------

class BQUnavailable(Exception):
    pass


def _bq_query_sync(sql: str, params: list | None = None, timeout: float = 25.0) -> list[dict]:
    from google.cloud import bigquery
    from google.api_core import exceptions as gexc

    job_config = bigquery.QueryJobConfig(query_parameters=params or [], use_query_cache=True)
    try:
        job = bq().query(sql, job_config=job_config, timeout=timeout)
        rows = job.result(timeout=timeout)
        return [dict(r.items()) for r in rows]
    except gexc.NotFound as e:
        raise BQUnavailable(f"table not found: {str(e)[:160]}")
    except gexc.BadRequest as e:
        raise BQUnavailable(f"bad query or missing table: {str(e)[:160]}")


async def bq_query(sql: str, params: list | None = None, timeout: float = 25.0) -> list[dict]:
    return await asyncio.wait_for(asyncio.to_thread(_bq_query_sync, sql, params, timeout), timeout + 5)


def bq_table(name: str) -> str:
    return f"`{config.PROJECT}.{config.BQ_DATASET}.{name}`"
