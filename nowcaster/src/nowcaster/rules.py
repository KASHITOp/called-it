"""Append a ``rules`` record: the SHA-256 of PREREGISTRATION.md and the universe config.

Seq 0 of the live chain is the preregistration (D-19). Any later rules change is a new
rules record, never an edit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from calledit_data.db.engine import make_engine
from calledit_data.db.schema import predictions
from calledit_data.db.settings import Settings, require_live_write_context

from nowcaster.ledger.canonical import canonicalize
from nowcaster.ledger.chain import AppendedRecord, append_record, next_position, read_head
from nowcaster.ledger.records import TypedColumns, build_rules_payload, rules_typed_columns
from nowcaster.universe import UniverseError, load_universe

RULES_ID = "prereg-v1"
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class RulesError(RuntimeError):
    """The rules record cannot be built or appended (fixed, non-secret message)."""


@dataclass(frozen=True)
class RulesResult:
    dry_run: bool
    payload_canonical: str
    appended: AppendedRecord | None


@dataclass(frozen=True)
class RulesHead:
    """The latest rules record: what every later lock is bound to (LEDG-07)."""

    seq: int
    hash: str
    document_sha256: str
    universe_sha256: str


def latest_rules_record(conn: sa.Connection) -> RulesHead | None:
    """The newest ``rules`` record in the chain, or ``None`` if none was ever appended."""
    row = conn.execute(
        sa.select(predictions.c.seq, predictions.c.hash, predictions.c.payload_canonical)
        .where(predictions.c.record_kind == "rules")
        .order_by(predictions.c.seq.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    payload = json.loads(row.payload_canonical)
    return RulesHead(
        seq=row.seq,
        hash=row.hash,
        document_sha256=payload["document_sha256"],
        universe_sha256=payload["universe_sha256"],
    )


def _file_sha256(path: Path, label: str) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        raise RulesError(f"{label} not readable: {path.as_posix()}") from None
    return hashlib.sha256(data).hexdigest()


def stale_fields(settings: Settings, head: RulesHead, universe_sha256: str) -> list[str]:
    """Which hashed inputs changed since ``head`` was appended (empty: the rules are current).

    ``universe_sha256`` is the hash of the universe bytes the caller parsed; the preregistration
    is hashed here from ``settings.prereg_path``. A lock may only run under the bytes the latest
    rules record names (T-01-27).
    """
    stale: list[str] = []
    if _file_sha256(settings.prereg_path, "preregistration document") != head.document_sha256:
        stale.append("document_sha256")
    if universe_sha256 != head.universe_sha256:
        stale.append("universe_sha256")
    return stale


def _git(args: list[str], folder: Path) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args], cwd=folder, capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        raise RulesError("git is not available; live rules records need it") from None


def _require_committed_lf(path: Path, label: str) -> None:
    """A hashed file must be tracked, equal to its blob at HEAD, and LF-only (Pitfall 4)."""
    shown = _display_path(path)
    data = path.read_bytes()
    if b"\r" in data:
        raise RulesError(f"{label} {shown} contains a CR byte; hashed files must be LF-only")
    folder = path.resolve().parent
    tracked = _git(["ls-files", "--error-unmatch", "--full-name", "--", path.name], folder)
    if tracked.returncode != 0:
        raise RulesError(f"{label} {shown} is not tracked by git; commit it first")
    full_name = tracked.stdout.decode("utf-8").strip()
    blob = _git(["cat-file", "blob", f"HEAD:{full_name}"], folder)
    if blob.returncode != 0:
        raise RulesError(f"{label} {shown} is not committed at HEAD; commit it first")
    if blob.stdout != data:
        raise RulesError(
            f"{label} {shown} differs from its committed blob at HEAD; commit it first"
        )


def _require_live_provenance(document_path: Path, universe_path: Path) -> None:
    """Live rules records hash committed files and a confirmed universe only (T-01-28)."""
    _require_committed_lf(document_path, "preregistration document")
    _require_committed_lf(universe_path, "universe config")
    try:
        problems = load_universe(universe_path).unconfirmed()
    except UniverseError as exc:
        raise RulesError(f"universe config refused: {exc}") from None
    if problems:
        raise RulesError("live rules refused, unconfirmed universe values: " + "; ".join(problems))


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _git_commit(settings: Settings) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        sha = result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        sha = ""
    if _GIT_SHA_RE.fullmatch(sha):
        return sha
    if settings.calledit_env == "live":
        raise RulesError("git rev-parse HEAD failed; live rules records need the commit")
    return "none"


def current_run_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    return run_id if run_id.isdigit() else "local"


def append_rules_record(
    settings: Settings,
    document: Path | None,
    universe: Path | None,
    now: datetime,
    dry_run: bool,
) -> RulesResult:
    live = settings.calledit_env == "live"
    if live and (document is not None or universe is not None):
        raise RulesError("--document and --universe overrides are refused when CALLEDIT_ENV=live")
    if live and not dry_run:
        require_live_write_context(settings)
    document_path = document if document is not None else settings.prereg_path
    universe_path = universe if universe is not None else settings.universe_path
    document_sha = _file_sha256(document_path, "preregistration document")
    universe_sha = _file_sha256(universe_path, "universe config")
    if live:
        _require_live_provenance(document_path, universe_path)
    git_commit = _git_commit(settings)
    run_id = current_run_id()

    def build(seq: int, prev_hash: str) -> tuple[dict, TypedColumns]:
        payload = build_rules_payload(
            seq=seq,
            prev_hash=prev_hash,
            rules_id=RULES_ID,
            document_path=_display_path(document_path),
            document_sha256=document_sha,
            document_git_commit=git_commit,
            universe_path=_display_path(universe_path),
            universe_sha256=universe_sha,
            recorded_at=now,
            run_id=run_id,
        )
        return payload, rules_typed_columns(now)

    engine = make_engine(settings)
    try:
        if dry_run:
            with engine.connect() as conn:
                seq, prev_hash = next_position(read_head(conn))
            payload, _typed = build(seq, prev_hash)
            return RulesResult(dry_run=True, payload_canonical=canonicalize(payload), appended=None)
        appended = append_record(engine, build)
        return RulesResult(
            dry_run=False, payload_canonical=appended.payload_canonical, appended=appended
        )
    except sa.exc.DBAPIError as exc:
        raise RulesError(
            f"ledger write refused by the database ({type(exc).__name__}); "
            "run: uv run nowcast db check"
        ) from None
    finally:
        engine.dispose()
