"""LEAK-02: the leakage suite can fail. This is the proof that it has teeth.

For each deliberately leaky reader this runs the whole ``tests/leakage`` suite in a
subprocess with ``--reader=<variant>`` and requires pytest exit code EXACTLY 1 (tests failed).
Anything else is not "caught": 2 (interrupted), 3 (internal error), 4 (usage error, e.g. an
unknown option) and 5 (no tests collected) would all look like a non-zero exit while proving
nothing. The correct reader is run as the control and must exit 0.

The subprocess uses absolute paths and an empty temp cwd, so a developer ``.env`` in the repo
root is never read, and ``-p no:cacheprovider`` keeps it from writing into the tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.leakage.leaky_readers import LEAKY_READERS

pytestmark = pytest.mark.slow

LEAKAGE_DIR = REPO_ROOT / "tests" / "leakage"
TAIL = 2000


def _run_leakage_suite(reader: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "CALLEDIT_ENV"}}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(LEAKAGE_DIR),
            f"--reader={reader}",
            "-q",
            "-p",
            "no:cacheprovider",
            "--hypothesis-profile=ci",
            "-m",
            "not postgres",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=170,
        check=False,
    )


@pytest.mark.parametrize("variant", sorted(LEAKY_READERS))
def test_suite_fails_on_leaky_reader(variant: str, tmp_path: Path) -> None:
    result = _run_leakage_suite(variant, tmp_path)
    assert result.returncode == 1, (
        f"--reader={variant}: expected pytest exit code 1 (tests failed), "
        f"got {result.returncode}. Exit codes 2-5 (interrupted, internal error, usage error, "
        f"no tests) do NOT count as the suite catching the leak.\n"
        f"--- last {TAIL} chars of stdout ---\n{result.stdout[-TAIL:]}\n"
        f"--- last {TAIL} chars of stderr ---\n{result.stderr[-TAIL:]}"
    )
    assert " failed" in result.stdout.splitlines()[-1], result.stdout[-TAIL:]


def test_suite_passes_on_correct_reader(tmp_path: Path) -> None:
    result = _run_leakage_suite("correct", tmp_path)
    assert result.returncode == 0, (
        f"--reader=correct: expected exit code 0, got {result.returncode}.\n"
        f"--- last {TAIL} chars of stdout ---\n{result.stdout[-TAIL:]}\n"
        f"--- last {TAIL} chars of stderr ---\n{result.stderr[-TAIL:]}"
    )


def test_every_leaky_variant_is_covered() -> None:
    assert sorted(LEAKY_READERS) == [
        "leaky-ingested",
        "leaky-le",
        "leaky-nofilter",
        "leaky-period",
    ]


def test_a_usage_error_is_not_counted_as_caught(tmp_path: Path) -> None:
    """An unknown --reader is pytest exit code 4, which the assertions above reject."""
    result = _run_leakage_suite("not-a-reader", tmp_path)
    assert result.returncode == 4, result.stdout[-TAIL:] + result.stderr[-TAIL:]
