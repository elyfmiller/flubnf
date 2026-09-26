"""`flubnf retro` (run, export, import) and `flubnf groundhog retro`: season
replays. Mounted onto the root app by flubnf/cli.py.

In file order: the retro group (a bare `flubnf retro <season>` is `run`),
run, export, import; then the groundhog sub-app. Heavy imports (pandas,
the engines) stay inside the commands so `flubnf app` never loads them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from typer.core import TyperGroup

console = Console()


class _RetroGroup(TyperGroup):
    """`flubnf retro <season> ...` replays a season (the `run` command,
    kept as the bare form); `export` and `import` move a replayed season
    between machines. A first word that is neither a subcommand nor --help
    (a season, or an option such as --locations) goes to `run`."""

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands and args[0] != "--help":
            args = ["run"] + list(args)
        return super().parse_args(ctx, args)


retro_app = typer.Typer(
    cls=_RetroGroup, add_completion=False, no_args_is_help=True,
    help="Replay a season as a competition (`flubnf retro <season>`), or "
         "export and import a replayed season as one zip bundle.")


def _oracle_none(inner):
    """`inner` (a week_extra) with the plain filter asked for: the week's
    oracle key set to 'none', the name saying so."""
    def week_extra(asof, i, vintages, _inner=inner):
        d = dict(_inner(asof, i, vintages))
        d["oracle"] = "none"
        return d
    week_extra.__name__ = inner.__name__ + "+oracle:none"
    return week_extra


@retro_app.command("run")
def retro_cmd(
    season: Annotated[str, typer.Argument(
        help="Season to replay, e.g. 2024-25.")],
    locations: Annotated[str, typer.Option(
        help="Comma-separated location names, or 'all' (52 jurisdictions).")] = "all",
    width: int = 0,
    replicates: Annotated[int, typer.Option(
        help="Particle-filter replicates (seeds) per location-week.")] = 3,
    root: Annotated[str, typer.Option(
        help="Season root to write (default: the console's "
             "app/state/retro/<season>, wherever the command runs).")] = "",
    aux: Annotated[str, typer.Option(
        help="Analogue donor preset; empty = the shipped Groundhog, "
             "'none' = the bare analogue (research).")] = "",
    oracle: Annotated[str, typer.Option(
        help="Empty = the Oracle SIHRS; 'none' = the plain filter "
             "(research).")] = "",
    knob: Annotated[Optional[list[str]], typer.Option(
        "--knob", help="Model knob as key=value (repeatable; see `flubnf "
                       "knobs`). Off-shipped values are recorded in "
                       "run_meta.json and a tree built with other values "
                       "is refused, not resumed.")] = None,
):
    """Run a season-as-competition retrospective (resumable).

    --width (shard width) 0 means auto: the engine's default_shard_width()
    for this machine, the same default the console form offers.

    aux names the analogue donor preset (analogue.AUX_PRESETS, e.g.
    'flusurv'). Empty runs the shipped Groundhog (analogue.SHIPPED_AUX);
    'none' the bare calendar analogue (research). The name and its bank
    digests go into run_meta.json.

    oracle: empty stores the Oracle SIHRS under pf (app/core/oracle.py
    applied to the filter's samples; the filter's quantiles are kept in
    oracle.json); 'none' stores the plain filter (research), which the
    week's oracle.json records.

    --knob key=value sets a model knob (app/core/knobs.py, parsed and
    range-checked by knobs.resolve). pf.particles and pf.replicates also
    come from here (--replicates is the older spelling of the latter; two
    different values are refused)."""
    import re

    import pandas as pd

    from app.core import knobs as _K
    from app.core import retro
    from app.core.engines import analogue as _an
    from app.core.engines import pf as _pf
    from app.core.runs import APP_STATE as _APP_STATE
    from flubnf.settings import LOCATIONS
    pairs = {}
    for item in knob or []:
        k, sep, v = str(item).partition("=")
        if not sep or not k.strip():
            raise typer.BadParameter(f"--knob takes key=value, got {item!r}")
        if k.strip() in pairs:
            raise typer.BadParameter(f"--knob {k.strip()} given twice")
        pairs[k.strip()] = v.strip()
    # a season name becomes a directory: YYYY-YY with consecutive years
    m = re.fullmatch(r"(\d{4})-(\d{2})", season)
    if not m or (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        raise typer.BadParameter(
            f"{season!r} is not a season; give one such as 2024-25")
    vints = retro.season_vintages(season)
    if not vints:
        from app.core import data as _data
        typer.echo(f"refused: no archived vintages for {season} in "
                   f"{_data.ARCHIVE} and no shipped snapshots for it in "
                   f"{_data.SHIPPED}; nothing was run. Update the hub clone, "
                   "or pick a season it holds.", err=True)
        raise typer.Exit(2)
    try:
        nd = _K.resolve(pairs, "all", scope="retro",
                        forecast_date=(vints[0] if vints else None),
                        check_dates=tuple(vints[-1:]),
                        oracle_step=(oracle != "none"),
                        legacy={"replicates": replicates})
    except _K.KnobError as e:
        raise typer.BadParameter(str(e)) from None
    replicates = int(nd.get("pf.replicates", 3))
    particles = int(nd.get("pf.particles", 10_000))
    width = _pf.resolve_width(width)
    locs = pd.read_csv(LOCATIONS, dtype=str)
    names = (list(locs.location_name[locs.location.str.len() == 2]
                  [locs.abbreviation != "US"])
             if locations == "all" else
             [x.strip() for x in locations.split(",")])
    # ABSOLUTE: runner subprocesses resolve conf/shard paths against their
    # own cwd, so a relative --root fails every fit.
    # the default is the console's own retro root (app/state/retro, beside
    # this package), never one under the shell's current directory
    r = (Path(root) if root else _APP_STATE / "retro" / season).resolve()
    if aux == "none":
        week_extra = _an.bare_analogue
    elif aux:
        week_extra = _an.aux_preset(aux)      # unknown name raises here
    else:
        week_extra = _an.aux_preset(_an.SHIPPED_AUX)
    print(f"  analogue donor configuration: {week_extra.__name__}")
    if oracle == "none":
        week_extra = _oracle_none(week_extra)
        print("  Oracle step: none (the plain filter, a research run)")
    elif oracle:
        raise typer.BadParameter(
            "--oracle takes 'none' (the plain filter, a research run) or "
            "nothing (the Oracle SIHRS)")
    else:
        print("  Oracle step: applied (w = 0.5; the donor bank built from "
              "each week's vintage, named in the week's oracle.json)")
    kx = {}
    if nd:
        if "groundhog.aux" in nd and aux:
            if (_K.aux_choice(nd, None) or "none") != aux:
                raise typer.BadParameter(
                    "--aux and --knob groundhog.aux disagree; give one")
        if "groundhog.aux" in nd:
            pick = _K.aux_choice(nd, None)
            week_extra = (_an.aux_preset(pick) if pick
                          else _an.bare_analogue)
            if oracle == "none":
                week_extra = _oracle_none(week_extra)
        week_extra = _K.retro_week_extra(week_extra, nd)
        kx = {"settings": {"knobs": _K.jsonable(nd)},
              "drop_same_day": bool(nd.get("run.drop_same_day", False))}
        print(f"  model settings: {_K.label(nd)}")
    try:
        done = retro.run_season(r, season, names, replicates=replicates,
                                particles=particles,
                                width=width, week_extra=week_extra,
                                progress=lambda a: print(f"  {a} done",
                                                         flush=True), **kx)
    except retro.EngineBuildChanged as e:
        typer.echo(f"stopped: {e}", err=True)
        raise typer.Exit(2)
    except retro.ResumeMismatch as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    print(f"{season}: {len(done)} weeks complete -> {r}")


def _retro_root_default() -> Path:
    """The console's retro root (app/state/retro), read at call time."""
    from app.core.runs import APP_STATE
    return APP_STATE / "retro"


