"""The localhost HTTP layer.

Security posture, because this server can place orders:

* It binds to 127.0.0.1 by default. Nothing outside the machine can reach it.
* Every request must carry a per-run token, handed to the browser once in the
  launch URL and then sent as a header. Custom headers cannot be set by a
  cross-origin page without a CORS preflight, which is never granted, so a
  random website you happen to have open cannot drive this API.
* The Host header is checked against a loopback allowlist, which is what stops
  DNS rebinding -- an attacker's domain resolving to 127.0.0.1 still arrives
  with the wrong Host.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..brokers.base import BrokerError
from .service import MIN_LOOP_INTERVAL, TradingService

log = logging.getLogger(__name__)

DEFAULT_PORT = 8787
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "[::1]", "::1"}


def _hostname_allowed(request: Request) -> bool:
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    return host in {h.strip("[]") for h in ALLOWED_HOSTNAMES}


def create_app(service: TradingService, token: str) -> FastAPI:
    app = FastAPI(title="autotrader", docs_url=None, redoc_url=None)
    app.state.service = service
    app.state.token = token

    def authorize(request: Request) -> None:
        if not _hostname_allowed(request):
            raise HTTPException(status_code=403, detail="unexpected Host header")
        supplied = request.headers.get("x-auth-token") or request.query_params.get("t")
        if not supplied or not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="bad or missing token")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        # The page itself is not secret; the token in its query string is what
        # unlocks the API, and the page reads it from the URL.
        if not _hostname_allowed(request):
            raise HTTPException(status_code=403, detail="unexpected Host header")
        return HTMLResponse((STATIC_DIR / "index.html").read_text())

    @app.get("/api/state")
    def state(request: Request) -> JSONResponse:
        authorize(request)
        try:
            return JSONResponse(service.snapshot())
        except BrokerError as exc:
            return JSONResponse({"errors": [str(exc)]}, status_code=502)

    @app.post("/api/run")
    def run(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
        authorize(request)
        try:
            result = service.run_once(
                dry_run=bool(payload.get("dry_run", True)),
                ignore_market_hours=bool(payload.get("ignore_market_hours", False)),
            )
        except BrokerError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        return JSONResponse(result)

    @app.post("/api/flatten")
    def flatten(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
        authorize(request)
        try:
            result = service.flatten(dry_run=bool(payload.get("dry_run", False)))
        except BrokerError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        return JSONResponse(result)

    @app.post("/api/loop")
    def loop(request: Request, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
        authorize(request)
        action = str(payload.get("action", "")).lower()
        if action == "start":
            status = service.start_loop(
                interval=int(payload.get("interval", service.loop.interval)),
                dry_run=bool(payload.get("dry_run", False)),
            )
        elif action == "stop":
            status = service.stop_loop()
        else:
            raise HTTPException(status_code=400, detail="action must be start or stop")
        return JSONResponse(status.as_dict())

    @app.get("/api/limits")
    def limits(request: Request) -> JSONResponse:
        authorize(request)
        return JSONResponse({"min_loop_interval": MIN_LOOP_INTERVAL})

    return app


def serve(
    service: TradingService,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    token: str | None = None,
) -> None:
    """Run the dashboard until interrupted."""
    import uvicorn

    token = token or secrets.token_urlsafe(24)
    app = create_app(service, token)
    url = f"http://{host}:{port}/?t={token}"

    print()
    print("  autotrader dashboard")
    print(f"  {url}")
    print()
    print("  Keep this terminal open. Ctrl-C stops the server -- and any")
    print("  trading loop started from the dashboard stops with it.")
    print()

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        server.run()
    finally:
        service.shutdown()
