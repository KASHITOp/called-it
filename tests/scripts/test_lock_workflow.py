"""Structural guards on the lock workflow (T-01-41, T-01-42, T-01-46), without a YAML parser."""

from __future__ import annotations

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "lock.yml").read_text(
    encoding="utf-8"
)


def test_dispatch_only_inputs_and_concurrency() -> None:
    assert re.search(r"(?m)^on:\n  workflow_dispatch:\n", TEXT)
    assert "pull_request" not in TEXT
    for name in ("action", "mode", "quarter", "confirm_live"):
        assert re.search(rf"(?m)^      {name}:$", TEXT), name
    assert "options: [rules, predict, stamp, upgrade]" in TEXT
    assert "options: [rehearsal, live]\n        default: rehearsal" in TEXT
    assert "group: ledger\n  cancel-in-progress: false" in TEXT
    assert "permissions:\n  contents: write" in TEXT


def test_inputs_never_reach_a_shell_command_directly() -> None:
    for block in re.findall(r"(?ms)^        run: \|\n(.*?)(?=^      - |\Z)", TEXT):
        assert "${{" not in block, block[:80]


def test_the_secret_is_only_in_step_level_env() -> None:
    lines = TEXT.splitlines()
    uses = [i for i, line in enumerate(lines) if "secrets.DATABASE_URL" in line]
    assert uses
    for index in uses:
        assert lines[index - 1].strip() == "env:", index
        assert lines[index].startswith("          DATABASE_URL: "), index


def test_no_shell_tracing_and_actions_are_sha_pinned() -> None:
    assert "set -x" not in TEXT and "xtrace" not in TEXT
    for ref in re.findall(r"uses: (\S+)", TEXT):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), ref


def test_live_requires_confirmation_and_main() -> None:
    assert '"$CONFIRM_LIVE" != "LIVE"' in TEXT and '"$GIT_REF" != "refs/heads/main"' in TEXT
