"""`flubnf oracle` (backfill, reproduce) and `flubnf site build`: the
verification and publication commands. Mounted onto the root app by
flubnf/cli.py.

oracle is verification only: backfill a stored season's Oracle SIHRS into a
NEW root from its samples (no refit, no engine) and score it beside the
registered screen (docs/ORACLE-SIHRS.md). Seasons are run by a replay.
site builds the public static site from the lab's own state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

oracle_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Verification only: backfill a stored season into a new root and "
         "reproduce the registered screen's relWIS with the app's scorer, "
         "no refit. A season is run and viewed by a console replay "
         "(flubnf retro, or the Retrospective tab).")


@oracle_app.command("backfill")
def oracle_backfill_cmd(
    season: str = typer.Argument(..., help="The season the root holds, e.g. 2025-26."),
    source: Path = typer.Option(
        ..., "--source", help="A season root of stored weeks. Read only."),
    out: Path = typer.Option(
        ..., "--out",
        help="A NEW season root to write. Never the source or a path under "
             "it, never under app/state, never a non-empty tree without --force."),
    force: bool = typer.Option(
        False, "--force", help="Write into a non-empty --out."),
    keep_filter: bool = typer.Option(
        True, "--keep-filter/--no-keep-filter",
        help="Keep the source's pf verbatim under the research key pf_filter "
             "beside the member (a research root; a replay's stored week "
             "does not carry it)."),
):
    """Compute the Oracle SIHRS for every stored week of a season root, from
    the stored samples and no refit, into a new root: a verification that
    the app's code reproduces the registered screen, not how a season is
    run or viewed (that is a console replay, flubnf retro).

    Each week is read through the storage boundary and written back
    through it: pf the member (the submitted seed's samples), pf_filter
    the source's pf, analogue verbatim, the sidecar, oracle.json and the
    donor pool beside it. The hub this process reads (FLUBNF_HUB) supplies
    the vintages the pools are built from.
    """
    from app.core import oracle_backfill as obf
    try:
        res = obf.backfill_season(
            source, out, season, force=force, keep_filter=keep_filter,
            progress=lambda a, m: console.print(f"  {a}  {m}"))
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]{season}[/bold]: {len(res['weeks'])} weeks backfilled "
                  f"-> {res['out']} in {res['seconds']}s"
                  + (f"; skipped (no pf block): {', '.join(res['skipped'])}"
                     if res["skipped"] else ""))


@oracle_app.command("reproduce")
def oracle_reproduce_cmd(
    roots: list[Path] = typer.Argument(
        ..., help="Backfilled season roots (one or more)."),
    source: Optional[list[Path]] = typer.Option(
        None, "--source",
        help="The source roots, scored read only for the plain filter (the "
             "NULL); every week's quantile sidecar must be current."),
    screen: Optional[Path] = typer.Option(
        None, "--screen",
        help="The registered screen's screen_scores.json (or the B2 screen's "
             "screen_b2_scores.json, the shipped bank), printed beside."),
):
    """Score backfilled roots with the app's own scorer and print relWIS
    per season and over the seasons together, on the record definition
    (each member's own scored cells) and on the common set (cells both
    stored members scored), each with its cell count, beside the screen's
    tables. FLUBNF_HUB must be the hub whose truth and baseline the screen
    used.
    """
    from app.core import oracle_backfill as obf
    from flubnf.settings import HUB
    try:
        res = obf.reproduce(list(roots), source_roots=(list(source) if source else None),
                            screen_json=screen)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[bold]reproduce[/bold]  hub {HUB}")
    for line in obf.report_lines(res):
        console.print(line, highlight=False)
    console.print(f"  cells scored (member root): {res['cells_scored']:,}")
    if res.get("screen"):
        console.print(f"  screen frozen document {res['screen'].get('frozen_document_sha256')}"
                      + (f", B2 document {res['screen']['b2_frozen_sha256']}"
                         if res['screen'].get('b2_frozen_sha256') else ""))


# ---------------------------------------------------------------------------
# site
# ---------------------------------------------------------------------------
site_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Build the public static site from the lab's retrospectives.")


@site_app.command("build")
def site_build_cmd(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output directory (default: the repo's site/)."),
    season: str = typer.Option(
        "", "--season",
        help="Pin the home outlook to this season instead of the newest "
             "forecast. Deliberate override; recorded in the payload."),
    asof: str = typer.Option(
        "", "--asof",
        help="Pin the home outlook to this forecast week (YYYY-MM-DD). "
             "Requires the week to exist in the chosen season."),
    check: bool = typer.Option(
        False, "--check",
        help="Exit non-zero if any computed score disagrees with the "
             "figure the console publishes for the same season."),
):
    """Read the app's state and write the static site.

    Everything on the page is computed here from the stored forecasts: the
    outlook map from the newest full-country forecast, the season table from
    whichever retrospective seasons exist on disk, and Methods from the
    console's own templates. Nothing is copied from a note.
    """
    from app.core import site_build as sb
    pin = (season, asof) if (season or asof) else None
    try:
        res = sb.build(out_dir=out, pin=pin)
    except sb.BuildError as e:
        console.print(f"[red]site build: {e}[/red]")
        raise typer.Exit(2)

    src = res["outlook"]
    console.print(f"[bold]site[/bold] -> {res['out']}")
    console.print(f"  page      {res['page_bytes']:>9,} bytes")
    console.print(f"  payload   {res['payload_bytes']:>9,} bytes"
                  "   (site.json, review this diff)")
    console.print(f"  plotly    {res['plotly_bytes']:>9,} bytes"
                  "   (cached sibling, not inlined)")
    console.print(f"  outlook   {src['label']}")
    console.print(f"  locations {res['locations']}")
    console.print(f"  seasons   {', '.join(res['seasons']) or 'none'}")
    if res["pooled"] is not None:
        console.print(f"  pooled    Oracle SIHRS relWIS {res['pooled']:.4f}")
    console.print(f"  built in  {res['elapsed_s']:.1f}s")

    if res["mismatches"]:
        console.print("[red]scores disagree with the console:[/red]")
        for m in res["mismatches"]:
            console.print(f"  {m['what']}: computed {m['computed']:.4f}, "
                          f"console states {m['app']:.4f}")
        if check:
            raise typer.Exit(1)
    else:
        console.print("[green]  scores match the console's published "
                      "figures[/green]")
