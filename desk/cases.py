from datetime import UTC, date, datetime
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from desk.models import (
    CaseEvent,
    ExceptionCase,
    IngestionRun,
    OrderLine,
    Shipment,
    User,
)
from desk.schemas import (
    CaseChange,
    CaseDetail,
    CasePage,
    CaseSignal,
    CaseStatus,
    CaseSummary,
    EventView,
    Overview,
    Severity,
    ShipmentView,
)


class Finding(NamedTuple):
    signal: CaseSignal
    severity: Severity


def assess(promise_date: date, ordered: int, delivered: int, as_of: date) -> Finding:
    days_late = (as_of - promise_date).days
    if days_late <= 0 or delivered >= ordered:
        return Finding("cleared", "normal")
    severity: Severity = (
        "critical" if days_late >= 7 else "high" if days_late >= 3 else "normal"
    )
    return Finding("short_shipment" if delivered else "overdue", severity)


def add_event(
    db: Session,
    item: ExceptionCase,
    action: str,
    note: str,
    previous_status: str | None,
    actor_id: int | None = None,
) -> None:
    db.add(
        CaseEvent(
            case_id=item.id,
            actor_id=actor_id,
            action=action,
            previous_status=previous_status,
            next_status=item.status,
            note=note,
        )
    )


def reconcile(db: Session, as_of: date) -> None:
    deliveries = (
        select(Shipment.order_line_id, func.sum(Shipment.quantity).label("delivered"))
        .where(Shipment.status == "delivered")
        .group_by(Shipment.order_line_id)
        .subquery()
    )
    orders = db.execute(
        select(OrderLine, func.coalesce(deliveries.c.delivered, 0))
        .outerjoin(deliveries, OrderLine.id == deliveries.c.order_line_id)
        .order_by(OrderLine.id)
    )
    existing = {
        item.order_line_id: item
        for item in db.scalars(
            select(ExceptionCase).order_by(ExceptionCase.id).with_for_update()
        )
    }
    for order, delivered in orders:
        signal, severity = assess(order.promise_date, order.quantity, delivered, as_of)
        item = existing.get(order.id)
        if item is None:
            if signal == "cleared":
                continue
            item = ExceptionCase(
                order_line_id=order.id,
                signal=signal,
                severity=severity,
                status="open",
                delivered_quantity=delivered,
            )
            db.add(item)
            db.flush()
            add_event(
                db,
                item,
                "detected",
                f"{delivered} of {order.quantity} units delivered.",
                None,
            )
            continue
        if (item.signal, item.severity, item.delivered_quantity) == (
            signal,
            severity,
            delivered,
        ):
            continue
        previous_status = item.status
        reopen = (
            previous_status == "resolved"
            and item.signal == "cleared"
            and signal != "cleared"
        )
        item.signal = signal
        item.severity = severity
        item.delivered_quantity = delivered
        item.version += 1
        item.updated_at = datetime.now(UTC)
        if reopen:
            item.status = "open"
        add_event(
            db,
            item,
            "reopened" if reopen else "evidence_updated",
            f"{delivered} of {order.quantity} units delivered. Signal is {signal.replace('_', ' ')}.",
            previous_status,
        )


def as_summary(
    item: ExceptionCase, order: OrderLine, assignee: str | None
) -> CaseSummary:
    return CaseSummary(
        id=item.id,
        order_number=order.order_number,
        line_number=order.line_number,
        supplier=order.supplier,
        sku=order.sku,
        description=order.description,
        promise_date=order.promise_date,
        ordered_quantity=order.quantity,
        delivered_quantity=item.delivered_quantity,
        status=item.status,
        signal=item.signal,
        severity=item.severity,
        assigned_to_id=item.assigned_to_id,
        assigned_to_name=assignee,
        version=item.version,
        updated_at=item.updated_at,
    )


def case_query():
    return (
        select(ExceptionCase, OrderLine, User.name)
        .join(OrderLine, OrderLine.id == ExceptionCase.order_line_id)
        .outerjoin(User, User.id == ExceptionCase.assigned_to_id)
    )


