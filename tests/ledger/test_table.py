"""LEDG-01: the typed columns agree with payload_canonical; the column types are strict."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from calledit_data.db.schema import predictions
from nowcaster.ledger.canonical import format_money, format_ts
from nowcaster.ledger.chain import append_record

from tests.ledger.helpers import T0, append_rules, prediction_builder


def _row(engine: sa.Engine, seq: int) -> sa.Row:
    with engine.connect() as conn:
        return conn.execute(sa.select(predictions).where(predictions.c.seq == seq)).one()


def test_rules_record_typed_columns_equal_payload(migrated_sqlite: sa.Engine) -> None:
    (record,) = append_rules(migrated_sqlite, 1)
    row = _row(migrated_sqlite, 0)
    payload = json.loads(row.payload_canonical)
    assert row.payload_canonical == record.payload_canonical
    assert row.record_kind == payload["record_kind"] == "rules"
    assert row.created_at.tzinfo is not None and row.created_at.utcoffset().total_seconds() == 0
    assert format_ts(row.created_at) == payload["recorded_at"]
    assert row.hash == record.hash and row.prev_hash == payload["prev_hash"]
    for column in (
        "ticker",
        "fiscal_quarter",
        "model_version",
        "predicted_revenue_cr",
        "low_cr",
        "high_cr",
        "baseline_cr",
        "feature_snapshot",
    ):
        assert getattr(row, column) is None, column


def test_prediction_typed_columns_equal_payload(migrated_sqlite: sa.Engine) -> None:
    append_rules(migrated_sqlite, 1)
    append_record(migrated_sqlite, prediction_builder({"quarters": ["Q3FY26"]}))
    row = _row(migrated_sqlite, 1)
    payload = json.loads(row.payload_canonical)
    assert row.record_kind == payload["record_kind"] == "prediction"
    assert row.ticker == payload["ticker"]
    assert row.fiscal_quarter == payload["fiscal_quarter"]
    assert row.model_version == payload["model_version"]
    assert isinstance(row.predicted_revenue_cr, Decimal)
    assert format_money(row.predicted_revenue_cr) == payload["point_inr_cr"]
    assert format_money(row.baseline_cr) == payload["baseline_inr_cr"]
    assert row.low_cr is None and payload["lo80_inr_cr"] == "none"
    assert format_ts(row.created_at) == payload["locked_at"]


def _insert(engine: sa.Engine, **overrides: object) -> None:
    values = {
        "seq": 0,
        "record_kind": "rules",
        "created_at": T0,
        "payload_canonical": "{}",
        "hash": "a" * 64,
        "prev_hash": "0" * 64,
    }
    values.update(overrides)
    with engine.begin() as conn:
        conn.execute(sa.insert(predictions).values(**values))


def test_naive_created_at_is_rejected(migrated_sqlite: sa.Engine) -> None:
    with pytest.raises(sa.exc.StatementError, match="naive"):
        _insert(migrated_sqlite, created_at=datetime(2026, 11, 28, 6, 0, 0))


def test_float_money_is_rejected(migrated_sqlite: sa.Engine) -> None:
    with pytest.raises(sa.exc.StatementError, match="Decimal"):
        _insert(migrated_sqlite, baseline_cr=18123.45)


def test_decimal_money_round_trips_quantised(migrated_sqlite: sa.Engine) -> None:
    ist_instant = datetime(2026, 11, 28, 11, 30, 0, tzinfo=UTC)
    _insert(migrated_sqlite, baseline_cr=Decimal("18123.455"), created_at=ist_instant)
    row = _row(migrated_sqlite, 0)
    assert row.baseline_cr == Decimal("18123.46")
    assert str(row.baseline_cr) == "18123.46"
    assert row.created_at == ist_instant
    with migrated_sqlite.connect() as conn:
        stored = conn.exec_driver_sql(
            "SELECT baseline_cr, created_at FROM predictions WHERE seq = 0"
        ).one()
    assert stored == ("18123.46", "2026-11-28T11:30:00.000000Z")
