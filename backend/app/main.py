"""HTTP boundary for the local Track 2 dispatch desk."""

import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter
from collections import deque
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from dotenv import load_dotenv
from pydantic import ValidationError
from backend.app.schemas import ChatRequest, RecommendationRequest, ToolCall
from backend.app.data_access import (
    get_orders,
    get_order,
    get_workshops,
    get_requests,
    dataset_info,
)
from backend.app.agent.graph import run_chat
from backend.app.agent.llm_provider import provider_status
from backend.app.services.audit import history, get_record
from backend.app.tools import tool_specs, call_tool

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend/.env")
app = FastAPI(
    title="SweaterCo Dispatch Desk",
    version="1.0.0",
    description="Track 2 · 建议与审计；无自动下单工具。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-App-Token"],
)
logger = logging.getLogger("dispatch")
latencies = deque(maxlen=500)
metrics = {"requests": 0, "errors": 0}
evaluation_lock = Lock()


def error(code, message, status=400, retryable=False):
    return JSONResponse(
        {"error": {"code": code, "message": message, "retryable": retryable}},
        status_code=status,
    )


@app.middleware("http")
async def observe(request: Request, call_next):
    start = perf_counter()
    try:
        body_size = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return error("INVALID_CONTENT_LENGTH", "请求长度格式无效。", 400)
    if body_size < 0:
        return error("INVALID_CONTENT_LENGTH", "请求长度不能为负数。", 400)
    if request.url.path.startswith("/api/") and body_size > 64000:
        return error("BODY_TOO_LARGE", "请求过大，请缩短消息。", 413)
    # Optional token for a server behind a trusted reverse proxy; local default is loopback-only.
    token = os.getenv("APP_ACCESS_TOKEN")
    if (
        token
        and request.url.path.startswith("/api/")
        and request.url.path != "/api/health"
    ):
        import hmac

        if not hmac.compare_digest(request.headers.get("X-App-Token", ""), token):
            return error("UNAUTHORIZED", "需要已授权的服务访问凭证。", 401)
    response = await call_next(request)
    elapsed = round((perf_counter() - start) * 1000, 2)
    metrics["requests"] += 1
    metrics["errors"] += int(response.status_code >= 400)
    latencies.append(elapsed)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Process-Time-Ms"] = str(elapsed)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    logger.info(
        "request method=%s path=%s status=%d duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    return error(
        "VALIDATION_ERROR", "输入格式不正确，请检查消息、日期、件数和目标选项。", 422
    )


@app.exception_handler(HTTPException)
async def http_handler(request, exc):
    return error("HTTP_ERROR", str(exc.detail), exc.status_code)


@app.exception_handler(ValidationError)
async def tool_validation_handler(request, exc):
    return error("VALIDATION_ERROR", "工具参数未通过类型校验。", 422)


@app.exception_handler(ValueError)
async def value_handler(request, exc):
    return error("INVALID_REQUEST", "参数未通过业务校验：" + str(exc), 422)


@app.exception_handler(LookupError)
async def lookup_handler(request, exc):
    return error("NOT_FOUND", "未找到对应的订单、工坊或记录。", 404)


@app.exception_handler(Exception)
async def generic_handler(request, exc):
    logger.error("request_failed type=%s", type(exc).__name__)
    return error("INTERNAL_ERROR", "服务暂时无法完成请求，请稍后重试。", 500, True)


@app.get("/api/health")
def health():
    data = dataset_info()
    return {
        "status": "ok" if data["source_verified"] else "degraded",
        "version": "1.0.0",
        "mode": provider_status()["mode"],
        "reference_date": "2026-04-01",
        "data": data,
    }


@app.get("/api/settings")
def settings():
    return {
        **provider_status(),
        "version": "1.0.0",
        "workflow": "bounded_state_machine",
        "execution_mode": "recommendation_only",
        "auth_mode": "token" if os.getenv("APP_ACCESS_TOKEN") else "local_single_user",
        "checkpoint_expiry_hours": 24,
        "objectives": ["lateness", "quality", "fairness", "robustness", "hybrid"],
        "dataset": dataset_info(),
    }


