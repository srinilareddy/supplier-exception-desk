import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date

import httpx
from pydantic import ValidationError
from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from desk.config import Settings
from desk.models import IngestionRun, OrderLine, Shipment
from desk.schemas import CarrierEnvelope, Issue, OrderInput, ShipmentInput, Source

logger = logging.getLogger("desk.ingestion")
ORDER_COLUMNS = tuple(OrderInput.model_fields)
MAX_ROWS = 2_000
MAX_ORDER_BYTES = 1_048_576
MAX_CARRIER_BYTES = 2_097_152
MAX_ISSUES = 25
# Serialize intake transactions for this one team. The lock is released by PostgreSQL at commit.
INTAKE_LOCK = 1_593_002_611


class SourceProblem(ValueError):
    pass


@dataclass
class ParsedBatch[T]:
    rows: list[tuple[int, T]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.issues)


@dataclass
class RunCounter:
    added: int = 0
    updated: int = 0
    duplicates: int = 0


def field_error(error: ValidationError) -> str:
    first = error.errors(include_input=False, include_url=False)[0]
    field_name = ".".join(str(part) for part in first["loc"]) or "row"
    return f"{field_name}: {first['msg']}"


def parse_orders(raw: bytes) -> ParsedBatch[OrderInput]:
    if len(raw) > MAX_ORDER_BYTES:
        raise SourceProblem("CSV must be 1 MiB or smaller.")
    batch = ParsedBatch[OrderInput]()
    try:
        reader = csv.reader(
            io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True
        )
        if tuple(next(reader, ())) != ORDER_COLUMNS:
            raise SourceProblem("CSV columns must match the documented order template.")
        while True:
            row_number = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if not row:
                continue
            if batch.total == MAX_ROWS:
                raise SourceProblem(f"CSV is limited to {MAX_ROWS:,} data rows.")
            if len(row) != len(ORDER_COLUMNS):
                batch.issues.append(
                    Issue(row=row_number, reason="Wrong number of columns.")
                )
                continue
            data = dict(zip(ORDER_COLUMNS, row, strict=True))
            try:
                iso = data["promise_date"].strip()
                if date.fromisoformat(iso).isoformat() != iso:
                    raise ValueError
            except ValueError:
                batch.issues.append(
                    Issue(row=row_number, reason="promise_date: use YYYY-MM-DD.")
                )
                continue
            try:
                order = OrderInput.model_validate(data)
            except ValidationError as error:
                batch.issues.append(Issue(row=row_number, reason=field_error(error)))
            else:
                batch.rows.append((row_number, order))
    except UnicodeDecodeError as error:
        raise SourceProblem("CSV must be UTF-8 encoded.") from error
    except csv.Error as error:
        raise SourceProblem(
            f"Invalid CSV syntax near line {reader.line_num}."
        ) from error
    if not batch.total:
        raise SourceProblem("CSV contains no order lines.")
    return batch


def fetch_carrier(settings: Settings) -> ParsedBatch[ShipmentInput]:
    url = str(settings.carrier_url).rstrip("/") + "/v1/shipments"
    try:
        with httpx.Client(
            timeout=settings.carrier_timeout_seconds, trust_env=False
        ) as client:
            with client.stream(
                "GET", url, headers={"Accept": "application/json"}
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65_536):
                    if len(body) + len(chunk) > MAX_CARRIER_BYTES:
                        raise SourceProblem(
                            "Carrier response exceeded the allowed size."
                        )
                    body.extend(chunk)
    except httpx.HTTPStatusError as error:
        raise SourceProblem(
            f"Carrier returned HTTP {error.response.status_code}."
        ) from error
    except httpx.TimeoutException as error:
        raise SourceProblem("Carrier did not respond before the timeout.") from error
    except httpx.HTTPError as error:
        raise SourceProblem("Carrier could not be reached.") from error
    try:
        feed = CarrierEnvelope.model_validate_json(bytes(body))
    except ValidationError as error:
        raise SourceProblem(
            "Carrier response did not match feed schema version 1."
        ) from error
    batch = ParsedBatch[ShipmentInput]()
    for row, data in enumerate(feed.shipments, start=1):
        try:
            shipment = ShipmentInput.model_validate(data)
        except ValidationError as error:
            batch.issues.append(Issue(row=row, reason=field_error(error)))
        else:
            batch.rows.append((row, shipment))
    return batch


