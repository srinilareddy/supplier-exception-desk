import logging
import re
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from desk.api import router
from desk.config import Settings
from desk.db import make_session_factory
from desk.telemetry import event

REQUEST_ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,64}")


@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        yield
    finally:
        application.state.sessions.kw["bind"].dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(
        title="Supplier Exception Desk",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.sessions = make_session_factory(settings)

    @application.middleware("http")
    async def observe(request: Request, call_next):
        started = perf_counter()
        proposed_id = request.headers.get("x-request-id", "")
        request_id = (
            proposed_id if REQUEST_ID_PATTERN.fullmatch(proposed_id) else uuid4().hex
        )
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception as error:
            frame = traceback.extract_tb(error.__traceback__)[-1]
            event(
                "request_failed",
                level=logging.ERROR,
                request_id=request_id,
                error_type=type(error).__name__,
                location=f"{Path(frame.filename).name}:{frame.lineno}",
            )
            response = JSONResponse(
                {"detail": "The request could not be completed."}, status_code=500
            )
        else:
            outcome = getattr(request.state, "run_outcome", None)
            if outcome:
                event(
                    "ingestion_finished",
                    level=logging.WARNING
                    if outcome["status"] == "failed"
                    else logging.INFO,
                    request_id=request_id,
                    **outcome,
                )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            route = request.scope.get("route")
            event(
                "http_request",
                request_id=request_id,
                method=request.method,
                route=getattr(route, "path", "unmatched"),
                status=response.status_code,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_failed(_request: Request, error: RequestValidationError):
        issues = [
            {"location": list(problem["loc"]), "message": problem["msg"]}
            for problem in error.errors()
        ]
        return JSONResponse(
            {"detail": "Check the request fields.", "issues": issues}, status_code=422
        )

    @application.get("/api/health/live", tags=["Health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/health/ready", tags=["Health"])
    def ready(request: Request):
        try:
            with request.app.state.sessions() as db:
                db.execute(text("SELECT 1 FROM ingestion_runs LIMIT 1"))
        except SQLAlchemyError:
            event(
                "database_readiness_failed",
                level=logging.WARNING,
                request_id=request.state.request_id,
            )
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    application.include_router(router)
    if (settings.web_dist / "index.html").is_file():
        application.mount(
            "/assets",
            StaticFiles(directory=settings.web_dist / "assets"),
            name="assets",
        )

        @application.get("/", include_in_schema=False)
        def web():
            return FileResponse(
                settings.web_dist / "index.html", headers={"Cache-Control": "no-cache"}
            )

    return application


app = create_app()
