"""LEDG-03: hash chaining and fork rejection, in the app and at the DB."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from nowcaster.ledger.canonical import GENESIS_PREV_HASH, sha256_hex
from nowcaster.ledger.chain import ForkError, RecordError, append_record, read_head

from tests.ledger.helpers import append_rules, raw_insert, rules_builder, stale_builder

DB_REFUSAL = "append-only|UNIQUE"


def _count(engine: sa.Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT COUNT(*) FROM predictions")).scalar_one()


def test_sequential_appends_link(migrated_sqlite: sa.Engine) -> None:
    records = append_rules(migrated_sqlite, 3)
    assert [r.seq for r in records] == [0, 1, 2]
    assert records[0].prev_hash == GENESIS_PREV_HASH
    assert records[1].prev_hash == records[0].hash
    assert records[2].prev_hash == records[1].hash
    for record in records:
        assert sha256_hex(record.payload_canonical) == record.hash
        payload = json.loads(record.payload_canonical)
        assert payload["prev_hash"] == record.prev_hash
        assert payload["seq"] == str(record.seq)
    with migrated_sqlite.connect() as conn:
        head = read_head(conn)
    assert head is not None and (head.seq, head.hash) == (2, records[2].hash)


def test_empty_chain_has_no_head(migrated_sqlite: sa.Engine) -> None:
    with migrated_sqlite.connect() as conn:
        assert read_head(conn) is None


def test_stale_prev_hash_raises_fork_error(migrated_sqlite: sa.Engine) -> None:
    first, _second = append_rules(migrated_sqlite, 2)
    with pytest.raises(ForkError, match="seq 2"):
        append_record(migrated_sqlite, stale_builder(rules_builder(note="fork"), first.hash))
    assert _count(migrated_sqlite) == 2


def test_zero_prev_hash_on_non_empty_chain_is_refused(migrated_sqlite: sa.Engine) -> None:
    append_rules(migrated_sqlite, 1)
    with pytest.raises(ForkError):
        append_record(
            migrated_sqlite, stale_builder(rules_builder(note="regenesis"), GENESIS_PREV_HASH)
        )
    assert _count(migrated_sqlite) == 1


def test_builder_with_wrong_seq_is_refused(migrated_sqlite: sa.Engine) -> None:
    append_rules(migrated_sqlite, 1)
    build = rules_builder(note="wrong-seq")

    def wrong_seq(seq: int, prev_hash: str):
        return build(seq + 5, prev_hash)

    with pytest.raises(RecordError):
        append_record(migrated_sqlite, wrong_seq)
    assert _count(migrated_sqlite) == 1


def test_raw_second_child_fails_at_the_db(migrated_sqlite: sa.Engine) -> None:
    first, _second = append_rules(migrated_sqlite, 2)
    with pytest.raises(sa.exc.DBAPIError, match=DB_REFUSAL), migrated_sqlite.begin() as conn:
        raw_insert(conn, seq=2, hash_="c" * 64, prev_hash=first.hash)
    assert _count(migrated_sqlite) == 2


def test_raw_zero_prev_hash_on_non_empty_chain_fails_at_the_db(
    migrated_sqlite: sa.Engine,
) -> None:
    append_rules(migrated_sqlite, 1)
    with pytest.raises(sa.exc.DBAPIError, match=DB_REFUSAL), migrated_sqlite.begin() as conn:
        raw_insert(conn, seq=1, hash_="d" * 64, prev_hash=GENESIS_PREV_HASH)
    assert _count(migrated_sqlite) == 1


def test_two_inserts_racing_for_the_same_seq(migrated_sqlite: sa.Engine) -> None:
    (genesis,) = append_rules(migrated_sqlite, 1)
    with migrated_sqlite.begin() as conn:
        raw_insert(conn, seq=1, hash_="e" * 64, prev_hash=genesis.hash)
    with pytest.raises(sa.exc.DBAPIError, match=DB_REFUSAL), migrated_sqlite.begin() as conn:
        raw_insert(conn, seq=1, hash_="f" * 64, prev_hash="1" * 64)
    assert _count(migrated_sqlite) == 2
