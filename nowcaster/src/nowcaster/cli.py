"""``nowcast``: the CALLED IT. command line.

Research and educational use only; nothing here is a buy or sell recommendation.
Every failure exits non-zero with a fixed message that never contains the DATABASE_URL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from calledit_data.calendar.fiscal import FiscalQuarter
from calledit_data.calendar.reveal import earliest_plausible_reveal
from calledit_data.calendar.tz import to_ist
from calledit_data.db.check import env_file_lines, run_db_check
from calledit_data.db.engine import make_engine
from calledit_data.db.settings import LiveContextError, Settings, get_settings
from calledit_data.seed.loader import (
    CANONICAL_SEED_PATH,
    SeedCompanyRules,
    SeedError,
    load_seed,
)
from pydantic import ValidationError

from nowcaster.clock import now_utc
from nowcaster.ledger.canonical import CanonicalError, format_ts
from nowcaster.ledger.chain import ForkError, RecordError
from nowcaster.ledger.export import ExportError, export_ledger
from nowcaster.rules import RulesError, append_rules_record
from nowcaster.universe import Break, Company, Universe, UniverseError, load_universe

app = typer.Typer(
    name="nowcast",
    help="CALLED IT. earnings nowcaster (research and educational use only).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
db_app = typer.Typer(help="Database checks.", no_args_is_help=True)
ledger_app = typer.Typer(help="The hash-chained ledger.", no_args_is_help=True)
seed_app = typer.Typer(help="Hand-curated seed data.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(ledger_app, name="ledger")
app.add_typer(seed_app, name="seed")


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


def _universe_or_exit(settings: Settings, command: str) -> Universe:
    try:
        return load_universe(settings.universe_path)
    except UniverseError as exc:
        typer.echo(f"{command}: refused: {exc}", err=True)
        raise typer.Exit(1) from None


def _show(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return ", ".join(_show(v) for v in value) if value else "none"
    if value is None:
        return "none"
    return str(value)


def _company_lines(company: Company) -> list[str]:
    state = "enabled" if company.enabled else "disabled"
    history = tuple(f"{h.symbol} until {h.until.isoformat()}" for h in company.symbol_history)
    return [
        f"company {company.ticker} ({state})",
        f"  name: {company.name}",
        f"  isin: {company.isin}",
        f"  isin_confirmed: {_show(company.isin_confirmed)}",
        f"  enabled: {_show(company.enabled)}",
        f"  revenue_basis: {company.revenue_basis}",
        f"  reveal_offset_days: {company.reveal_offset_days}",
        f"  has_business_update: {_show(company.has_business_update)}",
        f"  gst_states: {_show(company.gst_states)}",
        f"  gst_states_basis: {company.gst_states_basis}",
        f"  trends_terms: {_show(company.trends_terms)}",
        f"  apple_app_ids: {_show(company.apple_app_ids)}",
        f"  play_package_ids: {_show(company.play_package_ids)}",
        f"  labels: {_show(company.labels)}",
        f"  symbol_history: {_show(history)}",
        f"  break_ids: {_show(company.break_ids)}",
    ]


def _break_lines(brk: Break) -> list[str]:
    lines = [f"break {brk.id}", f"  kind: {brk.kind}", f"  applies_to: {_show(brk.applies_to)}"]
    if brk.kind == "quarter_range":
        lines += [f"  start_q: {brk.start_q}", f"  end_q: {brk.end_q}"]
    else:
        lines.append(f"  effective: {_show(brk.effective and brk.effective.isoformat())}")
    lines += [
        f"  source_url: {brk.source_url}",
        f"  source_note: {brk.source_note}",
        f"  confirmed: {_show(brk.confirmed)}",
    ]
    return lines


@app.command("universe")
def universe() -> None:
    """List every company in the universe config (disabled ones marked), breaks and hash."""
    settings = _settings_or_exit()
    loaded = _universe_or_exit(settings, "universe")
    typer.echo(f"universe: {settings.universe_path.as_posix()}")
    typer.echo(f"schema_version: {loaded.schema_version}")
    typer.echo(f"basis_note: {loaded.basis_note}")
    for company in loaded.companies:
        for line in _company_lines(company):
            typer.echo(line)
    for brk in loaded.breaks:
        for line in _break_lines(brk):
            typer.echo(line)
    typer.echo(f"universe_sha256: {loaded.universe_sha256}")


@app.command("calendar")
def calendar(
    quarter: Annotated[str, typer.Option("--quarter", help="Fiscal quarter, e.g. Q3FY27.")],
) -> None:
    """Show each enabled company's reveal calendar for a quarter (no as-of override)."""
    try:
        fq = FiscalQuarter.parse(quarter)
    except ValueError as exc:
        typer.echo(f"calendar: refused: {exc}", err=True)
        raise typer.Exit(2) from None
    settings = _settings_or_exit()
    loaded = _universe_or_exit(settings, "calendar")
    typer.echo(f"quarter: {fq.label} ({fq.start.isoformat()}..{fq.end.isoformat()})")
    for company in loaded.enabled():
        epr = earliest_plausible_reveal(fq, company.reveal_offset_days)
        ist = to_ist(epr).strftime("%Y-%m-%d %H:%M:%S IST")
        typer.echo(f"company {company.ticker}")
        # No reveal events are stored before Plan 01-04, so every quarter is still expected.
        typer.echo("  business_update_at: none")
        typer.echo("  results_at: none")
        typer.echo("  reveal_at: none")
        typer.echo("  status: expected")
        typer.echo(
            f"  earliest_plausible_reveal: {format_ts(epr)} ({ist}; "
            f"quarter end + {company.reveal_offset_days}d at 00:00 IST)"
        )
    typer.echo(f"universe_sha256: {loaded.universe_sha256}")


