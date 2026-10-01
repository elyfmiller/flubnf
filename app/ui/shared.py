"""Helpers two or more tabs use, so no tab imports another for them.

The same-host (CSRF) guard and the no-store header, which server.py
registers as middleware; the request helpers (flash notice, redirect
back, run phase, console clock); the cached disk scans and their one
invalidation hook; run labels, outcome chips and the latest shipped
results; and the readers of the sandbox's engine claim. Among app.ui
modules it imports only state.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from app.core import runs as _runs
from app.core import ttlcache
from app.ui.state import _sandbox_status, _status


#: Hostnames any request may name (POST, and since round 7 GET too). Host/Origin are what a
#: cross-site form-POST or DNS-rebinding page cannot forge. "testserver" is
#: Starlette's TestClient (no dot, so never a public DNS name).
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "testserver"}


def _authority_hostname(authority: str) -> str:
    """Hostname of a Host header value or an Origin URL: lowercased, port
    and IPv6 brackets stripped, "" when it cannot be parsed (and "" is
    never a local hostname, so unparseable means refused)."""
    from urllib.parse import urlsplit
    try:
        host = urlsplit(authority if "//" in authority
                        else "//" + authority).hostname
    except ValueError:
        return ""
    return host or ""


# registered first by server.py (so the sandbox engine guard wraps it)
async def _same_host_guard(request: Request, call_next):
    """DNS-rebinding and CSRF guard for a cookie-less loopback tool. Every
    request, GET included, must carry a localhost Host (a rebinding page
    names its own hostname, so it cannot read run pages or state files);
    POST/PUT/DELETE must also carry a localhost Origin when one is sent.
    The launcher, the window and the tests all address localhost or
    127.0.0.1."""
    if (_authority_hostname(request.headers.get("host", ""))
            not in _LOCAL_HOSTNAMES):
        return PlainTextResponse(
            "Refused: the Host header does not name localhost.\n",
            status_code=403)
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if (origin is not None
                and _authority_hostname(origin) not in _LOCAL_HOSTNAMES):
            return PlainTextResponse(
                "Refused: cross-origin request, the Origin header does "
                "not name localhost.\n", status_code=403)
    return await call_next(request)


# registered by server.py around the two guards, inside the slow-request log
async def _no_store(request: Request, call_next):
    """Cache-Control: no-store on every response but /static/'s. A page or
    a download is always fetched afresh: a cached Output page names an
    earlier run's files, and a report download keeps one URL from run to
    run. The static files keep their ETag and 304s. setdefault, so a
    route's own header (the sandbox zips') stands."""
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# === Cached filesystem scans ===
# Short-TTL caches (app/core/ttlcache.py) for directory scans repeated per
# render; keyed by path so a switched state root never serves another's
# answer. Every state-changing action calls _invalidate_scans().

@ttlcache.ttl_cache()
def _scan_results(workroots: Path) -> list:
    """results.json paths under a workroots directory, newest run first.
    A run id carries only its start second, so ids sharing one are put in
    the order the ledger beside the workroots opened them (created_utc,
    then rowid), never by their random suffix."""
    try:
        paths = list(Path(workroots).glob("*/results.json"))
    except OSError:
        return []

    def stamp(p):
        return p.parent.name[:15]
    seen: dict = {}
    for p in paths:
        seen[stamp(p)] = seen.get(stamp(p), 0) + 1
    tied = [p.parent.name for p in paths if seen[stamp(p)] > 1]
    order = (_runs.run_order(Path(workroots).parent / "ledger.sqlite", tied)
             if tied else {})
    return sorted(paths, key=lambda p: (stamp(p),
                                        order.get(p.parent.name, (0.0, 0)),
                                        p.parent.name), reverse=True)


def _workroot_results() -> list:
    """Workroot results.json paths, newest first (scan cached, files read
    fresh by the caller)."""
    from app.core.runs import APP_STATE
    return _scan_results(APP_STATE / "workroots")


@ttlcache.ttl_cache()
def _scan_archive_dates(root: Path) -> list:
    import re
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name))


def _archive_dates() -> list:
    """Forecast archive dates for the Output page, cached by directory."""
    from app.core.runs import APP_STATE
    return _scan_archive_dates(APP_STATE / "archive")


def _invalidate_scans() -> None:
    """Drop every cached scan; state-changing actions call this."""
    ttlcache.clear_all()


# === Request helpers ===
def _phase(msg):
    _status["phase"] = msg


def _name_workroot(workroot: Path, running: str) -> bool:
    """A console run worker publishes its claim and workroot together, under
    the engine lock, once the workroot is leased. True when Stop was pressed
    while the run was still "starting" (no workroot to flag yet): the STOP
    flag is written now and the worker ends the run as stopped before any
    fit. /run/stop reads the workroot under the same lock, so a press is
    never lost between the two."""
    from app.ui.state import _engine_lock
    with _engine_lock:
        _status["running"] = running
        _status["workroot"] = str(workroot)
        stop = bool(_status.pop("stop_requested", False))
    if stop:
        (Path(workroot) / "STOP").touch()
    return stop


def _flash(msg: str, kind: str = "info", detail: str = "") -> None:
    """Notice for the next page the user sees (also appended to the log).
    `msg` is one short sentence, the essential fact first; `detail` is an
    optional extra (the reason's fine print, what to do next) shown in the
    notice's "?" tip. `kind` is the kit alert's (info, ok, warn, error): a
    refusal warns, a failure is an error. Unconsumed messages join rather
    than overwrite; joined notices keep the most severe kind."""
    prev = _status.get("flash")
    # a repeat of a queued notice keeps the others
    _status["flash"] = (msg if not prev else prev if msg in prev
                        else f"{prev}  {msg}")
    rank = ("info", "ok", "warn", "error")
    old = _status.get("flash_kind") if prev else None
    _status["flash_kind"] = max((k for k in (old, kind) if k in rank),
                                key=rank.index, default="info")
    pd = _status.get("flash_detail") if prev else None
    if detail and not (pd and detail in pd):
        pd = f"{pd}  {detail}" if pd else detail
    if pd:
        _status["flash_detail"] = pd
    else:
        _status.pop("flash_detail", None)
    _status["log"].append(f"{msg} {detail}" if detail else msg)


def _back(request: Request, fallback: str) -> RedirectResponse:
    """Redirect back to the posting page (validated local path), query
    string kept so a refusal from /forecast?source=... lands on that view."""
    from urllib.parse import urlsplit
    parts = urlsplit(request.headers.get("referer", ""))
    path = parts.path
    ok = (path.startswith("/") and not path.startswith("//")
          and "\\" not in path)
    if ok and parts.query:
        path += "?" + parts.query
    return RedirectResponse(path if ok else fallback, status_code=303)


def _console_elapsed(now: float | None = None) -> float | None:
    """Seconds since the console run claimed its slot (setup counts), or
    None when idle."""
    import time as _time
    t0 = _status.get("started_utc")
    if not t0 or not _status.get("running"):
        return None
    return max(0.0, (now if now is not None else _time.time()) - float(t0))


# === Run labels, outcome chips, latest results ===
def _run_label(run_id: str, spec_json: str = "", tag: bool = True) -> str:
    """'2026-07-04 · 08-18 09:31' (forecast date · run time). Research runs
    get ' · research' unless tag=False (pages with a styled badge)."""
    import json as _json
    from app.core.runs import is_research
    when = f"{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}"
    suffix = " · research" if (tag and is_research(spec_json)) else ""
    if tag and _runs.is_modified(spec_json):
        suffix += " · modified settings"
    try:
        s = _json.loads(spec_json)
        return f"{s.get('forecast_date','run')} · {when}{suffix}"
    except Exception:
        return when + suffix


def relwis_chip(value, cells=None, member: str = "PF") -> str:
    """The one relWIS rendering outside a scores table, e.g. 'PF relWIS
    <span class="relwis bad">4.067</span> vs FluSight baseline, ratio of
    sums (2 cells)'. Always names convention and baseline (the CDC's
    dashboard reports a pairwise quantity, within about 0.02 of this one on
    the same cells). Markup from fixed phrases and numbers only."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    cov = ""
    if cells:
        n = int(cells)
        cov = f" ({n} cell{'s' if n != 1 else ''})"
    return (f'{member} relWIS <span class="relwis '
            f'{"ok" if v < 1 else "bad"}">{v:.3f}</span>'
            f' vs FluSight baseline, ratio of sums{cov}')


