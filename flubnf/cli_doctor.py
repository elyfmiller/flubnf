"""`flubnf doctor` and `flubnf knobs`: the environment report and the model
knob registry. Registered onto the root app by flubnf/cli.py."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def doctor(
    online: bool = typer.Option(
        False, "--online",
        help="Include network checks (Delphi Epidata and GitHub).",
    ),
    # Accepted and ignored: the checks read no config, workspace or Mac
    # Studio flag (the legacy workspace CLI that used them is gone), and old
    # scripts pass them.
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", hidden=True),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", hidden=True),
    pre_studio: bool = typer.Option(False, "--pre-studio", hidden=True),
):
    """Diagnose the environment and dependencies.

    Catches the common showstoppers (broken venv, missing engine or hub
    clone, missing BNG2.pl, NumPy 2.0 / pybnf incompat patch missing)
    before they bite mid-run. Exits 1 when any check fails.
    """
    from . import doctor as docmod
    if config is not None or workspace is not None or pre_studio:
        console.print("[dim]--config, --workspace and --pre-studio are "
                      "ignored: the doctor reads no config.[/dim]")
    rep = docmod.run_doctor(online=online)

    table = Table(title="FluBNF doctor")
    table.add_column("status"); table.add_column("check"); table.add_column("detail")
    color = {
        docmod.Status.OK: "green",
        docmod.Status.WARN: "yellow",
        docmod.Status.FAIL: "red",
    }
    for c in rep.checks:
        table.add_row(
            f"[{color[c.status]}]{c.status.value}[/]",
            c.name, c.detail,
        )
    console.print(table)

    # Surface hints below the table for any WARN/FAIL.
    hints = [c for c in rep.checks if c.hint and c.status is not docmod.Status.OK]
    if hints:
        console.print("\n[bold]hints[/]")
        for c in hints:
            console.print(f"  • [{color[c.status]}]{c.name}[/]: {c.hint}")

    console.print(
        f"\n[bold]summary:[/] "
        f"{len(rep.checks) - rep.n_fail - rep.n_warn} ok, "
        f"[yellow]{rep.n_warn} warn[/], "
        f"[red]{rep.n_fail} fail[/]"
    )
    if rep.n_fail:
        raise typer.Exit(code=1)


def engine_update(
    path: Optional[Path] = typer.Option(
        None, "--path",
        help="The engine checkout (default: the one the console uses)."),
    fetch: bool = typer.Option(
        True, "--fetch/--no-fetch",
        help="Fetch the production commit from GitHub when it is not on "
             "disk yet."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Print nothing when the engine is already the production "
             "build."),
):
    """Move the particle-filter engine to the production build, when that
    is safe.

    Only a clean git checkout on the production branch that is behind the
    production commit moves, by fast-forward. Anything else is left as it
    is and the reason is printed. The launchers run this on every open.
    Always exits 0: an engine left where it is never blocks a launch."""
    from app.core import engine_update as EU
    out = EU.update(path, fetch=fetch)
    EU.save(out)
    if quiet and out["status"] in ("production", "no-engine"):
        return
    typer.echo(f"  engine: {out['message']}")


def knobs(
    as_json: bool = typer.Option(False, "--json",
                                 help="Print the registry as JSON."),
):
    """List the model knobs: shipped value, allowed range, the models each
    affects and its class (run or method), then the locked settings.

    Any value other than the shipped one marks a run as modified."""
    import json

    from app.core import knobs as K
    if as_json:
        locked = [{"key": l.key, "value": l.value, "source": l.source,
                   "why": l.why} for l in K.LOCKED]
        typer.echo(json.dumps({"knobs": K.describe(), "locked": locked},
                              indent=1, default=list))
        return
    names = {"pf": "Oracle SIHRS", "analogue": "Groundhog"}
    table = Table(title="Model knobs")
    table.add_column("knob", no_wrap=True)
    for col in ("shipped", "range", "affects", "class"):
        table.add_column(col)
    for r in K.describe():
        d = r["default"]
        shown = (f"[{', '.join(f'{x:g}' for x in d)}]" if isinstance(d, list)
                 else f"{d:,}" if r["kind"] == "int"
                 else ("on" if d else "off") if isinstance(d, bool) else str(d))
        table.add_row(r["key"], shown + (f" {r['unit']}" if r["unit"] else ""),
                      r["range"], ", ".join(names[m] for m in r["affects"]),
                      r["class"])
    console.print(table)
    locked = Table(title="Locked")
    for col in ("setting", "value", "why"):
        locked.add_column(col)
    for l in K.LOCKED:
        locked.add_row(l.key, str(l.value), l.why)
    console.print(locked)
