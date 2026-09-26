"""The upload box of the Data, Forecast and Retrospective tabs
(templates/_dataset_upload.html, static/dataset_upload.js): reading the
posted form (the capped multipart body, the chosen files, the kind, the
column mapping) and the result box a check or a store shows (every problem
by kind, the column mapping, the target picker, the preview). The routes
that post to it are in app/ui/datasets_ui.py."""
from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path

from fastapi import Request
from markupsafe import Markup, escape

from app.ui import templating

#: groups drawn in an upload's preview (the rest are counted)
PREVIEW_GROUPS = 12
#: a preview sparkline's viewBox
SPARK_W, SPARK_H = 160, 40


def _datasets():
    """app.core.datasets, imported on first use: the console's import
    stays light (datasets_ui._D is the same, and the one tests patch)."""
    from app.core import datasets
    return datasets


async def _capped_form(request: Request, cap: int):
    """The multipart form, refused (None) when Content-Length already
    exceeds the cap and cut off while streaming when a chunked body does."""
    from starlette.formparsers import MultiPartParser

    class TooBig(Exception):
        pass

    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > cap:
        return None

    async def stream():
        n = 0
        async for chunk in request.stream():
            n += len(chunk)
            if n > cap:
                raise TooBig()
            yield chunk
    from starlette.formparsers import MultiPartException
    try:
        # several files are one dataset's snapshots (validate_snapshots)
        parser = MultiPartParser(request.headers, stream(),
                                 max_files=_datasets().MAX_SNAPSHOT_FILES,
                                 max_fields=20)
        return await parser.parse()
    except TooBig:
        return None
    except MultiPartException as e:
        if "files" in str(e).lower():
            return TOO_MANY_FILES
        raise


#: _capped_form's answer to more files than one upload holds
TOO_MANY_FILES = object()


def _too_many_message() -> str:
    return (f"Choose at most {_datasets().MAX_SNAPSHOT_FILES} files; nothing was "
            "read.")


#: the tables a snapshot folder gives (its other files are skipped)
_TABLE_SUFFIXES = (".csv", ".tsv", ".txt")


def _chosen(form, field: str) -> list:
    return [f for f in form.getlist(field)
            if hasattr(f, "file") and getattr(f, "filename", "")]


def _files_of(form) -> tuple:
    """The chosen files of an upload form, and what to say instead when
    they cannot be read together: ``(files, message, snapshots)``.

    The box's first zone posts one CSV as ``file``; its second posts
    snapshot files (chosen, dropped, or a whole folder, whose files other
    than tables are skipped) as ``snapshots``. Several ``file`` entries
    are snapshots too (the script's older posts, scripts, tests). Both
    zones at once are refused: which one was meant is not clear."""
    one = _chosen(form, "file")
    posted = _chosen(form, "snapshots")
    snaps = [f for f in posted if Path(str(f.filename)).suffix.lower()
             in _TABLE_SUFFIXES]
    if one and posted:
        return [], "Choose one CSV or snapshot files, not both.", False
    if posted and not snaps:
        return [], "That folder holds no CSV, TSV or TXT files.", True
    if snaps:
        return snaps, "", True
    if not one:
        return [], "Choose a CSV file, or snapshot files.", False
    return one, "", len(one) > 1


#: one file given as snapshots that holds no as_of: final data
_LONE = ("One snapshot file without an as_of column is read as final data, "
         "not vintage-true; add the other snapshot files, one per as_of.")


def _lone_snapshot(rep, snapshots: bool, n: int) -> str:
    """_LONE when one file was given as snapshots and holds no as_of."""
    s = getattr(rep, "summary", None) or {}
    return _LONE if snapshots and n == 1 and s and not s.get(
        "has_as_of") else ""
# ------------------------------------------------ the upload box (one partial)

def _form_columns(form) -> dict:
    """The column mapping the result box posts (col_<role> = '#N')."""
    return {r: str(form.get(f"col_{r}") or "").strip() for r in _datasets().ROLES
            if str(form.get(f"col_{r}") or "").strip()}


