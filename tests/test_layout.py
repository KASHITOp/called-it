"""FOUND-01: monorepo layout and import names."""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from tests.conftest import REPO_ROOT


@pytest.mark.parametrize("directory", ["data", "nowcaster", "tests", ".github/workflows"])
def test_monorepo_directories_exist(directory: str) -> None:
    assert (REPO_ROOT / directory).is_dir()


@pytest.mark.parametrize("module", ["calledit_data", "nowcaster"])
def test_workspace_packages_import(module: str) -> None:
    spec = importlib.util.find_spec(module)
    assert spec is not None
    assert spec.origin is not None, f"{module} must be a real package, not a namespace"


def test_no_top_level_data_package_is_installed() -> None:
    # Checked in an isolated interpreter (-I: no cwd, no PYTHON* env). Inside pytest the
    # repo root is on sys.path (--import-mode=prepend), which makes the bare ``data/``
    # directory look like a namespace package; what matters is that the installed
    # environment exposes no importable ``data`` package at all.
    probe = "import importlib.util, sys; sys.stdout.write(repr(importlib.util.find_spec('data')))"
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT.parent,
    )
    assert result.stdout == "None"


def test_data_member_is_not_a_regular_package() -> None:
    assert not (REPO_ROOT / "data" / "__init__.py").exists()
