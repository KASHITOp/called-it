"""The rules record binds every lock to the preregistration and the universe it was made under
(LEDG-07 mechanism, FOUND-03, T-01-27, D-19).

Edits to PREREGISTRATION.md or config/universe.toml are refused by ``predict`` until a new,
visible ``rules`` record is appended. Live provenance (tracked, equal to the blob at HEAD, LF-only,
confirmed universe) is tested against a temp git repository created inside the test.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
from calledit_data.db.settings import LiveContextError, Settings
from nowcaster.exit_codes import EXIT_OK, EXIT_REFUSED
from nowcaster.rules import RulesError, append_rules_record
from nowcaster.universe import load_universe

from nowcaster import rules as rules_module
from tests.ledger.lock_helpers import LOCK_TIME, RULES_TIME, UNIVERSE_SOURCE, LockEnv

LATER = LOCK_TIME.replace(hour=5)
EVEN_LATER = LOCK_TIME.replace(hour=6)
PG_URL = "postgresql://u:p@127.0.0.1:1/postgres"  # never contacted: every test refuses first


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- freshness (T-01-27) ------------------------------------------------------------------


def test_prereg_edit_requires_new_rules_record(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    first = lock_env.rules()
    assert first.exit_code == 0 and f"RULES seq=0 hash={lock_env.rows()[0]['hash']}" in first.output
    lock_env.prereg.write_bytes(lock_env.prereg.read_bytes() + b"one more rule\n")

    refused = lock_env.predict()
    assert refused.exit_code == EXIT_REFUSED, refused.output
    assert "document_sha256" in refused.output
    assert "universe_sha256" not in refused.output
    assert lock_env.count() == 1

    renewed = lock_env.rules(LOCK_TIME)
    assert renewed.exit_code == 0 and "RULES seq=1" in renewed.output
    assert lock_env.rows()[1]["payload"]["document_sha256"] == _sha(lock_env.prereg)

    locked = lock_env.predict("Q3FY27", LATER)
    assert locked.exit_code == EXIT_OK, locked.output
    rows = lock_env.rows()
    assert [r["record_kind"] for r in rows] == [
        "rules",
        "rules",
        "prediction",
        "prediction",
        "prediction",
    ]
    assert {r["payload"]["rules_seq"] for r in rows[2:]} == {"1"}
    assert {r["payload"]["rules_hash"] for r in rows[2:]} == {rows[1]["hash"]}


def test_universe_edit_requires_new_rules_record(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    lock_env.universe.write_bytes(lock_env.universe.read_bytes() + b"\n# a harmless comment\n")

    refused = lock_env.predict()
    assert refused.exit_code == EXIT_REFUSED, refused.output
    assert "universe_sha256" in refused.output
    assert "document_sha256" not in refused.output
    assert lock_env.count() == 1

    assert lock_env.rules(LOCK_TIME).exit_code == 0
    locked = lock_env.predict("Q3FY27", LATER)
    assert locked.exit_code == EXIT_OK, locked.output
    assert {r["payload"]["universe_sha256"] for r in lock_env.rows()[2:]} == {
        _sha(lock_env.universe)
    }


def test_both_files_changed_names_both_fields(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    lock_env.prereg.write_bytes(b"different\n")
    lock_env.universe.write_bytes(lock_env.universe.read_bytes() + b"\n#x\n")
    refused = lock_env.predict()
    assert refused.exit_code == EXIT_REFUSED
    assert "document_sha256" in refused.output and "universe_sha256" in refused.output


def test_a_missing_preregistration_file_refuses_the_lock(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    lock_env.prereg.unlink()
    refused = lock_env.predict()
    assert refused.exit_code == EXIT_REFUSED, refused.output
    assert "not readable" in refused.output
    assert lock_env.count() == 1


def test_disabling_company_drops_it_from_next_lock(lock_env: LockEnv) -> None:
    lock_env.load_seed()
    assert lock_env.rules().exit_code == 0
    text = lock_env.universe.read_text(encoding="utf-8")
    edited = re.sub(
        r'(ticker = "ETERNAL"(?:.|\n)*?)enabled = true', r"\1enabled = false", text, count=1
    )
    assert edited != text
    lock_env.universe.write_bytes(edited.encode("utf-8"))

    refused = lock_env.predict()
    assert refused.exit_code == EXIT_REFUSED and "universe_sha256" in refused.output
    assert lock_env.count() == 1

    assert lock_env.rules(LOCK_TIME).exit_code == 0
    locked = lock_env.predict("Q3FY27", LATER)
    assert locked.exit_code == EXIT_OK, locked.output  # every ENABLED company was locked
    rows = lock_env.rows()
    assert [r["payload"]["ticker"] for r in rows[2:]] == ["DMART", "TITAN"]
    assert "ETERNAL" not in locked.output
    assert {r["payload"]["universe_sha256"] for r in rows[2:]} == {_sha(lock_env.universe)}


def test_universe_hash_is_idempotent_and_is_the_sha256_of_the_file_bytes(lock_env: LockEnv) -> None:
    first = load_universe(lock_env.universe)
    second = load_universe(lock_env.universe)
    assert first.universe_sha256 == second.universe_sha256 == _sha(lock_env.universe)
    lock_env.universe.write_bytes(lock_env.universe.read_bytes() + b"\n")
    assert load_universe(lock_env.universe).universe_sha256 != first.universe_sha256


# --- the rules command --------------------------------------------------------------------


def test_rules_dry_run_prints_the_full_payload_and_appends_nothing(lock_env: LockEnv) -> None:
    result = lock_env.invoke(["rules", "--dry-run"], RULES_TIME)
    assert result.exit_code == 0, result.output
    assert f'"document_sha256":"{_sha(lock_env.prereg)}"' in result.output
    assert f'"universe_sha256":"{_sha(lock_env.universe)}"' in result.output
    assert '"record_kind":"rules"' in result.output
    assert lock_env.count() == 0


def test_rules_prints_seq_and_hash(lock_env: LockEnv) -> None:
    result = lock_env.rules()
    assert result.exit_code == 0, result.output
    assert re.search(r"RULES seq=0 hash=[0-9a-f]{64}", result.output)


# --- live provenance ----------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lock_env: LockEnv) -> Path:
    """A temp git repo with a committed preregistration and a fully confirmed universe."""
    folder = tmp_path / "repo"
    (folder / "config").mkdir(parents=True)
    text = UNIVERSE_SOURCE.read_text(encoding="utf-8")
    text = re.sub(
        r"(?m)^(isin_)?confirmed = false$", lambda m: f"{m.group(1) or ''}confirmed = true", text
    )
    (folder / "config" / "universe.toml").write_bytes(text.encode("utf-8"))
    (folder / "PREREGISTRATION.md").write_bytes(b"# Preregistration (live provenance test)\n")
    _git(folder, "init", "-q")
    _git(folder, "add", "PREREGISTRATION.md", "config/universe.toml")
    _git(folder, "commit", "-q", "-m", "init")
    monkeypatch.chdir(folder)
    monkeypatch.delenv("CALLEDIT_PREREG_PATH")
    monkeypatch.delenv("CALLEDIT_UNIVERSE_PATH")
    return folder


def _live(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=PG_URL, calledit_env="live", **overrides)  # type: ignore[arg-type]


def _live_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")


def test_live_rules_accepts_committed_lf_files_and_records_the_head_commit(
    repo: Path, lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    _live_actions(monkeypatch)
    monkeypatch.setattr(rules_module, "make_engine", lambda settings: lock_env.engine)
    head = _git(repo, "rev-parse", "HEAD")
    result = append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)
    assert result.appended is not None
    payload = lock_env.rows()[0]["payload"]
    assert payload["document_git_commit"] == head
    assert payload["document_sha256"] == _sha(repo / "PREREGISTRATION.md")
    assert payload["universe_sha256"] == _sha(repo / "config" / "universe.toml")
    assert payload["document_path"] == "PREREGISTRATION.md"
    assert payload["universe_path"] == "config/universe.toml"


def test_live_rules_dry_run_appends_nothing(
    repo: Path, lock_env: LockEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rules_module, "make_engine", lambda settings: lock_env.engine)
    result = append_rules_record(_live(), None, None, RULES_TIME, dry_run=True)
    assert result.dry_run and result.appended is None
    assert (
        '"document_git_commit":"' + _git(repo, "rev-parse", "HEAD") + '"'
        in result.payload_canonical
    )
    assert lock_env.count() == 0


@pytest.mark.parametrize("target", ["PREREGISTRATION.md", "config/universe.toml"])
def test_live_rules_refuses_a_file_that_differs_from_head(
    repo: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _live_actions(monkeypatch)
    path = repo / target
    path.write_bytes(path.read_bytes() + b"\n# edited after the commit\n")
    with pytest.raises(RulesError, match="differs from its committed blob"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


@pytest.mark.parametrize("target", ["PREREGISTRATION.md", "config/universe.toml"])
def test_live_rules_refuses_an_untracked_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _live_actions(monkeypatch)
    _git(repo, "rm", "-q", "--cached", target)
    with pytest.raises(RulesError, match="not tracked by git"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


def test_live_rules_refuses_a_staged_but_uncommitted_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _live_actions(monkeypatch)
    fresh = repo / "OTHER.md"
    fresh.write_bytes(b"x\n")
    _git(repo, "add", "OTHER.md")
    monkeypatch.setenv("CALLEDIT_PREREG_PATH", "OTHER.md")
    with pytest.raises(RulesError, match="not committed at HEAD"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


@pytest.mark.parametrize("target", ["PREREGISTRATION.md", "config/universe.toml"])
def test_live_rules_refuses_a_file_with_a_cr_byte_even_when_committed(
    repo: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _live_actions(monkeypatch)
    path = repo / target
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    _git(repo, "add", target)
    _git(repo, "commit", "-q", "-m", "crlf")
    with pytest.raises(RulesError, match="CR byte"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


def test_live_rules_refuses_an_unconfirmed_universe(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _live_actions(monkeypatch)
    path = repo / "config" / "universe.toml"
    unconfirmed = UNIVERSE_SOURCE.read_bytes().replace(
        b'isin = "INE758T01015"\nisin_confirmed = true',
        b'isin = "INE758T01015"\nisin_confirmed = false',
        1,
    )
    assert b"isin_confirmed = false" in unconfirmed
    path.write_bytes(unconfirmed)  # the shipped file is fully confirmed, so un-confirm one ISIN
    _git(repo, "add", "config/universe.toml")
    _git(repo, "commit", "-q", "-m", "unconfirmed")
    with pytest.raises(RulesError, match="isin_confirmed is false"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


def test_live_rules_refuses_outside_github_actions_main(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(LiveContextError, match="GitHub Actions"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    with pytest.raises(LiveContextError, match="refs/heads/main"):
        append_rules_record(_live(), None, None, RULES_TIME, dry_run=False)


def test_document_and_universe_overrides_are_refused_in_live(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _live_actions(monkeypatch)
    with pytest.raises(RulesError, match="overrides are refused"):
        append_rules_record(_live(), repo / "PREREGISTRATION.md", None, RULES_TIME, dry_run=True)
    with pytest.raises(RulesError, match="overrides are refused"):
        append_rules_record(
            _live(), None, repo / "config" / "universe.toml", RULES_TIME, dry_run=True
        )
