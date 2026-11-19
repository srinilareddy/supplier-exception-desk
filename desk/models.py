from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from desk.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('operator', 'viewer')", name="user_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str]


class LoginSession(Base):
    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_number", "line_number", name="order_line_source_key"),
        CheckConstraint("line_number > 0 AND quantity > 0", name="positive_order_line"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32))
    line_number: Mapped[int]
    supplier: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int]
    promise_date: Mapped[date] = mapped_column(index=True)


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_shipment_quantity"),
        CheckConstraint(
            "status IN ('label_created', 'in_transit', 'delivered')",
            name="shipment_status",
        ),
    )

    shipment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_line_id: Mapped[int] = mapped_column(ForeignKey("order_lines.id"), index=True)
    quantity: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    carrier: Mapped[str] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExceptionCase(Base):
    __tablename__ = "exception_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')", name="case_status"
        ),
        CheckConstraint(
            "signal IN ('overdue', 'short_shipment', 'cleared')", name="case_signal"
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'normal')", name="case_severity"
        ),
        CheckConstraint(
            "version > 0 AND delivered_quantity >= 0", name="valid_case_counters"
        ),
        Index("ix_case_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_line_id: Mapped[int] = mapped_column(
        ForeignKey("order_lines.id"), unique=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16))
    signal: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    delivered_quantity: Mapped[int]
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("exception_cases.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    previous_status: Mapped[str | None] = mapped_column(String(16))
    next_status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("source IN ('orders', 'carrier')", name="ingestion_source"),
        CheckConstraint(
            "status IN ('success', 'partial', 'failed')", name="ingestion_status"
        ),
        Index("ix_ingestion_source_id", "source", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total: Mapped[int] = mapped_column(default=0)
    added: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    duplicates: Mapped[int] = mapped_column(default=0)
    rejected: Mapped[int] = mapped_column(default=0)
    issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
