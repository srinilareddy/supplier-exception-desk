from datetime import date

import pytest

from desk.cases import assess
from desk.ingestion import ORDER_COLUMNS, SourceProblem, parse_orders

AS_OF = date(2026, 11, 19)
HEADER = ",".join(ORDER_COLUMNS).encode()


@pytest.mark.parametrize(
    ("promise_date", "delivered", "signal", "severity"),
    [
        (date(2026, 11, 19), 0, "cleared", "normal"),
        (date(2026, 11, 12), 0, "overdue", "critical"),
        (date(2026, 11, 16), 4, "short_shipment", "high"),
        (date(2026, 11, 18), 0, "overdue", "normal"),
        (date(2026, 11, 18), 10, "cleared", "normal"),
    ],
)
def test_exception_priority(promise_date, delivered, signal, severity):
    assert assess(promise_date, 10, delivered, AS_OF) == (signal, severity)


def test_parser_reports_physical_lines_and_excludes_bad_dates():
    batch = parse_orders(
        HEADER
        + b'\nPO-1,1,Vendor,ITEM,"Two\nlines",10,2026-11-02\n'
        + b"PO-2,1,Vendor,ITEM,Description,10,11/02/26\n"
        + b"PO-3,1,Vendor,ITEM,Description,-1,2026-11-01\n"
    )
    assert len(batch.rows) == 1 and batch.rows[0][0] == 2
    assert batch.total == 3
    assert [issue.row for issue in batch.issues] == [4, 5]
    assert "YYYY-MM-DD" in batch.issues[0].reason


@pytest.mark.parametrize(
    "raw", [b"unknown,header\n", HEADER + b"\n", b"\xff", HEADER + b'\n"broken']
)
def test_parser_rejects_unreadable_files(raw):
    with pytest.raises(SourceProblem):
        parse_orders(raw)