@app.get("/api/orders")
def orders(q: str = "", status: str | None = None, stages: bool = False):
    items = get_orders(stages)
    if q:
        items = [
            o
            for o in items
            if q.lower() in " ".join(str(v) for v in o.values()).lower()
        ]
    if status:
        items = [o for o in items if o["status"] == status]
    return {"items": items}


@app.get("/api/orders/{order_id}")
def order(order_id: str, stages: bool = False):
    return get_order(order_id, stages)


@app.get("/api/workshops")
def workshops(
    category: str | None = None, status: str | None = None, stages: bool = False
):
    items = get_workshops(stages)
    if category:
        items = [w for w in items if category in w["makes"].split("+")]
    if status:
        items = [w for w in items if w["status"] == status]
    return {"items": items}


@app.get("/api/requests")
def requests():
    return {"items": get_requests()}


@app.get("/api/requests/{request_id}")
def request_record(request_id: str):
    record = get_record(request_id)
    if record:
        return record
    for row in get_requests():
        if row["id"] == request_id:
            return row
    raise HTTPException(404, "未找到请求记录。")


@app.post("/api/chat")
def chat(body: ChatRequest):
    return run_chat(body.message, body.session_id, body.objective, body.stages)


@app.post("/api/recommendations")
def recommendation(body: RecommendationRequest):
    order = get_order(body.order_id, body.stages)
    names = {w["workshop_id"]: w["name"] for w in get_workshops(body.stages)}
    if any(w not in names for w in body.excluded_workshops) or (
        body.preferred_workshop and body.preferred_workshop not in names
    ):
        raise ValueError("工坊编号须为 W1–W8")
    message = f"{body.order_id}，{body.pieces or order['pieces']} 件，截止 {body.due_date.isoformat() if body.due_date else order['due_date']}。"
    for wid in body.excluded_workshops:
        message += " 不要给 " + names[wid] + "。"
    if body.preferred_workshop:
        message += " 建议 " + names[body.preferred_workshop] + "。"
    if body.allow_split:
        message += " 可以拆单。"
    return run_chat(
        message, objective=body.objective, stages=body.stages, use_llm=False
    )


@app.get("/api/history")
def audit_history(limit: int = Query(default=100, ge=1, le=500)):
    return {"items": history(limit)}


@app.get("/api/tools")
def tools():
    return {"items": tool_specs()}


@app.post("/api/tools/call")
def tool_call(body: ToolCall):
    return call_tool(body.name, body.arguments)


@app.get("/api/evaluations")
@app.get("/api/evaluations/latest")
def evaluations():
    from evals.run_evaluation import load_report

    return load_report()


@app.post("/api/evaluations/run")
def evaluate():
    if not evaluation_lock.acquire(blocking=False):
        raise HTTPException(409, "评估正在运行，请稍后读取报告。")
    try:
        from evals.run_evaluation import evaluate_all

        return evaluate_all(save=True)
    finally:
        evaluation_lock.release()


@app.get("/api/metrics")
def observe_metrics():
    return {
        **metrics,
        "mean_latency_ms": round(sum(latencies) / len(latencies), 2)
        if latencies
        else 0,
        "window_size": len(latencies),
        "provider": provider_status()["mode"],
    }


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API 不存在。")
    dist = (ROOT / "frontend/dist").resolve()
    target = (dist / path).resolve()
    if not target.is_relative_to(dist):
        raise HTTPException(404, "文件不存在。")
    if target.is_file():
        return FileResponse(target)
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html")
    return JSONResponse(
        {
            "service": "SweaterCo Dispatch Desk",
            "message": "前端尚未构建；使用 npm run build 后刷新。",
            "docs": "/docs",
        }
    )
