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
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

URL_PATTERN = re.compile(r"postgres(ql)?(\+psycopg)?://[^\s:@]+:[^\s@]+@([^\s/:?'\"`\\]*)")
HOST_PATTERNS = (
    re.compile(r"[a-z0-9]{15,}\.supabase\.co\b"),
    re.compile(r"[a-z0-9]+-\d+-[a-z0-9-]+\.pooler\.supabase\.com"),
)
# Hosts and placeholders that can never be a real database (documentation and test fixtures).
ALLOWED_HOSTS = frozenset(
    {
        "",
        "host",
        "pooler-host",
        "localhost",
        "127.0.0.1",
        "example.com",
        "example.invalid",
        "x",
        "bad-host",
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
    cleaned = host.strip("<>[]").lower()
    return cleaned not in ALLOWED_HOSTS and not cleaned.endswith(".example.com")


def _line_hits(path: str, line: str) -> bool:
    if path.endswith(EXAMPLE_FILE) and EXAMPLE_MARKER in line:
        return False
    if any(p.search(line) for p in HOST_PATTERNS):
        return True
    return any(_host_unlisted(m.group(3)) for m in URL_PATTERN.finditer(line))


def _real_secret_findings(repo: Path) -> list[str]:
    """Look for the real DATABASE_URL parts from .env in tracked files and history."""
    env = repo / ".env"
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


def scan(repo: Path, branch: str = "main") -> list[str]:
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
        repo, "log", branch, "-p", "-U0", "--no-color", "--format=commit %h", check=False
    )
    commit = path_in_diff = ""
    for line in history.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("commit "):
            commit = line[7:]
        elif line.startswith("+++ b/"):
            path_in_diff = line[6:]
        elif (
            line.startswith(("+", "-"))
            and not line.startswith(("+++", "---"))
            and _line_hits(path_in_diff, line[1:])
        ):
            findings.append(f"credential-like text in history: {commit} {path_in_diff}")
    findings.extend(_real_secret_findings(repo))
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    findings = scan(args.repo, args.branch)
    for finding in findings:
        print(f"FINDING: {finding}")
    if findings:
        print(f"preflight: {len(findings)} finding(s); do not push")
        return 1
    print("preflight: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