def _pf_member_label(o: dict) -> str:
    """The mechanistic member's name on one ledger row: "Oracle SIHRS",
    "plain filter" (oracle = none), or "PF" (rows from before the step)."""
    ox = (o or {}).get("oracle")
    if ox == "none":
        return "plain filter"
    # a modified run never claims the shipped member's name
    tail = " (modified)" if (o or {}).get("knobs") else ""
    return ("Oracle SIHRS" if ox else "PF") + tail


def _outcome_items(outcome_json) -> list:
    """One run's outcome as facts, for pages that draw each one with the UI
    kit (the Storage ledger): [{"chip", "text", "state", "tip"}]. "chip" is
    the fact as _outcome_chips writes it; "text" the short word or figure
    (Markup for a relWIS figure), "state" a badge state ("" = a plain
    fact), "tip" what the chip's parenthesis or tail said. A relWIS
    figure's text carries its verdict icon after the number. Fixed phrases
    and numbers only: raw error strings stay on the run page."""
    import json as _json

    from markupsafe import Markup
    try:
        o = _json.loads(outcome_json) if isinstance(outcome_json, str) else outcome_json
    except Exception:
        return []
    if not isinstance(o, dict):
        return []
    items = []

    def add(chip, text=None, state="", tip=""):
        items.append({"chip": chip, "text": chip if text is None else text,
                      "state": state, "tip": tip})

    def judged(chip, v):
        # the figure's verdict icon right after it (the one rule: below 1
        # beats the baseline), so the color is never the only signal
        from app.core.runs import _verdict
        return Markup(chip.replace("</span>", "</span>"
                                   + _verdict(float(v), "st-verdict"), 1))
    if "pf_cells" in o:
        n = o["pf_cells"]
        add(f"PF {n} fit{'s' if n != 1 else ''}")
    if o.get("pf_failures"):
        nf = len(o["pf_failures"])
        word = f"{nf} failure{'s' if nf != 1 else ''}"
        add(f'<span class="bad">{word}</span>', word, "error",
            "The run page names each failed fit.")
    if o.get("pf_skipped"):
        add("PF skipped (no engine)", "PF skipped", "",
            "No engine: a configuration, not a fault.")
    # no engine is a configuration; a broken install is a fault
    if o.get("pf_engine_broken"):
        add('<span class="bad">PF engine install incomplete</span>',
            "PF engine install incomplete", "error",
            "A broken install is a fault, unlike no engine at all. The run "
            "page has the message.")
    if o.get("submissions"):
        ns = len(o["submissions"])
        add(f"{ns} submission{'s' if ns != 1 else ''}")
    if o.get("submission_errors"):
        ns = len(o["submission_errors"])
        word = f"{ns} submission{'s' if ns != 1 else ''} refused"
        add(f'<span class="bad">{word}</span>', word, "error",
            "The run page gives each refused file's reason.")
    if o.get("submission_withheld"):
        # deliberate withholding (research run); the run page names the model
        add('<span class="hint">submission withheld (research run)</span>',
            "submission withheld", "",
            "Withheld deliberately: a research run. The run page names the "
            "model.")
    if o.get("knobs"):
        # modified model settings: the files carry the non-hub name unless
        # the operator exported under the hub names with a reason
        over = bool((o["knobs"] or {}).get("override"))
        add('<span class="warn">modified settings'
            + (', hub names by override' if over else '') + '</span>',
            "modified settings", "warn",
            "Modified model settings: the files carry the non-hub name "
            "unless the operator exported under the hub names with a reason"
            + ("; this run did (hub names by override)." if over else "."))
    if o.get("report"):
        add("report ✓", "report", "ok")
    if o.get("pf_relwis"):
        # scored-cell count; older rows only carry the fit-cell count
        chip = relwis_chip(o["pf_relwis"],
                           cells=o.get("pf_relwis_cells", o.get("pf_cells")),
                           member=_pf_member_label(o))
        if chip:
            add(chip, judged(chip, o["pf_relwis"]))
    # every scored member (older rows' retired-blend keys are not shown)
    for key, member in (("analogue_relwis", "Groundhog"),):
        if o.get(key):
            chip = relwis_chip(o[key], cells=o.get(f"{key}_cells"),
                               member=member + (" (modified)" if o.get(
                                   "knobs") else ""))
            if chip:
                add(chip, judged(chip, o[key]))
    if o.get("error"):
        add('<span class="bad">failed</span>; the full error is on the run '
            'page', "failed", "error", "The full error is on the run page.")
    return items


