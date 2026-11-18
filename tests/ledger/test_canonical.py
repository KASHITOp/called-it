"""LEDG-02: calledit-ledger-v1 golden vectors, shared with web/tests/canonical.test.ts."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from nowcaster.ledger import canonical
from nowcaster.ledger.canonical import (
    GENESIS_PREV_HASH,
    SCHEME,
    CanonicalError,
    canonicalize,
    sha256_hex,
    validate,
)

from tests.conftest import REPO_ROOT

VECTORS_PATH = REPO_ROOT / "tests" / "fixtures" / "hash_vectors.json"
RESEARCH_PROBE_SHA256 = "3274e09024a2561fb06caa533f7727a9e67ae6c7c5e3bfe8fe849233d2c5d99e"


def _load() -> dict[str, Any]:
    raw = VECTORS_PATH.read_bytes()
    raw.decode("ascii")  # the file must be pure ASCII (non-ASCII inputs use JSON escapes)
    assert b"\r" not in raw
    return json.loads(raw)


VECTORS = _load()


def test_vector_file_shape() -> None:
    assert set(VECTORS) == {"accept", "reject", "formatting"}
    assert len(VECTORS["accept"]) >= 10
    assert len(VECTORS["reject"]) >= 10
    names = [v["name"] for v in VECTORS["accept"] + VECTORS["reject"]]
    assert len(names) == len(set(names)), "vector names must be unique"


def test_research_probe_is_independently_anchored() -> None:
    probe = {
        "prev_hash": GENESIS_PREV_HASH,
        "scheme": SCHEME,
        "seq": "0",
        "test": "researcher-probe-2026-11-18",
    }
    assert sha256_hex(canonicalize(probe)) == RESEARCH_PROBE_SHA256
    (vector,) = [v for v in VECTORS["accept"] if v["name"] == "research-probe"]
    assert vector["value"] == probe
    assert vector["sha256"] == RESEARCH_PROBE_SHA256


@pytest.mark.parametrize("vector", VECTORS["accept"], ids=lambda v: v["name"])
def test_accept_vector(vector: dict[str, Any]) -> None:
    validate(vector["value"])
    text = canonicalize(vector["value"])
    assert text == vector["canonical"]
    assert sha256_hex(text) == vector["sha256"]
    assert json.loads(text) == vector["value"]


@pytest.mark.parametrize("vector", VECTORS["reject"], ids=lambda v: v["name"])
def test_reject_vector(vector: dict[str, Any]) -> None:
    with pytest.raises(CanonicalError):
        validate(vector["value"])
    with pytest.raises(CanonicalError):
        canonicalize(vector["value"])


def _coerce(kind: str, text: str) -> Any:
    return {
        "decimal": Decimal,
        "float": float,
        "int": int,
        "bool": lambda s: s == "true",
        "str": str,
        "datetime": datetime.fromisoformat,
        "date": date.fromisoformat,
    }[kind](text)


@pytest.mark.parametrize(
    "vector",
    VECTORS["formatting"],
    ids=lambda v: f"{v['fn']}({v['input_type']}:{v['input']})",
)
def test_formatting_vector(vector: dict[str, Any]) -> None:
    fn = getattr(canonical, vector["fn"])
    value = _coerce(vector["input_type"], vector["input"])
    if vector.get("refused"):
        with pytest.raises(CanonicalError):
            fn(value)
    else:
        assert fn(value) == vector["expected"]


def test_formatting_covers_every_helper_and_float_refusal() -> None:
    helpers = {"format_money", "format_ratio", "format_ts", "format_date", "format_int"}
    assert {v["fn"] for v in VECTORS["formatting"]} == helpers
    float_refused = {
        v["fn"] for v in VECTORS["formatting"] if v["input_type"] == "float" and v.get("refused")
    }
    assert float_refused == helpers
