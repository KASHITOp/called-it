"""The pre-push scan finds planted fake credentials and never prints them (T-01-40)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "preflight_publish.py"
FAKE = "postgresql+psycopg://user:hunter2secret@" + "db.notlisted" + ".test:5432/postgres"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(".env\n*.db\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_repo_passes(repo: Path) -> None:
    done = _run(repo)
    assert done.returncode == 0, done.stdout
    assert "clean" in done.stdout


def test_planted_credential_in_a_tracked_file_fails_and_is_not_printed(repo: Path) -> None:
    (repo / "notes.txt").write_text(f"x\n{FAKE}\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-q", "-m", "oops")
    done = _run(repo)
    assert done.returncode == 1
    assert "notes.txt:2" in done.stdout
    assert "hunter2secret" not in done.stdout + done.stderr
    assert "notlisted" not in done.stdout + done.stderr


def test_a_credential_deleted_but_still_in_history_fails(repo: Path) -> None:
    (repo / "notes.txt").write_text(f"{FAKE}\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-q", "-m", "oops")
    _git(repo, "rm", "-q", "notes.txt")
    _git(repo, "commit", "-q", "-m", "remove")
    done = _run(repo)
    assert done.returncode == 1
    assert "in history" in done.stdout
    assert "hunter2secret" not in done.stdout


def test_a_supabase_pooler_host_fails(repo: Path) -> None:
    host = "aws-0-ap-south-1" + ".pooler.supabase" + ".com"
    (repo / "a.md").write_text("host " + host + "\n", encoding="utf-8")
    _git(repo, "add", "a.md")
    _git(repo, "commit", "-q", "-m", "host")
    assert _run(repo).returncode == 1


def test_tracked_env_and_db_files_fail(repo: Path) -> None:
    (repo / "data.db").write_bytes(b"x")
    _git(repo, "add", "-f", "data.db")
    _git(repo, "commit", "-q", "-m", "db")
    done = _run(repo)
    assert done.returncode == 1 and "data.db" in done.stdout


def test_env_example_with_the_marker_is_allowed(repo: Path) -> None:
    (repo / ".env.example").write_text(
        "DATABASE_URL=postgresql+psycopg://postgres.REF:URL-ENCODED-PASSWORD@HOST:5432/postgres\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".env.example")
    _git(repo, "commit", "-q", "-m", "example")
    assert _run(repo).returncode == 0


def test_an_unignored_env_file_fails(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    done = _run(tmp_path)
    assert done.returncode == 1 and ".env is not git-ignored" in done.stdout


def test_wrong_branch_fails(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature")
    done = _run(repo)
    assert done.returncode == 1 and "not main" in done.stdout


def test_allowlisted_placeholder_hosts_and_bare_prose_are_not_findings(repo: Path) -> None:
    text = "postgresql://u:p@" + "localhost:5432/x" + "\n" + "see the supabase" + ".com docs" + "\n"
    (repo / "doc.md").write_text(text, encoding="utf-8")
    _git(repo, "add", "doc.md")
    _git(repo, "commit", "-q", "-m", "doc")
    assert _run(repo).returncode == 0


def test_the_real_env_secret_in_a_tracked_file_is_found_without_printing_it(repo: Path) -> None:
    secret = "Zq9wLm2Xv8"
    env_line = "DATABASE_URL=postgresql+psycopg://admin:" + secret + "@" + "db.realhost.test:5432/p"
    (repo / ".env").write_text(env_line + "\n", encoding="utf-8")
    (repo / "leak.txt").write_text("token " + secret + "\n", encoding="utf-8")
    _git(repo, "add", "leak.txt")
    _git(repo, "commit", "-q", "-m", "leak")
    done = _run(repo)
    assert done.returncode == 1 and "real DATABASE_URL password" in done.stdout
    assert secret not in done.stdout + done.stderr
