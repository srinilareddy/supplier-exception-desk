from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from desk.cases import reconcile
from desk.config import Settings
from desk.db import make_session_factory
from desk.ingestion import fetch_carrier, ingest_orders, ingest_shipments, parse_orders
from desk.models import User
from desk.security import hash_password

DEMO_ACCOUNTS = (
    ("buyer@example.test", "Maya Chen", "operator"),
    ("supervisor@example.test", "Jordan Avery", "operator"),
    ("viewer@example.test", "Riley Brooks", "viewer"),
)


def seed_accounts(db: Session, password: str) -> None:
    for email, name, role in DEMO_ACCOUNTS:
        statement = insert(User).values(
            email=email,
            name=name,
            role=role,
            password_hash=hash_password(password),
        )
        db.execute(statement.on_conflict_do_nothing(index_elements=[User.email]))


def main() -> None:
    settings = Settings()
    if settings.demo_password is None:
        raise SystemExit("Set DESK_DEMO_PASSWORD before loading the synthetic demo.")
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "orders.csv"
    orders = parse_orders(fixture.read_bytes())
    shipments = fetch_carrier(settings)
    with make_session_factory(settings).begin() as db:
        seed_accounts(db, settings.demo_password.get_secret_value())
        order_run = ingest_orders(db, orders, None)
        shipment_run = ingest_shipments(db, shipments, None)
        if order_run.rejected or shipment_run.rejected:
            raise SystemExit(
                "Demo import failed. Existing data might conflict with these fixtures."
            )
        reconcile(db, settings.business_date())
    print(
        f"Demo ready. Added {order_run.added} order lines and {shipment_run.added} shipments."
    )


if __name__ == "__main__":
    main()