@seed_app.command("load")
def seed_load(
    csv_path: Annotated[
        Path, typer.Option("--csv", help="Seed CSV (rehearsal/live: only the canonical file).")
    ] = CANONICAL_SEED_PATH,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate the whole file; insert nothing.")
    ] = False,
    require_verified: Annotated[
        bool, typer.Option("--require-verified", help="Treat any verified = N row as an error.")
    ] = False,
) -> None:
    """Validate the seed CSV and load it into the point-in-time store in one transaction."""
    settings = _settings_or_exit()
    loaded = _universe_or_exit(settings, "seed load")
    rules = {
        c.ticker: SeedCompanyRules(isin=c.isin, has_business_update=c.has_business_update)
        for c in loaded.companies
    }
    if not csv_path.is_file():
        typer.echo(f"seed load: refused: no such file: {csv_path.as_posix()}", err=True)
        raise typer.Exit(1)
    engine = None if dry_run else make_engine(settings)
    try:
        report = load_seed(
            engine,
            csv_path,
            rules,
            settings,
            now=now_utc(),
            dry_run=dry_run,
            require_verified=require_verified,
        )
    except (SeedError, LiveContextError) as exc:
        typer.echo(f"seed load: refused: {exc}", err=True)
        raise typer.Exit(1) from None
    except Exception as exc:  # noqa: BLE001 - DB errors: class name only, never the URL
        typer.echo(
            f"seed load: failed ({type(exc).__name__}); nothing inserted. "
            "Is the store migrated? run: uv run alembic upgrade head",
            err=True,
        )
        raise typer.Exit(1) from None
    finally:
        if engine is not None:
            engine.dispose()
    if report.errors:
        for error in report.errors:
            typer.echo(f"  {error}", err=True)
        typer.echo(
            f"seed load: refused: {len(report.errors)} error(s) in {report.rows_seen} rows; "
            "nothing inserted",
            err=True,
        )
        raise typer.Exit(1)
    mode = " (dry run: nothing inserted)" if report.dry_run else ""
    typer.echo(
        f"seed load{mode}: {report.rows_seen} rows seen, "
        f"{report.observations_inserted} observations inserted, "
        f"{report.events_inserted} reveal events inserted"
    )


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