@retro_app.command("export")
def retro_export_cmd(
    season: Annotated[str, typer.Argument(
        help="Season to export, e.g. 2024-25.")],
    archive: Annotated[str, typer.Option(
        "--archive", help="Export this archived run (its stamp, as the "
                          "season list shows it) instead of the live one.")] = "",
    out: Annotated[str, typer.Option(
        "--out", help="Folder for the bundle (default: app/state/exports).")] = "",
    root: Annotated[str, typer.Option(
        "--root", help="Retro root holding the season (default: the "
                       "console's app/state/retro).")] = "",
):
    """Write a season's replay bundle: one zip of its run record, scores
    and every stored week, for `flubnf retro import` or the Retrospective
    tab on another machine. Prints the bundle's path and size."""
    from app.core import replay_bundle, retro
    rr = Path(root) if root else _retro_root_default()
    src = retro.archive_dir(rr, season, archive) if archive else rr / season
    if archive and not retro.valid_stamp(archive):
        raise typer.BadParameter(f"{archive!r} is not an archive stamp")
    try:
        p = replay_bundle.export_season(
            src, season, Path(out) if out else _retro_root_default().parent
            / "exports", stamp=archive)
    except replay_bundle.BundleError as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    m = replay_bundle.inspect_bundle(p)
    print(f"{season}: {len(m['weeks'])} weeks, "
          f"{retro.human_bytes(p.stat().st_size)} -> {p}")


