"""``nowcast``: the CALLED IT. command line.

Research and educational use only; nothing here is a buy or sell recommendation.
Every failure exits non-zero with a fixed message that never contains the DATABASE_URL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from calledit_data.db.check import env_file_lines, run_db_check
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import LiveContextError, Settings, get_settings
from pydantic import ValidationError

from nowcaster.clock import now_utc
from nowcaster.ledger.canonical import CanonicalError
from nowcaster.ledger.chain import ForkError, RecordError
from nowcaster.ledger.export import ExportError, export_ledger
from nowcaster.rules import RulesError, append_rules_record

app = typer.Typer(
    name="nowcast",
    help="CALLED IT. earnings nowcaster (research and educational use only).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
db_app = typer.Typer(help="Database checks.", no_args_is_help=True)
ledger_app = typer.Typer(help="The hash-chained ledger.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(ledger_app, name="ledger")


def _settings_or_exit(*, report_env: bool = False) -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        if report_env:
            for line in env_file_lines():
                typer.echo(line)
        for error in exc.errors():
            typer.echo(f"settings error: {error['msg']}", err=True)
        if report_env:
            typer.echo("result: FAIL")
        raise typer.Exit(2) from None


@db_app.command("check")
def db_check(
    connect_only: Annotated[
        bool, typer.Option("--connect-only", help="Only test the connection.")
    ] = False,
) -> None:
    """Report backend, .env presence, schema, connectivity and ledger triggers."""
    settings = _settings_or_exit(report_env=True)
    report = run_db_check(settings, connect_only=connect_only)
    for line in report.lines:
        typer.echo(line)
    if not report.ok:
        raise typer.Exit(1)


@app.command("rules")
def rules(
    document: Annotated[
        Path | None, typer.Option("--document", help="Preregistration file (non-live only).")
    ] = None,
    universe: Annotated[
        Path | None, typer.Option("--universe", help="Universe config (non-live only).")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the payload; append nothing.")
    ] = False,
) -> None:
    """Append a rules record (SHA-256 of the preregistration and the universe config)."""
    settings = _settings_or_exit()
    try:
        result = append_rules_record(settings, document, universe, now_utc(), dry_run)
    except (RulesError, LiveContextError, ForkError, RecordError, CanonicalError) as exc:
        typer.echo(f"rules: refused: {exc}", err=True)
        raise typer.Exit(1) from None
    if result.dry_run:
        typer.echo("dry run: nothing appended")
        typer.echo(result.payload_canonical)
        return
    assert result.appended is not None
    typer.echo(f"appended rules record seq {result.appended.seq} hash {result.appended.hash}")


@ledger_app.command("export")
def ledger_export(
    out: Annotated[
        Path | None, typer.Option("--out", help="Output directory (default per CALLEDIT_ENV).")
    ] = None,
) -> None:
    """Verify the chain and write ledger.jsonl (append-only: history is a byte-prefix)."""
    settings = _settings_or_exit()
    out_dir = out if out is not None else settings.effective_ledger_dir
    engine = make_engine(settings)
    try:
        report = export_ledger(engine, out_dir)
    except ExportError as exc:
        typer.echo(f"ledger export: refused: {exc}", err=True)
        raise typer.Exit(1) from None
    except Exception as exc:  # noqa: BLE001 - DB errors: class name only
        typer.echo(f"ledger export: failed ({type(exc).__name__})", err=True)
        raise typer.Exit(1) from None
    finally:
        engine.dispose()
    typer.echo(
        f"exported {report.records} record(s) to {report.path.as_posix()} "
        f"(+{report.appended_lines} line(s)); head seq {report.head_seq} hash {report.head_hash}"
    )


if __name__ == "__main__":
    app()
