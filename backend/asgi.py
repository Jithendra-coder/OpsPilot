from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from io import BytesIO

import app as core
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from backend import telemetry

log = logging.getLogger("opspilot.api")


@asynccontextmanager
async def lifespan(_app):
    await run_in_threadpool(core.initialize)
    yield


app = FastAPI(title="OpsPilot API", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    })
    return response


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    method = request.method
    route = "unmatched"
    status = 500
    if telemetry.tracer:
        with telemetry.tracer.start_as_current_span("http.server") as span:
            span.set_attribute("http.request.method", method)
            try:
                response = await call_next(request)
                status = response.status_code
                route = getattr(request.scope.get("route"), "path", "unmatched")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status)
                return response
            except Exception as error:
                span.record_exception(error)
                raise
            finally:
                telemetry.record_request(method, route, status, time.perf_counter() - started)
    try:
        response = await call_next(request)
        status = response.status_code
        route = getattr(request.scope.get("route"), "path", "unmatched")
        return response
    finally:
        telemetry.record_request(method, route, status, time.perf_counter() - started)


@app.get("/", include_in_schema=False)
async def introduction():
    return FileResponse(core.WEB / "intro.html", headers={"Cache-Control": "no-cache"})


@app.get("/console", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def console():
    return FileResponse(core.WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/{asset_name}", include_in_schema=False)
async def web_asset(asset_name: str):
    mime = {
        "app.css": "text/css; charset=utf-8",
        "app.js": "text/javascript; charset=utf-8",
        "intro.css": "text/css; charset=utf-8",
        "favicon.svg": "image/svg+xml",
        "demo-poster.svg": "image/svg+xml",
        "demo-captions.vtt": "text/vtt; charset=utf-8",
        "demo.webm": "video/webm",
    }.get(asset_name)
    if not mime:
        return JSONResponse({"error": {"code": "not_found", "message": "Page not found."}}, status_code=404)
    headers = {"Cache-Control": "public, max-age=3600"} if asset_name == "demo.webm" else {"Cache-Control": "no-cache"}
    return FileResponse(core.WEB / asset_name, media_type=mime, headers=headers)


@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "DELETE"])
async def versioned_api(path: str, request: Request):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > core.MAX_BODY:
                return JSONResponse({"error": {"code": "body_size", "message": "Request body must not exceed 64 KiB."}}, status_code=413)
        except ValueError:
            return JSONResponse({"error": {"code": "invalid_length", "message": "Invalid Content-Length."}}, status_code=400)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > core.MAX_BODY:
            return JSONResponse({"error": {"code": "body_size", "message": "Request body must not exceed 64 KiB."}}, status_code=413)

    def dispatch():
        handler = core.Handler.__new__(core.Handler)
        handler.path = request.url.path + ("?" + request.url.query if request.url.query else "")
        handler.command = request.method
        handler.headers = request.headers
        handler.client_address = (request.client.host if request.client else "127.0.0.1", 0)
        handler.rfile = BytesIO(body)
        captured = {}

        def send(status, data, extra=None, content_type="application/json; charset=utf-8", cache="no-store"):
            payload = data if isinstance(data, bytes) else core.dumps(data).encode()
            headers = {"Content-Type": content_type, "Cache-Control": cache}
            headers.update(extra or {})
            captured.update(status=status, body=payload, headers=headers)

        handler.send = send
        try:
            core.Handler.route(handler)
        except core.ApiError as error:
            send(error.status, {"error": {"code": error.code, "message": error.message}})
        except Exception:
            log.exception("Unhandled API failure", extra={"path": request.url.path})
            send(500, {"error": {"code": "internal_error", "message": "The request could not be completed."}})
        if not captured:
            send(404, {"error": {"code": "not_found", "message": "Route not found."}})
        return Response(content=captured["body"], status_code=captured["status"], headers=captured["headers"])

    return await run_in_threadpool(dispatch)


app.mount("/", StaticFiles(directory=str(core.WEB), html=True), name="console")