@retro_app.command("import")
def retro_import_cmd(
    file: Annotated[Path, typer.Argument(
        exists=True, dir_okay=False, help="The .flubnf-replay.zip to import.")],
    replace: Annotated[bool, typer.Option(
        "--replace", help="Replace a copy already imported from the same "
                          "export.")] = False,
    root: Annotated[str, typer.Option(
        "--root", help="Retro root to import into (default: the console's "
                       "app/state/retro).")] = "",
):
    """Import a replay bundle as a read-only archived run of its season
    (<season>__archived_<export stamp> under the retro root). The live
    season tree is never written."""
    from app.core import replay_bundle
    rr = Path(root) if root else _retro_root_default()
    try:
        r = replay_bundle.import_bundle(file, rr, replace=replace)
    except replay_bundle.BundleError as e:
        typer.echo(f"refused: {e}", err=True)
        raise typer.Exit(2)
    when = (r.exported_at or "")[:10]
    print(f"imported {r.season}: {len(r.weeks)} weeks, exported from "
          f"{r.from_host or 'another machine'}"
          f"{' on ' + when if when else ''} -> {r.root}")
    print(f"  open it as /retro/{r.season}?archive={r.stamp}")
    for w in r.warnings:
        print(f"  note: {w}")


# ---------------------------------------------------------------------------
# groundhog: the calendar member alone. No particle filter or toolchain,
# about two minutes a season.
# ---------------------------------------------------------------------------
groundhog_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="GroundHogCGR, the calendar member, replayed and scored on its own.")

GROUNDHOG_SEASONS = ("2023-24", "2024-25", "2025-26")


def _gh_row(label: str, b: dict) -> str:
    if not b.get("cells"):
        return f"  {label:<26} no scorable cells"
    return (f"  {label:<26}{b['relwis']:>8.4f}"
            f"{b.get('cov50', float('nan')):>8.3f}"
            f"{b.get('cov80', float('nan')):>8.3f}"
            f"{b.get('cov95', float('nan')):>8.3f}"
            f"{b['worst_dev']:>8.3f}{b['cells']:>9,}{b['weeks']:>7}")


