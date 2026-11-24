"""Pre-push secret and .env scan (D-03, threat T-01-40). Standard library only.

Exits 1 on any finding and 0 when clean. It prints file paths, commit ids and line numbers
only, never the text that matched.

Checks:
  1. ``.env`` is git-ignored.
  2. No tracked file, and nothing in the pushed history, is named ``.env*`` (other than
     ``.env.example``) or ``*.db`` / ``*.db-wal`` / ``*.db-shm``.
  3. No tracked file and no line in the history of the branch being pushed contains a
     connection string with a password for a host that is not an allowlisted placeholder
     (localhost, 127.0.0.1, example.*, HOST, POOLER-HOST), or a Supabase host that carries a
     project reference or a region prefix. ``.env.example`` is exempt for lines containing
     ``URL-ENCODED-PASSWORD``. A bare mention of a Supabase domain in prose is not a finding.
  4. The real host, user and password from the local ``.env`` appear in no tracked file and
     nowhere in history. They are checked in memory; only a yes/no finding is printed.
  5. The current branch is ``main``.
  3c. When origin/<branch> exists, the credential-text scan of history covers only the commits
     not yet published (earlier ones are already public and were reviewed); file names and the
     real secret are still checked over the full history.
  6. The whole scan, including check 4, is repeated on a fresh clone of the branch (with the
     real secret taken from the working copy's ``.env``), so what is pushed is what is checked.
     Run by ``.githooks/pre-push`` before every push.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

URL_PATTERN = re.compile(r"postgres(ql)?(\+psycopg)?://[^\s:@]+:[^\s@]+@([^\s/:?'\"`\\]*)")
HOST_PATTERNS = (
    re.compile(r"[a-z0-9]{15,}\.supabase\.co\b"),
    re.compile(r"[a-z0-9]+-\d+-[a-z0-9-]+\.pooler\.supabase\.com"),
)
# Hosts and placeholders that can never be a real database (documentation and test fixtures).
# EXACT, case-insensitive matches only: never a substring, suffix or wildcard, so a real
# *.pooler.supabase.com host or a real project reference is never excused.
ALLOWED_HOSTS = frozenset(
    {
        "",
        "example.invalid",
        "example.com",
        "localhost",
        "127.0.0.1",
        "host",
        "pooler-host",
        "projectref",
        "ref",
        "pooler.example.com",
    }
)
EXAMPLE_FILE = ".env.example"
EXAMPLE_MARKER = "URL-ENCODED-PASSWORD"
FORBIDDEN_NAME = re.compile(r"(^|/)(\.env(\..+)?|[^/]+\.db(-wal|-shm)?)$")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False, timeout=300)
    if check and done.returncode != 0:
        raise SystemExit(f"preflight: git {args[0]} failed")
    return done


def _name_forbidden(path: str) -> bool:
    if path == EXAMPLE_FILE or path.endswith("/" + EXAMPLE_FILE):
        return False
    return bool(FORBIDDEN_NAME.search(path))


def _host_unlisted(host: str) -> bool:
    cleaned = host.strip("<>[]").lower()  # placeholder brackets only; then an exact lookup
    return cleaned not in ALLOWED_HOSTS


def _line_hits(path: str, line: str) -> bool:
    if path.endswith(EXAMPLE_FILE) and EXAMPLE_MARKER in line:
        return False
    if any(p.search(line) for p in HOST_PATTERNS):
        return True
    return any(_host_unlisted(m.group(3)) for m in URL_PATTERN.finditer(line))


def _real_secret_findings(repo: Path, env_file: Path | None = None) -> list[str]:
    """Look for the real DATABASE_URL parts from .env in tracked files and history."""
    env = env_file if env_file is not None else repo / ".env"
    if not env.is_file():
        return []
    value = ""
    for raw in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("DATABASE_URL="):
            value = raw.split("=", 1)[1].strip().strip("'\"")
    if not value:
        return []
    try:
        parts = urlsplit(value)
        needles = {
            "host": parts.hostname or "",
            "user": parts.username or "",
            "password": unquote(parts.password or ""),
            "raw password": parts.password or "",
        }
    except ValueError:
        return []
    findings: list[str] = []
    for label, needle in needles.items():
        if len(needle) < 6 or needle.lower() in ALLOWED_HOSTS:
            continue
        if _git(repo, "grep", "-qF", "--", needle, check=False).returncode == 0:
            findings.append(f"the real DATABASE_URL {label} is in a tracked file")
        log = _git(repo, "log", "--all", "-S" + needle, "--format=%h", check=False)
        if log.stdout.strip():
            findings.append(f"the real DATABASE_URL {label} is in git history")
    return findings


def scan(
    repo: Path, branch: str = "main", env_file: Path | None = None, since: str | None = None
) -> list[str]:
    findings: list[str] = []
    if _git(repo, "check-ignore", "-q", ".env", check=False).returncode != 0:
        findings.append(".env is not git-ignored")
    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()
    if current != branch:
        findings.append(f"current branch is not {branch}")

    for name in _git(repo, "ls-files", "-z").stdout.decode("utf-8", "replace").split("\0"):
        if not name:
            continue
        if _name_forbidden(name):
            findings.append(f"tracked file with a forbidden name: {name}")
        path = repo / name
        if not path.is_file():
            continue
        try:
            text = path.read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _line_hits(name, line):
                findings.append(f"credential-like text in tracked file: {name}:{number}")

    names = _git(repo, "log", branch, "--name-only", "--format=", "-z", check=False)
    for name in sorted(set(names.stdout.decode("utf-8", "replace").split("\0"))):
        if name and _name_forbidden(name):
            findings.append(f"forbidden file name in history: {name}")

    history = _git(
        repo,
        "log",
        f"{since}..{branch}" if since else branch,
        "-p",
        "-U0",
        "--no-color",
        "--format=commit %h",
        check=False,
    )
    commit = path_in_diff = ""
    for line in history.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ b/"):
            path_in_diff = line[6:]
        elif (
            line.startswith(("+",) if since else ("+", "-"))
            and not line.startswith(("+++", "---"))
            and _line_hits(path_in_diff, line[1:])
        ):
            findings.append(f"credential-like text in history: {commit} {path_in_diff}")
    findings.extend(_real_secret_findings(repo, env_file))
    return sorted(set(findings))


def pushed_base(repo: Path, branch: str) -> str | None:
    """The commit already published as origin/<branch>, if any (text scan covers only newer ones).

    The full history is still checked for forbidden file names and for the real secret.
    """
    done = _git(repo, "rev-parse", "--verify", "-q", f"origin/{branch}", check=False)
    return done.stdout.decode().strip() or None


def scan_fresh_clone(repo: Path, branch: str = "main") -> list[str]:
    """Scan a fresh clone of what would be pushed, against the real secret of the working copy."""
    with tempfile.TemporaryDirectory(prefix="preflight-clone-") as tmp:
        clone = Path(tmp) / "clone"
        done = subprocess.run(
            ["git", "clone", "-q", "--branch", branch, "--single-branch", str(repo), str(clone)],
            capture_output=True,
            check=False,
            timeout=600,
        )
        if done.returncode != 0:
            return ["fresh clone failed"]
        return [
            f"fresh clone: {f}"
            for f in scan(clone, branch, repo / ".env", since=pushed_base(repo, branch))
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    findings = scan(
        args.repo, args.branch, since=pushed_base(args.repo, args.branch)
    ) + scan_fresh_clone(args.repo, args.branch)
    for finding in findings:
        print(f"FINDING: {finding}")
    if findings:
        print(f"preflight: {len(findings)} finding(s); do not push")
        return 1
    print("preflight: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