def _sparkline(points, first: _date, last: _date, top: float) -> str:
    """SVG polyline points for one group's weeks on the shared date axis."""
    span = max((last - first).days, 1)
    pad = 2.0
    if len(points) > 400:                       # a long series, thinned
        step = len(points) / 400.0
        points = [points[int(i * step)] for i in range(400)] + [points[-1]]
    out = []
    for d, v in points:
        x = pad + (SPARK_W - 2 * pad) * (d - first).days / span
        y = SPARK_H - pad - ((SPARK_H - 2 * pad) * v / top if top > 0 else 0)
        out.append(f"{x:.1f},{y:.1f}")
    return " ".join(out)


def _preview(rep, kind: str) -> dict:
    """What a valid upload holds: counts and dates, the first rows as read,
    and a sparkline per group (the newest snapshot of each week)."""
    s = rep.summary
    newest = {}
    for a, name, _, d, v, _ in rep.records:
        if v is None:
            continue
        k = (name, d)
        if k not in newest or (a or _date.min) >= newest[k][0]:
            newest[k] = (a or _date.min, v)
    by = {}
    for (name, d), (_, v) in newest.items():
        by.setdefault(name, []).append((d, v))
    first = _date.fromisoformat(s["first"])
    last = _date.fromisoformat(s["last"])
    sparks = []
    for name in s["groups"][:PREVIEW_GROUPS]:
        pts = sorted(by.get(name, []))
        if not pts:
            continue
        top = max(v for _, v in pts)
        peak = max(pts, key=lambda p: p[1])
        sparks.append({"name": name, "points": _sparkline(pts, first, last,
                                                          top),
                       "label": f"{name}: {len(pts)} weeks, peak "
                                f"{peak[1]:,.6g} ({peak[0].isoformat()})"})
    return {"groups": s["groups"], "n_groups": len(s["groups"]),
            "more": max(0, len(s["groups"]) - PREVIEW_GROUPS),
            "first": s["first"], "last": s["last"], "weeks": s["weeks"],
            "rows": s["rows"], "kind": kind or s["inferred_kind"],
            "inferred": not kind, "population": s["has_population"],
            "snapshots": len(s["as_of"]), "national": s.get("national_group"),
            # several snapshot files: how many, and the as_of they span
            "files": len(s.get("snapshot_files") or []),
            "as_of_first": (s["as_of"] or [""])[0],
            "as_of_last": (s["as_of"] or [""])[-1],
            "rows_file": s.get("first_rows_file") or "",
            "target": s.get("target"),
            "read_as": f"{s['delimiter']}-separated, {s['encoding']}",
            "first_rows": s.get("first_rows") or [],
            # the file's own date column only when it differs from the week
            "dates_differ": any(r["date"] != r["week"]
                                for r in s.get("first_rows") or []),
            "sparks": sparks, "w": SPARK_W, "h": SPARK_H}


#: mapping-step problems shown in the problem box: a reason to choose (two
#: columns that could each be a role, a mapping that named nothing), never
#: a silent pick; a role no header matched is only asked for
MAPPING_PROBLEMS = ("ambiguous_columns", "column_unknown")


def _mapping_why(rep) -> list:
    """The mapping's own hint: one line naming the roles no header matched
    (the reasons to choose are problems, MAPPING_PROBLEMS)."""
    if not rep.needs_mapping:
        return []
    unset = [r for r in _datasets().REQUIRED
             if r not in rep.guess and r not in rep.ambiguous]
    out = []
    if unset:
        names = [f"the {r}" for r in unset]
        out.append("Choose the column that holds "
                   + (", ".join(names[:-1]) + " and " if len(names) > 1
                      else "") + names[-1] + ".")
    return out


#: a date in a problem or a notice (2024-03-16, or 2024-03-32 as written)
_DATE_TOKEN = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")


