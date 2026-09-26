"""`flubnf dataset` (validate, import, list, delete): custom target data
(grouped or hubverse CSV), checked offline. Mounted onto the root app by
flubnf/cli.py."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

dataset_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Check, import, list and delete custom target data (a grouped "
         "CSV or a hubverse time series; comma, semicolon or tab separated; "
         "UTF-8, UTF-16 or Windows-1252; or a folder of snapshot files, one "
         "per as_of).")

_KIND_HELP = ("'count' or 'rate'; default: from the values (whole numbers "
              "are counts; numbers like 1.234, whose dot could separate "
              "thousands, need it).")
_COLUMN_HELP = ("ROLE=HEADER (or ROLE=#N, the Nth column) when the headers "
                "do not say which column is which; ROLE is date, group, "
                "value or population. Repeat for each.")
_PATHS_HELP = ("A CSV, or a folder of snapshot files (or several files): "
               "one per as_of, each named by its as_of date "
               "(2024-10-05.csv) or holding an as_of column, read as one "
               "vintage-true dataset.")


def _dataset_columns(pairs) -> dict:
    """--column ROLE=HEADER pairs as validate's mapping; a malformed pair
    or an unknown role is a usage error (exit 2)."""
    from app.core import datasets as ds
    out = {}
    for pair in pairs or []:
        role, sep, header = str(pair).partition("=")
        role = role.strip().lower()
        if not sep or role not in ds.ROLES or not header.strip():
            raise typer.BadParameter(
                f"{pair!r}: expected ROLE=HEADER with ROLE one of "
                f"{', '.join(ds.ROLES)}.", param_hint="--column")
        out[role] = header.strip()
    return out


def _dataset_sources(paths) -> tuple:
    """(label, [(filename, path), ...]) for the paths given: a file as
    itself, a folder as its CSV, TSV and TXT files (named with the folder,
    so the dataset takes the folder's name). Exit 2 on an empty folder."""
    out = []
    for p in paths:
        if p.is_dir():
            got = sorted(q for q in p.iterdir() if q.is_file()
                         and q.suffix.lower() in (".csv", ".tsv", ".txt"))
            if not got:
                raise typer.BadParameter(f"{p} holds no CSV, TSV or TXT "
                                         "files.", param_hint="PATHS")
            out += [(f"{p.name}/{q.name}", q) for q in got]
        else:
            out.append((p.name, p))
    label = (paths[0].name if len(paths) == 1
             else f"{len(out)} files")
    return label, out


def _print_dataset_problems(name: str, rep_problems, rep=None) -> None:
    from app.core import datasets as ds
    print(f"{name}: {len(rep_problems)} problem(s), nothing stored")
    if rep is not None:
        lines = ds.problem_lines(rep)
    else:
        lines = []
        for kind, probs in ds.problem_groups(rep_problems):
            lines.append(f"{kind}:")
            lines += [f"  - {p}" for p in probs]
    for line in lines:
        print(f"  {line}")


@dataset_app.command("validate")
def dataset_validate_cmd(
    paths: list[Path] = typer.Argument(..., exists=True,
                                       help="The CSV to check. " + _PATHS_HELP),
    kind: Optional[str] = typer.Option(None, "--kind", help=_KIND_HELP),
    target: Optional[str] = typer.Option(
        None, "--target", help="The target to keep when the file has several."),
    column: Optional[list[str]] = typer.Option(
        None, "--column", help=_COLUMN_HELP),
    sunday: bool = typer.Option(
        False, "--sunday", hidden=True,
        help="Accepted and ignored: any one weekday is moved to Saturday."),
):
    """Validate a dataset CSV (or a folder of snapshot files) and print
    every problem, or a summary.

    Exit code 0 when the data is valid, 1 when it has problems. Nothing is
    stored."""
    from app.core import datasets as ds
    label, sources = _dataset_sources(paths)
    rep = ds.validate_snapshots(sources, kind=kind, target=target,
                                columns=_dataset_columns(column))
    if not rep.ok:
        _print_dataset_problems(label, rep.problems, rep)
    else:
        print(f"{label}: valid")
        for line in ds.summary_lines(rep):
            print(f"  {line}")
    for w in rep.warnings:
        print(f"  note: {w}")
    if not rep.ok:
        raise typer.Exit(1)


@dataset_app.command("import")
def dataset_import_cmd(
    paths: list[Path] = typer.Argument(..., exists=True,
                                       help="The CSV to store. " + _PATHS_HELP),
    kind: Optional[str] = typer.Option(None, "--kind", help=_KIND_HELP),
    name: Optional[str] = typer.Option(
        None, "--name", help="The dataset's name (default: the file name, "
                             "with the target when the file holds several; "
                             "a folder's name for its snapshots)."),
    target: Optional[str] = typer.Option(
        None, "--target", help="The target to keep when the file has several."),
    column: Optional[list[str]] = typer.Option(
        None, "--column", help=_COLUMN_HELP),
    sunday: bool = typer.Option(
        False, "--sunday", hidden=True,
        help="Accepted and ignored: any one weekday is moved to Saturday."),
):
    """Validate and store a dataset CSV (or a folder of snapshot files),
    as the console's upload does.

    Prints the dataset's id and summary (exit 0), or every problem (exit 1,
    nothing stored). Importing the same data with the same options again
    returns the stored dataset."""
    from app.core import datasets as ds
    columns = _dataset_columns(column)
    label, sources = _dataset_sources(paths)
    try:
        d = ds.ingest_snapshots(sources, (name or "")[:80] or None,
                                kind=kind, target=target, columns=columns)
    except ds.DatasetError as e:
        _print_dataset_problems(label, e.problems, e.report)
        raise typer.Exit(1)
    print(f"stored {d.name!r} as {d.id}")
    print(f"  groups      {len(d.groups)}: {', '.join(d.groups[:8])}"
          + (" ..." if len(d.groups) > 8 else ""))
    print(f"  weeks       {len(d.weeks())} ({d.meta['date_range'][0]} to "
          f"{d.meta['date_range'][1]})")
    inferred = d.meta.get("options", {}).get("kind_from") == "values"
    print(f"  kind        {d.kind}"
          + (" (inferred from the values; --kind to change)" if inferred
             else ""))
    print(f"  population  {'yes' if d.has_population else 'no'}")
    print(f"  vintages    " + (f"{len(d.vintages())} (vintage-true)"
                               if d.vintage_true else "none (final data)")
          + (f", from {len(d.meta['snapshot_files'])} files"
             if d.meta.get("snapshot_files") else ""))
    if d.meta.get("target"):
        print(f"  target      {d.meta['target']}")
    if d.national_group:
        print(f"  national    {d.national_group}")
    for w in d.meta.get("warnings") or []:
        print(f"  note: {w}")


@dataset_app.command("list")
def dataset_list_cmd():
    """List the stored datasets, newest first."""
    from app.core import datasets as ds
    items = ds.list_datasets()
    if not items:
        print("no datasets stored")
        return
    for d in items:
        print(f"{d.id}  {d.name!r}  {len(d.groups)} group(s), "
              f"{len(d.weeks())} week(s), {d.kind}, population "
              f"{'yes' if d.has_population else 'no'}, vintages "
              f"{'yes' if d.vintage_true else 'no'}")


@dataset_app.command("delete")
def dataset_delete_cmd(
    dataset_id: str = typer.Argument(..., help="The id `dataset list` prints."),
    yes: bool = typer.Option(False, "--yes", help="Delete without asking."),
):
    """Delete a stored dataset and its replays (runs keep their results)."""
    from app.core import datasets as ds
    try:
        d = ds.get(dataset_id)
    except ds.DatasetError as e:
        print(str(e))
        raise typer.Exit(1)
    if not yes and not typer.confirm(f"Delete {d.name!r} ({d.id}) and its "
                                     "replays?"):
        print("nothing deleted")
        raise typer.Exit(1)
    ds.delete(d.id)
    print(f"deleted {d.name!r} ({d.id})")