def finish_run(
    db: Session,
    source: Source,
    total: int,
    counts: RunCounter,
    issues: list[Issue],
    actor_id: int | None,
) -> IngestionRun:
    rejected = len(issues)
    status = (
        "failed"
        if rejected and rejected == total
        else "partial"
        if rejected
        else "success"
    )
    run = IngestionRun(
        source=source,
        status=status,
        actor_id=actor_id,
        total=total,
        added=counts.added,
        updated=counts.updated,
        duplicates=counts.duplicates,
        rejected=rejected,
        issues=[
            issue.model_dump()
            for issue in sorted(issues, key=lambda issue: issue.row or 0)[:MAX_ISSUES]
        ],
    )
    db.add(run)
    db.flush()
    return run


def record_failure(
    db: Session,
    source: Source,
    error: SourceProblem,
    actor_id: int | None,
) -> IngestionRun:
    run = IngestionRun(
        source=source,
        status="failed",
        actor_id=actor_id,
        issues=[Issue(reason=str(error)).model_dump()],
    )
    db.add(run)
    db.flush()
    return run


def _lock_intake(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INTAKE_LOCK})


def ingest_orders(
    db: Session,
    batch: ParsedBatch[OrderInput],
    actor_id: int | None,
) -> IngestionRun:
    _lock_intake(db)
    keys = {(item.order_number, item.line_number) for _, item in batch.rows}
    existing = {
        (item.order_number, item.line_number): item
        for item in db.scalars(
            select(OrderLine).where(
                tuple_(OrderLine.order_number, OrderLine.line_number).in_(keys)
            )
        )
    }
    counts = RunCounter()
    issues = list(batch.issues)
    for row, item in batch.rows:
        key = (item.order_number, item.line_number)
        data = item.model_dump()
        previous = existing.get(key)
        if previous is None:
            order = OrderLine(**data)
            db.add(order)
            existing[key] = order
            counts.added += 1
        elif all(getattr(previous, field) == value for field, value in data.items()):
            counts.duplicates += 1
        else:
            issues.append(
                Issue(row=row, reason="Order line exists with different values.")
            )
    return finish_run(db, "orders", batch.total, counts, issues, actor_id)


def ingest_shipments(
    db: Session,
    batch: ParsedBatch[ShipmentInput],
    actor_id: int | None,
) -> IngestionRun:
    _lock_intake(db)
    keys = {(item.order_number, item.line_number) for _, item in batch.rows}
    orders = {
        (order.order_number, order.line_number): order.id
        for order in db.scalars(
            select(OrderLine).where(
                tuple_(OrderLine.order_number, OrderLine.line_number).in_(keys)
            )
        )
    }
    existing = {
        item.shipment_id: item
        for item in db.scalars(
            select(Shipment).where(
                Shipment.shipment_id.in_(
                    {shipment.shipment_id for _, shipment in batch.rows}
                )
            )
        )
    }
    counts = RunCounter()
    issues = list(batch.issues)
    for row, item in batch.rows:
        order_id = orders.get((item.order_number, item.line_number))
        if order_id is None:
            issues.append(
                Issue(row=row, reason="Order line is unknown. Import orders and retry.")
            )
            continue
        previous = existing.get(item.shipment_id)
        data = item.model_dump(exclude={"order_number", "line_number"}) | {
            "order_line_id": order_id
        }
        if previous is None:
            shipment = Shipment(**data)
            db.add(shipment)
            existing[item.shipment_id] = shipment
            counts.added += 1
        elif previous.order_line_id != order_id:
            issues.append(
                Issue(
                    row=row,
                    reason="Shipment ID is already assigned to another order line.",
                )
            )
        elif all(getattr(previous, field) == value for field, value in data.items()):
            counts.duplicates += 1
        elif item.updated_at <= previous.updated_at:
            issues.append(
                Issue(
                    row=row,
                    reason="Shipment conflicts with a current or newer snapshot.",
                )
            )
        else:
            for field_name, value in data.items():
                setattr(previous, field_name, value)
            counts.updated += 1
    return finish_run(db, "carrier", batch.total, counts, issues, actor_id)
