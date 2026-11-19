import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, NamedTuple
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from desk import cases, ingestion
from desk.models import IngestionRun, LoginSession, User
from desk.schemas import (
    CaseChange,
    CaseDetail,
    CasePage,
    CaseSignal,
    CaseStatus,
    LoginInput,
    Overview,
    RunView,
    SessionView,
    Severity,
    UserView,
)
from desk.security import hash_password, verify_password

router = APIRouter(prefix="/api")
COOKIE_NAME = "desk_session"
session_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False)
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def database(request: Request):
    # Function scope commits before the client receives the response.
    with request.app.state.sessions.begin() as db:
        yield db


type Database = Annotated[Session, Depends(database, scope="function")]


class Auth(NamedTuple):
    user: User
    token: str


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_for(token: str) -> str:
    return hmac.new(token.encode(), b"supplier-desk-csrf", hashlib.sha256).hexdigest()


def session_view(auth: Auth) -> SessionView:
    return SessionView(
        user=UserView.model_validate(auth.user), csrf_token=csrf_for(auth.token)
    )


def current_session(
    db: Database,
    token: Annotated[str | None, Depends(session_cookie)],
) -> Auth:
    if token is None or len(token) != 43:
        raise HTTPException(401, "Sign in to continue.")
    entry = db.get(LoginSession, token_digest(token))
    if entry is None or entry.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "Your session has expired. Sign in again.")
    user = db.get(User, entry.user_id)
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return Auth(user, token)


type SignedIn = Annotated[Auth, Depends(current_session)]


def protected_write(
    auth: SignedIn,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Auth:
    if csrf_token is None or not hmac.compare_digest(
        csrf_for(auth.token).encode(), csrf_token.encode()
    ):
        raise HTTPException(403, "A valid CSRF token is required.")
    return auth


def operator(auth: Annotated[Auth, Depends(protected_write)]) -> Auth:
    if auth.user.role != "operator":
        raise HTTPException(403, "Only operators can make this change.")
    return auth


type Operator = Annotated[Auth, Depends(operator)]


@router.post("/session", tags=["Session"])
def login(
    body: LoginInput, request: Request, response: Response, db: Database
) -> SessionView:
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Sign in from the application origin.")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if (
        not verify_password(user.password_hash if user else DUMMY_HASH, body.password)
        or user is None
    ):
        raise HTTPException(401, "Email or password was incorrect.")
    now = datetime.now(UTC)
    settings = request.app.state.settings
    duration = timedelta(hours=settings.session_hours)
    previous_token = request.cookies.get(COOKIE_NAME)
    if previous_token and len(previous_token) == 43:
        db.execute(
            delete(LoginSession).where(
                LoginSession.token_hash == token_digest(previous_token)
            )
        )
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=token_digest(token), user_id=user.id, expires_at=now + duration
        )
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(duration.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return session_view(Auth(user, token))


@router.get("/session", tags=["Session"])
def session(auth: SignedIn) -> SessionView:
    return session_view(auth)


@router.delete("/session", status_code=204, tags=["Session"])
def logout(
    request: Request, db: Database, auth: Annotated[Auth, Depends(protected_write)]
) -> Response:
    db.execute(
        delete(LoginSession).where(LoginSession.token_hash == token_digest(auth.token))
    )
    response = Response(status_code=204)
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.cookie_secure,
    )
    return response


@router.get("/overview", tags=["Exceptions"])
def summary(request: Request, db: Database, _auth: SignedIn) -> Overview:
    return cases.overview(db, request.app.state.settings.business_date())


@router.get("/exceptions", tags=["Exceptions"])
def exceptions(
    db: Database,
    _auth: SignedIn,
    status: CaseStatus | Literal["active", "all"] = "active",
    severity: Severity | None = None,
    supplier: Annotated[str | None, Query(max_length=100)] = None,
    signal: CaseSignal | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CasePage:
    return cases.list_cases(db, status, severity, supplier, signal, q, limit, offset)


@router.get("/exceptions/{case_id}", tags=["Exceptions"])
def exception_detail(case_id: int, db: Database, _auth: SignedIn) -> CaseDetail:
    return cases.detail(db, case_id)


@router.patch("/exceptions/{case_id}", tags=["Exceptions"])
def update_exception(
    case_id: int, body: CaseChange, db: Database, auth: Operator
) -> CaseDetail:
    return cases.change_case(db, case_id, body, auth.user)


@router.get("/operators", tags=["Exceptions"])
def operators(db: Database, _auth: SignedIn) -> list[UserView]:
    return [
        UserView.model_validate(user)
        for user in db.scalars(
            select(User).where(User.role == "operator").order_by(User.name)
        )
    ]


@router.get("/runs", tags=["Intake"])
def runs(
    db: Database,
    _auth: SignedIn,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RunView]:
    return [
        RunView.model_validate(run)
        for run in db.scalars(
            select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit)
        )
    ]


@router.get("/imports/orders/template", tags=["Intake"], response_class=Response)
def order_template(_auth: SignedIn) -> Response:
    return Response(
        ",".join(ingestion.ORDER_COLUMNS) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="order-template.csv"'},
    )


async def csv_body(request: Request, _auth: Operator) -> bytes:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "text/csv"
    ):
        raise HTTPException(415, "Send the file with Content-Type text/csv.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > ingestion.MAX_ORDER_BYTES:
            raise HTTPException(413, "CSV must be 1 MiB or smaller.")
        body.extend(chunk)
    return bytes(body)


def report_run(run: IngestionRun, request: Request, *, status_code: int | None = None):
    request.state.run_outcome = {
        "actor_id": run.actor_id,
        "run_id": run.id,
        "source": run.source,
        "status": run.status,
        "added": run.added,
        "updated": run.updated,
        "duplicates": run.duplicates,
        "rejected": run.rejected,
    }
    summary = RunView.model_validate(run)
    if status_code:
        return JSONResponse(summary.model_dump(mode="json"), status_code=status_code)
    return summary


@router.post(
    "/imports/orders",
    tags=["Intake"],
    response_model=RunView,
    responses={422: {"model": RunView, "description": "CSV format error recorded"}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def import_orders(
    request: Request,
    db: Database,
    auth: Operator,
    raw: Annotated[bytes, Depends(csv_body)],
):
    try:
        batch = ingestion.parse_orders(raw)
    except ingestion.SourceProblem as error:
        run = ingestion.record_failure(db, "orders", error, auth.user.id)
        return report_run(run, request, status_code=422)
    run = ingestion.ingest_orders(db, batch, auth.user.id)
    if run.status != "failed":
        cases.reconcile(db, request.app.state.settings.business_date())
    return report_run(run, request)


@router.post(
    "/sync/carrier",
    tags=["Intake"],
    response_model=RunView,
    responses={502: {"model": RunView, "description": "Upstream failure recorded"}},
)
def sync_carrier(request: Request, db: Database, auth: Operator):
    settings = request.app.state.settings
    try:
        batch = ingestion.fetch_carrier(settings)
    except ingestion.SourceProblem as error:
        run = ingestion.record_failure(db, "carrier", error, auth.user.id)
        return report_run(run, request, status_code=502)
    run = ingestion.ingest_shipments(db, batch, auth.user.id)
    if run.status != "failed":
        cases.reconcile(db, settings.business_date())
    return report_run(run, request)
