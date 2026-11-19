from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

type Role = Literal["operator", "viewer"]
type CaseStatus = Literal["open", "acknowledged", "resolved"]
type CaseSignal = Literal["overdue", "short_shipment", "cleared"]
type Severity = Literal["critical", "high", "normal"]
type ShipmentStatus = Literal["label_created", "in_transit", "delivered"]
type Source = Literal["orders", "carrier"]
type SourceKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9._-]*$"),
]
type Quantity = Annotated[int, Field(gt=0, le=10_000_000)]
type LineNumber = Annotated[int, Field(gt=0, le=100_000)]


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class OrderInput(InputModel):
    order_number: SourceKey
    line_number: LineNumber
    supplier: str = Field(min_length=1, max_length=100)
    sku: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=160)
    quantity: Quantity
    promise_date: date


class ShipmentInput(InputModel):
    shipment_id: SourceKey
    order_number: SourceKey
    line_number: LineNumber
    quantity: Quantity
    status: ShipmentStatus
    carrier: str = Field(min_length=1, max_length=60)
    updated_at: AwareDatetime


class CarrierEnvelope(InputModel):
    schema_version: Literal[1]
    shipments: list[object] = Field(max_length=2000)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128, repr=False)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    role: Role


class SessionView(BaseModel):
    user: UserView
    csrf_token: str


class CaseChange(InputModel):
    action: Literal["assign", "acknowledge", "resolve"]
    version: int = Field(ge=1)
    assigned_to_id: int | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def action_parameters(self) -> Self:
        if self.action == "assign" and self.assigned_to_id is None:
            raise ValueError("Assignment requires an operator.")
        if self.action != "assign" and self.assigned_to_id is not None:
            raise ValueError("Only assignment accepts an operator.")
        if self.action == "resolve" and not self.reason:
            raise ValueError("Resolution requires a reason.")
        if self.action != "resolve" and self.reason is not None:
            raise ValueError("Only resolution accepts a reason.")
        return self


class Issue(InputModel):
    row: int | None = None
    reason: str


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: Source
    status: Literal["success", "partial", "failed"]
    total: int
    added: int
    updated: int
    duplicates: int
    rejected: int
    issues: list[Issue]
    created_at: datetime


class CaseSummary(BaseModel):
    id: int
    order_number: str
    line_number: int
    supplier: str
    sku: str
    description: str
    promise_date: date
    ordered_quantity: int
    delivered_quantity: int
    status: CaseStatus
    signal: CaseSignal
    severity: Severity
    assigned_to_id: int | None
    assigned_to_name: str | None
    version: int
    updated_at: datetime


class ShipmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    shipment_id: str
    carrier: str
    quantity: int
    status: ShipmentStatus
    updated_at: datetime


class EventView(BaseModel):
    id: int
    action: str
    actor_name: str | None
    previous_status: CaseStatus | None
    next_status: CaseStatus
    note: str
    created_at: datetime


class CaseDetail(CaseSummary):
    shipments: list[ShipmentView]
    events: list[EventView]


class CasePage(BaseModel):
    items: list[CaseSummary]
    total: int


class Overview(BaseModel):
    as_of_date: date
    active_cases: int
    critical_cases: int
    affected_suppliers: int
    resolved_cases: int
    order_lines: int
    shipments: int
    suppliers: list[str]
    latest_orders: RunView | None
    latest_carrier: RunView | None
    orders_last_available_at: datetime | None
    carrier_last_available_at: datetime | None
