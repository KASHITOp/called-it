"""Postgres test fixtures: guarded scratch schemas on the database named by TEST_DATABASE_URL.

TEST_DATABASE_URL may be the live Supabase project, so everything here is built around one rule:
this suite may only ever create, migrate or drop a schema named ``calledit_test_<hex>``. The
live schema (``calledit``) and the rehearsal schema (``calledit_rehearsal``) are unreachable:

- ``assert_scratch_schema`` is a fullmatch on ``calledit_test_[0-9a-f]{8,32}`` and is called
  before every CREATE and every DROP.
- ``_scratch_guard_selftest`` is a session-scoped autouse fixture that proves the guard refuses
  ``calledit`` and ``calledit_rehearsal`` (and other bad names) BEFORE any engine exists. If it
  does not, the whole session is aborted with ``pytest.exit``. ``pg_scratch_factory`` requests it
  explicitly, so the ordering does not depend on autouse alone.
- A failure here never prints the URL, a host, a user or a password: messages are fixed strings
  plus the exception class name.

Without TEST_DATABASE_URL every postgres test is skipped ("TEST_DATABASE_URL not set"). With
``CALLEDIT_REQUIRE_PG=1`` (CI) a missing URL is an error instead, so skips cannot hide a hole.

The URL comes from the environment, falling back to the ``TEST_DATABASE_URL`` key of the
git-ignored ``.env`` at the repository root (read through pydantic-settings, never printed).
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
import sqlalchemy as sa
from alembic import command
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import Settings
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.conftest import REPO_ROOT, alembic_config

SCRATCH_RE = re.compile(r"calledit_test_[0-9a-f]{8,32}")
REQUIRE_PG_VAR = "CALLEDIT_REQUIRE_PG"
URL_VAR = "TEST_DATABASE_URL"

# Names the guard must refuse. ``calledit`` is the live schema, ``calledit_rehearsal`` the
# rehearsal one; the rest are near misses an unanchored or case-insensitive check would admit.
REFUSED_NAMES = (
    "calledit",
    "calledit_rehearsal",
    "calledit_dev",
    "calledit_ci",
    "public",
    "",
    "calledit_test_",
    "calledit_test_xyz",
    "calledit_test_0123456",
    "CALLEDIT_TEST_0123ABCD",
    "calledit_test_0123abcd\n",
    "calledit_test_0123abcd; DROP SCHEMA calledit CASCADE",
    'calledit_test_0123abcd"',
    "x_calledit_test_0123abcd",
)


class ScratchSchemaError(RuntimeError):
    """A schema name is not a ``calledit_test_<hex>`` scratch schema."""


def assert_scratch_schema(name: str) -> str:
    """Return ``name`` if it is a scratch schema name, else raise ``ScratchSchemaError``."""
    if not isinstance(name, str) or SCRATCH_RE.fullmatch(name) is None:
        raise ScratchSchemaError("not a calledit_test_<hex> scratch schema; refusing to touch it")
    return name


class _DotenvTestUrl(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    test_database_url: SecretStr | None = None


def _test_database_url() -> str | None:
    value = os.environ.get(URL_VAR, "").strip()
    if value:
        return value
    try:
        secret = _DotenvTestUrl().test_database_url
    except Exception:  # noqa: BLE001 - never echo the value
        return None
    text = secret.get_secret_value().strip() if secret is not None else ""
    return text or None


def require_pg() -> bool:
    return os.environ.get(REQUIRE_PG_VAR) == "1"


@dataclass(frozen=True)
class ScratchDb:
    """One migrated scratch schema: its name, a schema-translated engine and its settings."""

    schema: str
    engine: sa.Engine
    settings: Settings

    def q(self, table: str) -> str:
        """Schema-qualified, validated table name for raw SQL."""
        assert_scratch_schema(self.schema)
        if re.fullmatch(r"[a-z_]+", table) is None:
            raise ValueError("bad table name")
        return f"{self.schema}.{table}"

    def head(self) -> tuple[int, str] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.text(f"SELECT seq, hash FROM {self.q('predictions')} ORDER BY seq DESC LIMIT 1")
            ).first()
        return None if row is None else (row[0], row[1])


@dataclass
class ScratchFactory:
    """Creates guarded scratch schemas and drops every one of them at session end."""

    url: str
    created: list[ScratchDb] = field(default_factory=list)
    dropped: set[str] = field(default_factory=set)

    def create(self) -> ScratchDb:
        name = assert_scratch_schema("calledit_test_" + secrets.token_hex(6))
        try:
            settings = Settings(
                _env_file=None, database_url=self.url, calledit_env="test", db_schema=name
            )
        except Exception as exc:  # noqa: BLE001 - never echo the value
            pytest.fail(
                f"TEST_DATABASE_URL is not usable as a settings URL ({type(exc).__name__})",
                pytrace=False,
            )
        if settings.backend != "postgresql":
            pytest.fail("TEST_DATABASE_URL must be a postgresql URL", pytrace=False)
        assert settings.effective_schema == name
        engine = make_engine(settings)
        scratch = ScratchDb(schema=name, engine=engine, settings=settings)
        self.created.append(scratch)
        try:
            with engine.connect() as conn:
                cfg = alembic_config()
                cfg.attributes["connection"] = conn
                cfg.attributes["schema"] = name
                command.upgrade(cfg, "head")
                conn.commit()
        except Exception as exc:  # noqa: BLE001 - class name only, never the URL
            pytest.fail(
                f"could not migrate scratch schema {name} ({type(exc).__name__})", pytrace=False
            )
        return scratch

    def drop(self, scratch: ScratchDb) -> None:
        name = assert_scratch_schema(scratch.schema)
        if name in self.dropped:
            return
        with scratch.engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        scratch.engine.dispose()
        self.dropped.add(name)

    def drop_all(self) -> None:
        errors: list[str] = []
        for scratch in reversed(self.created):
            try:
                self.drop(scratch)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{scratch.schema}: {type(exc).__name__}")
        if errors:
            pytest.fail("could not drop scratch schema(s): " + ", ".join(errors), pytrace=False)
        self.verify_gone()

    def verify_gone(self) -> None:
        """Final query: none of the schemas this session created is left behind."""
        if not self.created:
            return
        names = [scratch.schema for scratch in self.created]
        engine = sa.create_engine(
            self.url, poolclass=sa.pool.NullPool, connect_args={"prepare_threshold": None}
        )
        left: list[str] = []
        try:
            with engine.connect() as conn:
                for name in names:
                    found = conn.execute(
                        sa.text("SELECT nspname FROM pg_namespace WHERE nspname = :name"),
                        {"name": assert_scratch_schema(name)},
                    ).first()
                    if found is not None:
                        left.append(name)
        finally:
            engine.dispose()
        if left:
            pytest.fail("scratch schema(s) left behind: " + ", ".join(sorted(left)), pytrace=False)


@pytest.fixture(scope="session", autouse=True)
def _scratch_guard_selftest() -> None:
    """Prove the guard refuses every protected name before anything can reach a database."""
    for name in REFUSED_NAMES:
        try:
            assert_scratch_schema(name)
        except ScratchSchemaError:
            continue
        pytest.exit(
            "scratch-schema guard self-test failed: it admitted a protected name; "
            "no database was contacted",
            returncode=1,
        )
    try:
        assert_scratch_schema("calledit_test_" + "0123456789ab")
    except ScratchSchemaError:
        pytest.exit(
            "scratch-schema guard self-test failed: it refused a valid scratch name",
            returncode=1,
        )


@pytest.fixture(scope="session")
def pg_scratch_factory(_scratch_guard_selftest: None) -> Iterator[ScratchFactory]:
    url = _test_database_url()
    if url is None:
        if require_pg():
            pytest.fail(
                f"{REQUIRE_PG_VAR}=1 but {URL_VAR} is not set: refusing to skip", pytrace=False
            )
        pytest.skip("TEST_DATABASE_URL not set")
    factory = ScratchFactory(url=url)
    try:
        yield factory
    finally:
        factory.drop_all()


@pytest.fixture(scope="session")
def pg_scratch(pg_scratch_factory: ScratchFactory) -> ScratchDb:
    """One migrated scratch schema shared by the whole session (dropped at the end)."""
    return pg_scratch_factory.create()


@pytest.fixture
def fresh_scratch(pg_scratch_factory: ScratchFactory) -> Iterator[ScratchDb]:
    """A private migrated scratch schema for one test (an empty chain), dropped afterwards."""
    scratch = pg_scratch_factory.create()
    try:
        yield scratch
    finally:
        pg_scratch_factory.drop(scratch)
