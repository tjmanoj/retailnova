"""RetailNova API (FastAPI). Routes live under /api (docs/contracts.md §5)."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .db import cache, clean_doc, fs, log, now_iso
from .limits import ApiError, chat_limiter, check_message, decode_image, plan_limiter
from .models import AskRequest, ChatRequest, ItemRequest, PlanRequest
from .sse import sse_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.WARM_ON_STARTUP:
        async def warm():
            from .llm import warm_up
            from .tools import catalog

            from .tools import inventory

            try:
                await asyncio.gather(catalog.products(), inventory.warm_inventory())
            except Exception as e:
                log("WARNING", "catalog warm-up failed", error=type(e).__name__)
            await warm_up()
            try:  # BigQuery caches for the default store (radar, plan, manager Q&A)
                from .tools import ops

                await asyncio.gather(ops.forecast_rows(config.DEFAULT_STORE), ops.sales_by_day(config.DEFAULT_STORE),
                                     ops.sku_velocity("sarees"), return_exceptions=True)
            except Exception:
                pass
            try:  # build the agents so the first request does not pay for it
                from .agents import concierge, manager_qa

                concierge.runner()
                manager_qa.runner()
            except Exception as e:
                log("WARNING", "agent warm-up failed", error=type(e).__name__, detail=str(e)[:200])

        asyncio.create_task(warm())
    yield


app = FastAPI(title="RetailNova API", version=config.VERSION, lifespan=lifespan)

if config.ALLOWED_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Errors and request logging
# ---------------------------------------------------------------------------

@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": str(exc.detail)}})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(status_code=422, content={"error": {"code": "invalid_request",
                                                            "message": f"Invalid request: {loc} {first.get('msg', '')}".strip()}})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log("ERROR", "unhandled error", path=request.url.path, error=type(exc).__name__, detail=str(exc)[:300])
    return JSONResponse(status_code=500, content={"error": {"code": "internal", "message": "Something went wrong. Please try again."}})


@app.middleware("http")
async def access_log(request: Request, call_next):
    # Request-arrival time: streams use it for done.latency_ms, so time spent before the handler shows up.
    t0 = time.monotonic()
    request.state.t0 = t0
    if request.url.path != "/api/health":
        log("INFO", "request start", method=request.method, route=request.url.path)
    response = await call_next(request)
    if request.url.path not in ("/api/chat", "/api/plan", "/api/ask"):  # streams log their own line
        log("INFO", "request", method=request.method, route=request.url.path, status=response.status_code,
            latency_ms=int((time.monotonic() - t0) * 1000))
    return response


def _session_key(request: Request, session_id: Optional[str]) -> str:
    if session_id:
        return session_id
    xf = request.headers.get("x-forwarded-for", "")
    return xf.split(",")[0].strip() or (request.client.host if request.client else "anon")


def _check_store(store_id: Optional[str]) -> str:
    s = (store_id or config.DEFAULT_STORE).strip().upper()
    if s not in config.STORES:
        raise ApiError(400, "unknown_store", f"Unknown store_id {store_id}.")
    return s


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": config.VERSION, "time": now_iso()}


@app.get("/api/bootstrap")
async def bootstrap():
    async def load_meta():
        try:
            d = await fs().document("meta/demo").get()
            return clean_doc(d.to_dict()) if d.exists else {}
        except Exception:
            return {}

    meta = await cache.get_or_load("meta", 15.0, load_meta)
    stores = [{k: v for k, v in s.items()} for s in config.STORES.values()]
    return {
        "demo_today": config.DEMO_TODAY,
        "diwali_date": config.DIWALI_DATE,
        "days_to_diwali": config.DAYS_TO_DIWALI,
        "stores": stores,
        "categories": [{"category": c["category"], "label": c["label"]} for c in config.CATEGORIES],
        "sample_prompts": config.SAMPLE_PROMPTS,
        "reset_at": meta.get("reset_at"),
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    check_message(req.message)
    image = decode_image(req.image_base64)
    chat_limiter.check(_session_key(request, req.session_id))
    if not (req.message or "").strip() and not image:
        raise ApiError(400, "empty_message", "Please type a message or attach a photo.")
    store_id = _check_store(req.store_id)
    from .agents.concierge import run_chat

    return sse_response(run_chat(req.session_id, (req.message or "").strip(), store_id, image, req.image_mime,
                                 t0=getattr(request.state, "t0", None)))


@app.post("/api/notify")
async def notify(req: ItemRequest):
    from .tools import catalog, inventory as inv

    store_id = _check_store(req.store_id)
    p = await catalog.product(req.sku)
    if not p:
        raise ApiError(404, "unknown_sku", f"We couldn't find {req.sku}.")
    w = await inv.create_waitlist(req.session_id, p["sku"], (req.size or "FREE").upper(), store_id)
    return {"waitlist_id": w["waitlist_id"],
            "message": f"Done! We'll let you know as soon as {p.get('name')} is available at {config.store_name(store_id)}."}


@app.post("/api/reserve")
async def reserve(req: ItemRequest):
    from .tools import catalog, inventory as inv

    store_id = _check_store(req.store_id)
    p = await catalog.product(req.sku)
    if not p:
        raise ApiError(404, "unknown_sku", f"We couldn't find {req.sku}.")
    size = (req.size or "FREE").upper()
    size_txt = f" (size {size})" if size != "FREE" else ""
    rows = (await inv.inventory_for_skus([p["sku"]])).get(p["sku"], [])
    if inv.qty_at(rows, store_id, size) <= 0:
        raise ApiError(409, "out_of_stock",
                       f"{p.get('name')}{size_txt} is out of stock at {config.store_name(store_id)}. Try notify-me or another store.")
    r = await inv.create_reservation(req.session_id, p["sku"], size, store_id)
    return {"reservation_id": r["reservation_id"], "hold_until": r["hold_until"],
            "message": f"Reserved! {p.get('name')}{size_txt} is held for you at {config.store_name(store_id)} for 48 hours."}


@app.get("/api/notifications")
async def notifications(session_id: str):
    from .actions import notifications_for

    return {"items": await notifications_for(session_id)}


@app.get("/api/radar")
async def radar(store_id: str = config.DEFAULT_STORE, category: Optional[str] = None):
    from .tools import catalog, ops

    sid = _check_store(store_id)
    cat = catalog.normalize_category(category) if category else None
    if category and not cat:
        raise ApiError(400, "unknown_category", f"Unknown category {category}.")
    return await cache.get_or_load(("radar", sid, cat), 10.0, lambda: ops.radar(sid, cat))


@app.post("/api/plan")
async def plan(req: PlanRequest, request: Request):
    if req.question:
        check_message(req.question)
    plan_limiter.check(_session_key(request, req.session_id))
    store_id = _check_store(req.store_id)
    from .agents.ops_planner import run_plan

    return sse_response(run_plan(store_id, req.category, req.horizon_days, req.question,
                                 t0=getattr(request.state, "t0", None)))


@app.post("/api/ask")
async def ask(req: AskRequest, request: Request):
    check_message(req.question)
    if not req.question.strip():
        raise ApiError(400, "empty_question", "Please ask a question.")
    chat_limiter.check("ask:" + _session_key(request, req.session_id))
    store_id = _check_store(req.store_id)
    from .agents.manager_qa import run_ask

    return sse_response(run_ask(store_id, req.question.strip(), req.session_id, t0=getattr(request.state, "t0", None)))


@app.post("/api/actions/{action_id}/approve")
async def approve_action(action_id: str):
    from .actions import approve

    return await approve(action_id)


@app.post("/api/actions/{action_id}/reject")
async def reject_action(action_id: str):
    from .actions import reject

    return await reject(action_id)


@app.post("/api/demo/reset")
async def demo_reset():
    from .actions import reset_demo

    res = await reset_demo()
    try:
        from .agents import concierge

        concierge._session_signals.clear()
    except Exception:
        pass
    chat_limiter.reset()
    plan_limiter.reset()
    return res
