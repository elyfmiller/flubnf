"""`flubnf bank` (build, verify, show): the committed auxiliary donor banks.
Build once with network, commit, then `verify` rebuilds from source and
reports drift. Mounted onto the root app by flubnf/cli.py."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

bank_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Build, inspect and verify the committed auxiliary donor banks.")


@bank_app.command("build")
def bank_build_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write here instead of data/banks/."),
):
    """Build a donor bank from its upstream source and commit it.

    Needs network access once. Everything afterwards reads the committed
    file, so a clone with no network still produces a spliced forecast and
    a Delphi outage on submission day is not a failure.
    """
    from datetime import datetime, timezone

    from flubnf import bank as bankmod
    if stream not in bankmod.STREAMS:
        console.print(f"[red]unknown stream {stream!r}; "
                      f"known: {', '.join(bankmod.STREAMS)}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]building[/bold] the {stream} donor bank")
    try:
        b, url = bankmod.build_from_source(stream)
    except Exception as e:
        console.print(f"[red]build failed: {e}[/red]")
        raise typer.Exit(1)
    prev = None
    try:
        prev, _ = bankmod.read(stream, out)
    except Exception:
        pass                       # no committed bank yet, or an unusable one
    man = bankmod.write(stream, b, source_url=url,
                        built_utc=datetime.now(timezone.utc).isoformat(
                            timespec="seconds"),
                        builder="flubnf bank build", banks_dir=out)
    console.print(f"  cells     {man['cells']:>9,}")
    console.print(f"  locations {man['location_count']:>9}")
    console.print(f"  span      {man['span'][0]} to {man['span'][1]}")
    console.print(f"  digest    {man['digest'][:32]}")
    console.print(f"  -> {bankmod.bank_path(stream, out)}")
    console.print(f"  -> {bankmod.manifest_path(stream, out)}")
    if prev is not None:
        d = bankmod.compare(prev, b)
        if d["identical"]:
            console.print("  [green]unchanged from the committed bank[/green]")
        else:
            console.print(f"  [yellow]changed: +{d['added']} cells, "
                          f"-{d['removed']}, {d['changed']} revised[/yellow]")
    console.print("\n[bold]commit both files.[/bold] The bank is only "
                  "reproducible if the manifest travels with it.")


@bank_app.command("verify")
def bank_verify_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    banks: Optional[Path] = typer.Option(
        None, "--banks", help="Read from here instead of data/banks/."),
):
    """Rebuild from source and say what moved against the committed bank.

    Exits non-zero when they differ, so a scheduled job can notice drift
    instead of a person having to remember to look.
    """
    from flubnf import bank as bankmod
    try:
        committed, man = bankmod.read(stream, banks)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]committed[/bold] {man['cells']:,} cells, built "
                  f"{man['built_utc']}, digest {man['digest'][:16]}")
    try:
        fresh, _ = bankmod.build_from_source(stream)
    except Exception as e:
        console.print(f"[red]could not rebuild from source: {e}[/red]")
        raise typer.Exit(1)
    d = bankmod.compare(committed, fresh)
    if d["identical"]:
        console.print("[green]identical: the committed bank is current[/green]")
        return
    console.print(f"[yellow]DRIFT[/yellow]  fresh {d['fresh_cells']:,} cells "
                  f"against committed {d['committed_cells']:,}")
    console.print(f"  added   {d['added']:>6}  {d['added_sample']}")
    console.print(f"  removed {d['removed']:>6}  {d['removed_sample']}")
    console.print(f"  revised {d['changed']:>6}")
    for c in d["changed_sample"]:
        console.print(f"    {c['cell']}: {c['committed']} -> {c['fresh']}")
    console.print("\nRebuild with `flubnf bank build "
                  f"{stream}` and commit both files, or leave it: a "
                  "committed bank is a frozen donor pool and staying on it "
                  "is a legitimate choice, so long as it is a choice.")
    raise typer.Exit(1)


@bank_app.command("show")
def bank_show_cmd(
    stream: str = typer.Argument(..., help="flusurv or iliplus"),
    banks: Optional[Path] = typer.Option(
        None, "--banks", help="Read from here instead of data/banks/."),
):
    """Print a committed bank's manifest, digest verified."""
    from flubnf import bank as bankmod
    try:
        _, man = bankmod.read(stream, banks)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    for k in ("stream", "built_utc", "source_url", "cells", "location_count",
              "span", "digest", "layout_version", "builder"):
        if k in man:
            console.print(f"  {k:<15} {man[k]}")
    console.print(f"  {'locations':<15} {', '.join(man['locations'])}")