def _whole_dates(text) -> Markup:
    """Problem or notice text, escaped, with each date kept on one line: at
    phone width a browser breaks it after a hyphen ('2024-03-' / '16')."""
    return Markup(_DATE_TOKEN.sub(lambda m: f'<span class="nw">{m[0]}</span>',
                                  str(escape(text))))


def check_view(rep, *, kind: str = "", columns=None, files: int = 1) -> dict:
    """The result box's context (templates/_dataset_check.html) for one
    report: every problem grouped by kind, a column mapping when that is
    what is missing (instead of an error; two columns that could each be
    a role are also a problem, with its reason, and neither is picked),
    the target picker when a file holds several (a choice to make, not a
    problem; nothing is picked for the user), the notices, and a preview
    when it is valid."""
    columns = columns or {}
    choose = len(rep.targets) > 1 and "target_required" in rep.codes
    mapping = None
    if rep.headers and (rep.needs_mapping or columns):
        labels = {"date": "Date", "group": "Group", "value": "Value",
                  "population": "Population"}
        mapping = {
            "headers": [(f"#{i + 1}", h) for i, h in enumerate(rep.headers)
                        if h],
            "why": _mapping_why(rep),
            "roles": [{"role": r, "label": labels[r],
                       "required": r in _datasets().REQUIRED,
                       "value": columns.get(r) or rep.guess.get(r, "")}
                      for r in _datasets().ROLES]}
    shown = [p for p in rep.problems
             if not (choose and p.code == "target_required")
             and (p.code in MAPPING_PROBLEMS or not rep.needs_mapping)]
    problems = [(k, [{"message": _whole_dates(p), "rows": list(p.rows)}
                     for p in ps])
                for k, ps in _datasets().problem_groups(shown)]
    return {"ok": rep.ok, "problems": problems,
            "n": sum(len(ps) for _, ps in problems),
            "mapping": mapping, "needs_mapping": rep.needs_mapping,
            "notices": [_whole_dates(w) for w in rep.warnings],
            "targets": rep.targets if len(rep.targets) > 1 else [],
            "target": (rep.summary or {}).get("target") or "",
            "files": files,
            "preview": _preview(rep, kind) if rep.ok and rep.summary else None}


def check_status(chk: dict) -> str:
    """The upload box's status line (role=status): what a check found, in
    a few words, read out instead of the whole result."""
    if chk.get("preview"):
        pv = chk["preview"]
        return (f"Ready to use: {pv['n_groups']} group"
                f"{'' if pv['n_groups'] == 1 else 's'}, {pv['weeks']} week"
                f"{'' if pv['weeks'] == 1 else 's'}"
                + (f", {pv['files']} snapshot files." if pv["files"]
                   else "."))
    n = chk.get("n") or 0
    if chk.get("needs_mapping"):
        return "Choose which column is which." + (
            f" {n} problem{'' if n == 1 else 's'} to fix." if n else "")
    if chk.get("targets") and not chk.get("target") and not n:
        return "Choose the target."
    return f"{n} problem{'' if n == 1 else 's'} to fix."


def _message_view(message: str) -> dict:
    """The result box for a refusal that is not about the file's content."""
    return {"ok": False, "problems": [("File", [{"message": message,
                                                 "rows": []}])],
            "n": 1, "mapping": None, "notices": [], "targets": [],
            "target": "", "preview": None}


def render_check(chk: dict, where: str = "data") -> str:
    """The result box's HTML (the same macro the pages render)."""
    tpl = templating.templates.get_template("_dataset_check.html")
    return str(tpl.module.result(chk, where))


def _kind_field(form):
    """The posted kind: '' = from the values; None = not a kind. A kind
    the upload box filled in from the values (kind_auto=1, never picked by
    hand) stays "from the values", as the CLI records it."""
    k = str(form.get("kind") or "").strip()
    if k not in ("",) + _datasets().KINDS:
        return None
    return "" if str(form.get("kind_auto") or "") == "1" else k