def list_cases(
    db: Session,
    status: CaseStatus | str,
    severity: Severity | None,
    supplier: str | None,
    signal: CaseSignal | None,
    search: str | None,
    limit: int,
    offset: int,
) -> CasePage:
    query = case_query()
    if status == "active":
        query = query.where(ExceptionCase.status != "resolved")
    elif status != "all":
        query = query.where(ExceptionCase.status == status)
    if severity:
        query = query.where(ExceptionCase.severity == severity)
    if supplier:
        query = query.where(OrderLine.supplier == supplier)
    if signal:
        query = query.where(ExceptionCase.signal == signal)
    if search:
        query = query.where(
            or_(
                OrderLine.order_number.icontains(search, autoescape=True),
                OrderLine.sku.icontains(search, autoescape=True),
                OrderLine.supplier.icontains(search, autoescape=True),
                OrderLine.description.icontains(search, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    priority = case({"critical": 0, "high": 1}, value=ExceptionCase.severity, else_=2)
    rows = db.execute(
        query.order_by(priority, OrderLine.promise_date, ExceptionCase.id)
        .limit(limit)
        .offset(offset)
    )
    return CasePage(items=[as_summary(*row) for row in rows], total=total)


def detail(db: Session, case_id: int) -> CaseDetail:
    row = db.execute(case_query().where(ExceptionCase.id == case_id)).one_or_none()
    if row is None:
        raise HTTPException(404, "Exception not found.")
    summary = as_summary(*row)
    item = row[0]
    shipments = db.scalars(
        select(Shipment)
        .where(Shipment.order_line_id == item.order_line_id)
        .order_by(Shipment.updated_at.desc(), Shipment.shipment_id)
    )
    events = db.execute(
        select(CaseEvent, User.name)
        .outerjoin(User, User.id == CaseEvent.actor_id)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.id.desc())
    )
    return CaseDetail(
        **summary.model_dump(),
        shipments=[ShipmentView.model_validate(shipment) for shipment in shipments],
        events=[
            EventView(
                id=event.id,
                action=event.action,
                actor_name=name,
                previous_status=event.previous_status,
                next_status=event.next_status,
                note=event.note,
                created_at=event.created_at,
            )
            for event, name in events
        ],
    )


def change_case(
    db: Session, case_id: int, change: CaseChange, actor: User
) -> CaseDetail:
    item = db.scalar(
        select(ExceptionCase).where(ExceptionCase.id == case_id).with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Exception not found.")
    if item.version != change.version:
        raise HTTPException(
            409, "This exception changed. Refresh its details and retry."
        )
    previous = item.status
    if previous == "resolved":
        raise HTTPException(409, "The exception is already resolved.")
    match change.action:
        case "assign":
            operator = db.get(User, change.assigned_to_id)
            if operator is None or operator.role != "operator":
                raise HTTPException(422, "Choose a valid operator.")
            if operator.id == item.assigned_to_id:
                return detail(db, case_id)
            item.assigned_to_id = operator.id
            note = f"Assigned to {operator.name}."
        case "acknowledge":
            if previous != "open":
                raise HTTPException(409, "Only an open exception can be acknowledged.")
            item.status = "acknowledged"
            note = "Acknowledged the exception."
        case "resolve":
            item.status = "resolved"
            note = change.reason or ""
    item.version += 1
    item.updated_at = datetime.now(UTC)
    add_event(db, item, change.action, note, previous, actor.id)
    return detail(db, case_id)


def overview(db: Session, as_of: date) -> Overview:
    active = ExceptionCase.status != "resolved"
    active_count, critical, resolved, suppliers_affected = db.execute(
        select(
            func.count().filter(active),
            func.count().filter(active, ExceptionCase.severity == "critical"),
            func.count().filter(ExceptionCase.status == "resolved"),
            func.count(func.distinct(OrderLine.supplier)).filter(active),
        )
        .select_from(ExceptionCase)
        .join(OrderLine, OrderLine.id == ExceptionCase.order_line_id)
    ).one()
    return Overview(
        as_of_date=as_of,
        active_cases=active_count,
        critical_cases=critical,
        affected_suppliers=suppliers_affected,
        resolved_cases=resolved,
        order_lines=db.scalar(select(func.count()).select_from(OrderLine)) or 0,
        shipments=db.scalar(select(func.count()).select_from(Shipment)) or 0,
        suppliers=list(
            db.scalars(
                select(OrderLine.supplier).distinct().order_by(OrderLine.supplier)
            )
        ),
        latest_orders=db.scalar(
            select(IngestionRun)
            .where(IngestionRun.source == "orders")
            .order_by(IngestionRun.id.desc())
            .limit(1)
        ),
        latest_carrier=db.scalar(
            select(IngestionRun)
            .where(IngestionRun.source == "carrier")
            .order_by(IngestionRun.id.desc())
            .limit(1)
        ),
        orders_last_available_at=db.scalar(
            select(func.max(IngestionRun.created_at)).where(
                IngestionRun.source == "orders", IngestionRun.status != "failed"
            )
        ),
        carrier_last_available_at=db.scalar(
            select(func.max(IngestionRun.created_at)).where(
                IngestionRun.source == "carrier", IngestionRun.status != "failed"
            )
        ),
    )
