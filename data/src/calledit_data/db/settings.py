"""Runtime settings: the single storage switch and the environment guards.

``DATABASE_URL`` is a secret. It is held as a ``SecretStr``, validation errors never echo
the input (pydantic's hide-input option is on) and every error message here is a fixed string
that contains no part of the URL (RESEARCH Pitfall 9, threat T-01-03).

Environment rules (D-16, D-17, D-21):

- ``live`` requires a postgresql URL and always uses the schema ``calledit``. There is no
  fallback to SQLite or any other store.
- ``rehearsal`` always uses the schema ``calledit_rehearsal``.
- ``dev`` / ``test`` on Postgres must use ``calledit_dev``, ``calledit_ci`` or
  ``calledit_test_<hex>``. No non-live environment may ever name ``calledit``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

SCHEMA_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")
NON_LIVE_PG_SCHEMA_RE = re.compile(r"calledit_(dev|ci|test_[0-9a-f]{8,32})")
LIVE_SCHEMA = "calledit"
REHEARSAL_SCHEMA = "calledit_rehearsal"
DEV_DEFAULT_SCHEMA = "calledit_dev"
DEFAULT_DATABASE_URL = "sqlite:///data/local.db"

URL_PARSE_ERROR = "DATABASE_URL does not parse (the password may need percent-encoding)"
URL_BACKEND_ERROR = "DATABASE_URL backend must be sqlite or postgresql"
URL_HOST_ERROR = "DATABASE_URL has no host (the password may need percent-encoding)"

Env = Literal["dev", "test", "rehearsal", "live"]


class LiveContextError(RuntimeError):
    """A live write was attempted outside GitHub Actions on refs/heads/main."""


def validate_schema_identifier(name: str) -> str:
    """Return ``name`` if it is a safe lower-case SQL identifier, else raise ValueError.

    Every schema name that is ever interpolated into DDL passes through here first.
    """
    if not isinstance(name, str) or SCHEMA_RE.fullmatch(name) is None:
        raise ValueError("schema name must match ^[a-z_][a-z0-9_]{0,62}$")
    return name


def _normalise_url(raw: str) -> str:
    text = raw.strip()
    for prefix in ("postgres://", "postgresql://"):
        if text.startswith(prefix):
            text = "postgresql+psycopg://" + text[len(prefix) :]
            break
    try:
        url = make_url(text)
    except Exception:  # noqa: BLE001 - the message must never carry the value
        raise ValueError(URL_PARSE_ERROR) from None
    backend = url.get_backend_name()
    if backend not in ("sqlite", "postgresql"):
        raise ValueError(URL_BACKEND_ERROR)
    if backend == "postgresql":
        if not url.host:
            raise ValueError(URL_HOST_ERROR)
        # make_url is lenient: an unencoded '@', '#', '/' or bracket in the password still
        # yields *a* host. Cross-check with the stricter RFC 3986 split that libpq-style
        # parsers use; any disagreement means the password needs percent-encoding.
        try:
            split = urlsplit(text)
            split_host = split.hostname
            _ = split.port
        except ValueError:
            raise ValueError(URL_PARSE_ERROR) from None
        if not split_host or split_host != url.host.lower().strip("[]"):
            raise ValueError(URL_PARSE_ERROR)
    return text


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        validate_by_name=True,
        validate_by_alias=True,
    )

    database_url: SecretStr = Field(default=SecretStr(DEFAULT_DATABASE_URL))
    calledit_env: Env = "dev"
    db_schema: str | None = Field(default=None, validation_alias="CALLEDIT_DB_SCHEMA")
    ledger_dir: Path | None = Field(default=None, validation_alias="CALLEDIT_LEDGER_DIR")
    prereg_path: Path = Field(
        default=Path("PREREGISTRATION.md"), validation_alias="CALLEDIT_PREREG_PATH"
    )
    universe_path: Path = Field(
        default=Path("config/universe.toml"), validation_alias="CALLEDIT_UNIVERSE_PATH"
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _check_url(cls, value: Any) -> str:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if not isinstance(value, str):
            raise ValueError(URL_PARSE_ERROR)  # noqa: TRY004 - pydantic needs ValueError
        return _normalise_url(value)

    @field_validator("db_schema", mode="before")
    @classmethod
    def _check_schema(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return validate_schema_identifier(value)

    @model_validator(mode="after")
    def _check_env_rules(self) -> Settings:
        env = self.calledit_env
        backend = self.backend
        if env == "live":
            if backend != "postgresql":
                raise ValueError(
                    "CALLEDIT_ENV=live requires a postgresql DATABASE_URL; "
                    "SQLite is never used for live (D-17)"
                )
            if self.db_schema not in (None, LIVE_SCHEMA):
                raise ValueError("CALLEDIT_ENV=live always uses the schema calledit")
            if self.ledger_dir is not None:
                raise ValueError("CALLEDIT_LEDGER_DIR cannot be overridden when CALLEDIT_ENV=live")
            return self
        if self.db_schema == LIVE_SCHEMA:
            raise ValueError("only CALLEDIT_ENV=live may use the schema calledit (D-21)")
        if env == "rehearsal":
            if self.db_schema not in (None, REHEARSAL_SCHEMA):
                raise ValueError("CALLEDIT_ENV=rehearsal always uses the schema calledit_rehearsal")
            return self
        if backend == "postgresql":
            if env == "test" and self.db_schema is None:
                raise ValueError(
                    "CALLEDIT_ENV=test on postgresql requires CALLEDIT_DB_SCHEMA=calledit_test_<hex>"
                )
            schema = self.db_schema or DEV_DEFAULT_SCHEMA
            if NON_LIVE_PG_SCHEMA_RE.fullmatch(schema) is None:
                raise ValueError(
                    "dev/test postgresql schema must match ^calledit_(dev|ci|test_[0-9a-f]{8,32})$"
                )
        return self

    @property
    def backend(self) -> Literal["sqlite", "postgresql"]:
        name = make_url(self.database_url.get_secret_value()).get_backend_name()
        return "postgresql" if name == "postgresql" else "sqlite"

    @property
    def effective_schema(self) -> str | None:
        """The Postgres schema every table lives in; ``None`` on SQLite."""
        if self.backend == "sqlite":
            return None
        if self.calledit_env == "live":
            return LIVE_SCHEMA
        if self.calledit_env == "rehearsal":
            return REHEARSAL_SCHEMA
        return self.db_schema or DEV_DEFAULT_SCHEMA

    @property
    def effective_ledger_dir(self) -> Path:
        if self.calledit_env == "live":
            return Path("ledger")
        if self.ledger_dir is not None:
            return self.ledger_dir
        if self.calledit_env == "rehearsal":
            return Path("build/rehearsal/ledger")
        return Path("build/dev/ledger")


def get_settings() -> Settings:
    """Build settings from the environment and ``.env`` (never cached: tests change env)."""
    return Settings()


def require_live_write_context(settings: Settings) -> None:
    """Refuse a live write unless it runs in GitHub Actions on refs/heads/main."""
    if settings.calledit_env != "live":
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise LiveContextError("live writes run only inside GitHub Actions")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise LiveContextError("live writes run only on refs/heads/main")
