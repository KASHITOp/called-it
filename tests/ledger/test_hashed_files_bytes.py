"""The files whose bytes are hashed into the ledger must be byte-stable (D-19).

For each hashed file: git must not normalise its line endings (``text`` unset), the working
tree must equal the committed blob, and it must contain no carriage return. The preregistration
is also checked against the code it describes (field lists, reason codes, the statements the
user froze), so the text cannot drift from what the code does.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from nowcaster.ledger.records import GAP_FIELDS, PREDICTION_FIELDS, RULES_FIELDS

from nowcaster import baseline as baseline_module
from nowcaster import lock as lock_module
from tests.conftest import REPO_ROOT

HASHED_FILES = (
    "PREREGISTRATION.md",
    "config/universe.toml",
    "data/seed/quarterly_revenue.csv",
    "tests/fixtures/hash_vectors.json",
)
PREREG = REPO_ROOT / "PREREGISTRATION.md"


def _git(*args: str) -> bytes:
    done = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, check=False, timeout=60
    )
    assert done.returncode == 0, f"git {' '.join(args)} failed: {done.stderr.decode()[:200]}"
    return done.stdout


@pytest.mark.parametrize("path", HASHED_FILES)
def test_git_does_not_normalise_line_endings(path: str) -> None:
    out = _git("check-attr", "text", "--", path).decode().strip()
    assert out.endswith(": text: unset"), out


@pytest.mark.parametrize("path", HASHED_FILES)
def test_working_tree_bytes_equal_the_committed_blob(path: str) -> None:
    assert (REPO_ROOT / path).read_bytes() == _git("cat-file", "blob", f"HEAD:{path}")


@pytest.mark.parametrize("path", HASHED_FILES)
def test_no_carriage_return_in_hashed_file(path: str) -> None:
    assert b"\r" not in (REPO_ROOT / path).read_bytes()


# --- the preregistration against the code ---------------------------------------------------


def _text() -> str:
    return PREREG.read_bytes().decode("ascii")


def test_prereg_is_ascii_lf_and_ends_with_one_newline() -> None:
    data = PREREG.read_bytes()
    assert data.isascii() and b"\r" not in data
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


def test_prereg_has_the_twelve_numbered_sections_in_order() -> None:
    numbers = [int(n) for n in re.findall(r"(?m)^## (\d+)\. ", _text())]
    assert numbers == list(range(1, 13))


def _listed_fields(kind: str) -> tuple[str, ...]:
    match = re.search(rf"(?m)^- fields of {kind}: (.+)$", _text())
    assert match is not None, kind
    return tuple(match.group(1).split(", "))


def test_prereg_field_lists_match_records() -> None:
    assert _listed_fields("rules") == RULES_FIELDS
    assert _listed_fields("prediction") == PREDICTION_FIELDS
    assert _listed_fields("gap") == GAP_FIELDS


def test_prereg_lists_exactly_the_baseline_reason_codes() -> None:
    codes = {
        baseline_module.REASON_MISSING,
        baseline_module.REASON_UNVERIFIED,
        baseline_module.REASON_INVALID_BASE,
        baseline_module.REASON_TIED,
    }
    assert codes == {
        "missing_seed_quarter",
        "unverified_seed_quarter",
        "invalid_base_sum",
        "tied_available_at",
    }
    text = _text()
    for code in codes:
        assert f"- `{code}`:" in text, code


def test_prereg_names_every_guard_refusal_that_the_code_emits() -> None:
    source = Path(lock_module.__file__).read_text(encoding="utf-8")
    text = _text()
    for name in (
        "quarter_not_started",
        "past_earliest_plausible_reveal",
        "reveal_event_known",
        "invalid_reveal_event",
        "lock_before_rules",
    ):
        assert name in source, f"{name} no longer exists in lock.py"
        assert f"`{name}`" in text, f"{name} missing from the preregistration"


def test_prereg_states_what_invalid_base_sum_really_is() -> None:
    text = _text()
    assert "the growth denominator is zero or negative" in text
    assert "NOT a check that components add up" in text


def test_prereg_states_the_frozen_wording() -> None:
    text = _text()
    required = (
        (
            "GST 2.0 (22 Sep 2025) is flagged, not adjusted; treatment decided in Phase 3 and "
            "recorded as a dated amendment."
        ),
        baseline_module.ETERNAL_LABEL,
        "`start_q` = Q2 FY26 to `end_q` = Q3 FY26",
        "Q1 FY26 is the last pre-break quarter",
        "INCLUDES gold-ingot and bullion sales",
        "TITAN is noisy against a 3% band",
        "changes `universe_sha256`",
        "The official call for a company and quarter is the last valid lock",
        "Earlier entries are never overwritten, edited or deleted.",
        "Fully trust-minimised verification requires your own Bitcoin node.",
        baseline_module.MODEL_VERSION,
    )
    for needle in required:
        assert needle in text, needle


def test_prereg_makes_no_recommendation_outside_the_disclaimer() -> None:
    pattern = re.compile(r"(?i)\b(buy|sell|hold|price target|outperform|underperform)\b")
    hits = [line for line in _text().splitlines() if pattern.search(line)]
    assert len(hits) == 1 and "no buy or sell calls" in hits[0], hits