def _outcome_chips(outcome_json: str) -> str:
    """One run's outcome as short chips: MARKUP (|safe) of fixed phrases and
    numbers only; raw error strings stay on the run page."""
    return " · ".join(i["chip"] for i in _outcome_items(outcome_json))


def _latest_results():
    """(run_id, results) of the newest non-research run, or (None, None).
    A corrupt results.json falls through to the next run; the file is read
    fresh (only the scan is cached). Research runs are skipped because
    every caller is a shipped-product surface (audit rr-1)."""
    import json as _json
    from app.core.runs import is_contained
    for f in _workroot_results():
        try:
            res = _json.loads(f.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, OSError):
            continue
        # research, or modified model settings exported under the non-hub
        # name (an override puts a modified run back, badged)
        if res.get("research") or is_contained(res.get("spec", "")):
            continue
        return f.parent.name, res
    return None, None


# === The sandbox's engine claim, read by /api/busy, /run, /retro/run and
# the sandbox itself ===
def _sandbox_live() -> str:
    """The live sandbox fit, in words for /api/busy ("" when none)."""
    if _sandbox_status.get("running"):
        return str(_sandbox_status["running"])
    if _sandbox_status.get("claim"):
        return f"{_sandbox_status['claim']} (preparing)"
    return ""


def _sandbox_live_reason() -> str:
    """Why the sandbox holds the engine ("" when it does not). Read under
    _engine_lock by /run and /retro/run as well as by the sandbox itself."""
    if _sandbox_status.get("running"):
        return f"sandbox run {_sandbox_status['running']} is still fitting"
    if _sandbox_status.get("claim"):
        return f"a sandbox run of {_sandbox_status['claim']} is being prepared"
    return ""