@groundhog_app.command("retro")
def groundhog_retro_cmd(
    season: str = typer.Argument(
        ..., help="A season such as 2024-25, or 'all' for the three on record."),
    aux: str = typer.Option(
        "", "--aux",
        help="Auxiliary donor preset (flusurv, iliplus, both); flusurv is "
             "the Groundhog. Empty runs the bare single-pool analogue "
             "(arm directory 'shipped', its historical name)."),
    compare: bool = typer.Option(
        True, "--compare/--no-compare",
        help="With --aux: also run the shipped member and report both on "
             "identical cells, with a clustered bootstrap on the difference."),
    with_us: bool = typer.Option(
        False, "--with-us",
        help="Also forecast the national row. Reported separately, never "
             "pooled into the state figures."),
):
    """Replay the calendar member alone over a season and score it.

    No particle filter, no PyBNF: only this repository, the committed donor
    bank, and a hub clone for the vintages, the truth and the FluSight
    baseline. About two minutes a season.
    """
    import pandas as pd

    from app.core import groundhog as gh
    seasons = list(GROUNDHOG_SEASONS) if season == "all" else [season]
    arms = ([gh.SHIPPED, aux] if (aux and compare) else [aux or gh.SHIPPED])
    runs = {a: [] for a in arms}
    for a in arms:
        for s in seasons:
            console.print(f"[bold]{a}[/bold]  {s}")
            try:
                r = gh.run_season(
                    s, "" if a == gh.SHIPPED else a, with_us=with_us,
                    progress=lambda asof, i, n: (
                        console.print(f"    {i:>3}/{n}  {asof}")
                        if (i % 8 == 0 or i == n) else None))
            except Exception as e:
                console.print(f"[red]{s}: {e}[/red]")
                raise typer.Exit(1)
            runs[a].append(r)
            if r["meta"]["aux"]:
                console.print(f"    donors: {r['meta']['aux']}")
            console.print(f"    -> {r['dir']}")

    head = (f"  {'':<26}{'relWIS':>8}{'cov50':>8}{'cov80':>8}{'cov95':>8}"
            f"{'worst':>8}{'cells':>9}{'weeks':>7}")
    pooled = {a: (pd.concat([r["cells"] for r in rs], ignore_index=True),
                  pd.concat([r["coverage"] for r in rs], ignore_index=True))
              for a, rs in runs.items()}

    console.print("\n[bold]Each arm on its own cells[/bold]  (52 states, US "
                  "national excluded)")
    console.print(head)
    for a, (c, v) in pooled.items():
        sm = gh.summarise(c, v)
        console.print(_gh_row(a, sm["states"]))
        if "us" in sm:
            console.print(_gh_row(f"{a}, US national", sm["us"]))

    if len(arms) == 2:
        (ac, av), (bc, bv) = pooled[arms[0]], pooled[arms[1]]
        cmp_ = gh.compare(ac, av, bc, bv)
        console.print(f"\n[bold]On identical cells[/bold]  "
                      f"({cmp_['common_cells']:,} common)")
        console.print(head)
        console.print(_gh_row(arms[0], cmp_["a"]))
        console.print(_gh_row(arms[1], cmp_["b"]))
        if len(seasons) > 1:
            console.print("\n[bold]By season[/bold]")
            console.print(f"  {'season':<10}{arms[0]:>10}{arms[1]:>10}"
                          f"{'change':>9}{'worst a':>9}{'worst b':>9}")
            for s, d in cmp_["by_season"].items():
                ra, rb = d["a"]["relwis"], d["b"]["relwis"]
                console.print(f"  {s:<10}{ra:>10.4f}{rb:>10.4f}"
                              f"{(1 - rb / ra) * 100:>+8.1f}%"
                              f"{d['a']['worst_dev']:>9.3f}"
                              f"{d['b']['worst_dev']:>9.3f}")
        bs = cmp_.get("bootstrap")
        if bs:
            console.print(
                f"\n  clustered bootstrap over {bs['clusters']} as-of dates, "
                f"{bs['reps']} replicates\n"
                f"  {arms[1]} minus {arms[0]}: median {bs['median']:+.4f}, "
                f"95 percent interval [{bs['lo']:+.4f}, {bs['hi']:+.4f}], "
                f"better in {bs['b_better']} of {bs['reps']}")
    console.print("\nSelf scored, ratio of WIS sums against the FluSight "
                  "baseline of the same\nreference date, on FluSight's cell "
                  "rule (truth of 0 and a median of 0 scored).\nThe FluSight "
                  "dashboard reports pairwise scaled relative WIS, within "
                  "about\n0.02 of this on the same cells. No finite-sample "
                  "coverage guarantee is claimed.")
