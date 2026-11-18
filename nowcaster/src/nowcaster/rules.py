"""Append a ``rules`` record: the SHA-256 of PREREGISTRATION.md and the universe config.

Seq 0 of the live chain is the preregistration (D-19). Any later rules change is a new
rules record, never an edit.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import Settings, require_live_write_context

from nowcaster.ledger.canonical import canonicalize
from nowcaster.ledger.chain import AppendedRecord, append_record, next_position, read_head
from nowcaster.ledger.records import TypedColumns, build_rules_payload, rules_typed_columns

RULES_ID = "prereg-v1"
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


class RulesError(RuntimeError):
    """The rules record cannot be built or appended (fixed, non-secret message)."""


@dataclass(frozen=True)
class RulesResult:
    dry_run: bool
    payload_canonical: str
    appended: AppendedRecord | None


def _file_sha256(path: Path, label: str) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        raise RulesError(f"{label} not readable: {path.as_posix()}") from None
    return hashlib.sha256(data).hexdigest()


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


def _run_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    return run_id if run_id.isdigit() else "local"


def append_rules_record(
    settings: Settings,
    document: Path | None,
    universe: Path | None,
    now: datetime,
    dry_run: bool,
) -> RulesResult:
    if settings.calledit_env == "live" and (document is not None or universe is not None):
        raise RulesError("--document and --universe overrides are refused when CALLEDIT_ENV=live")
    document_path = document if document is not None else settings.prereg_path
    universe_path = universe if universe is not None else settings.universe_path
    document_sha = _file_sha256(document_path, "preregistration document")
    universe_sha = _file_sha256(universe_path, "universe config")
    git_commit = _git_commit(settings)
    run_id = _run_id()

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
        require_live_write_context(settings)
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
