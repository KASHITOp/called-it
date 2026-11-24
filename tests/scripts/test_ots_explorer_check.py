"""The explorer cross-check passes only when both explorers agree (D-26c).

The proofs here are SYNTHETIC test fixtures built in code: they are not real timestamps.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import BytesSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ots_explorer_check.py"
spec = importlib.util.spec_from_file_location("ots_explorer_check", SCRIPT)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

FILE_DIGEST = bytes(range(32))
MERKLE_ROOT_INTERNAL = hashlib.sha256(FILE_DIGEST).digest()  # what the attestation commits to
HEIGHT = 840000
BLOCK_TIME = 1_798_000_000  # 2026-12-23, test value


def _proof(tmp_path: Path, *, pending_only: bool = False) -> Path:
    root = Timestamp(FILE_DIGEST)
    child = root.ops.add(OpSHA256())  # its msg is sha256(FILE_DIGEST) = MERKLE_ROOT_INTERNAL
    if pending_only:
        child.attestations.add(PendingAttestation("https://calendar.invalid"))
    else:
        child.attestations.add(BitcoinBlockHeaderAttestation(HEIGHT))
    ctx = BytesSerializationContext()
    DetachedTimestampFile(OpSHA256(), root).serialize(ctx)
    path = tmp_path / "x.ots"
    path.write_bytes(ctx.getbytes())
    return path


def _explorers(monkeypatch: pytest.MonkeyPatch, roots: dict[str, str], time: int = BLOCK_TIME):
    def fake_get(url: str) -> str:
        for host, root in roots.items():
            if host in url:
                if "block-height" in url:
                    return "00" * 32
                return json.dumps({"merkle_root": root, "timestamp": time})
        raise OSError("unreachable")

    monkeypatch.setattr(checker, "_get", fake_get)


GOOD = bytes(reversed(MERKLE_ROOT_INTERNAL)).hex()


def test_pass_when_both_explorers_agree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _explorers(monkeypatch, {"blockstream.info": GOOD, "mempool.space": GOOD})
    code = checker.check(_proof(tmp_path), FILE_DIGEST.hex(), "2026-12-31T18:30:00Z")
    assert code == checker.EXIT_PASS


def test_fail_when_one_explorer_disagrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _explorers(monkeypatch, {"blockstream.info": GOOD, "mempool.space": "ab" * 32})
    assert checker.check(_proof(tmp_path), FILE_DIGEST.hex(), None) == checker.EXIT_FAIL


def test_fail_when_the_digest_does_not_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _explorers(monkeypatch, {"blockstream.info": GOOD, "mempool.space": GOOD})
    assert checker.check(_proof(tmp_path), "00" * 32, None) == checker.EXIT_FAIL


def test_fail_when_the_block_is_after_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _explorers(monkeypatch, {"blockstream.info": GOOD, "mempool.space": GOOD})
    assert checker.check(_proof(tmp_path), FILE_DIGEST.hex(), "2026-12-01T00:00:00Z") == (
        checker.EXIT_FAIL
    )


def test_fail_when_an_explorer_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _explorers(monkeypatch, {"blockstream.info": GOOD})
    assert checker.check(_proof(tmp_path), FILE_DIGEST.hex(), None) == checker.EXIT_FAIL


def test_pending_only_proof_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _explorers(monkeypatch, {})
    code = checker.check(_proof(tmp_path, pending_only=True), FILE_DIGEST.hex(), None)
    assert code == checker.EXIT_PENDING == 2
