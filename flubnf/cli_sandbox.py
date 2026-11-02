"""`flubnf model`, `flubnf experiment` and `flubnf storage`: the Sandbox's
model and experiment actions as its pages have them, for a terminal and
for scripts. Mounted onto the root app by flubnf/cli.py.

  model new | check | register | list
  experiment start | show | list | stop | delete
  storage

Each command takes what its page asks and nothing more, and calls the
core its page calls, in the page's words. --json prints one JSON document
on stdout, the route's JSON where the route has one, and every human word
then goes to stderr. Exit codes, one table for every command: 0 done, or
answered in words; 1 refused or failed (the model, the settings or the
request); 2 usage (click's own); 3 this computer (a MACHINE finding, or
interrupted).

On a laptop, and on the runner computer's main install, `experiment
start` replays in this terminal until it ends: refused while this clone's
console is open or another replay runs here, its fits registered apart
(app/state/pf_runners.terminal.json) so a console launch never kills
them, and stopped before its next week once the console opens. Ctrl-C
once is the page's Stop; a second, or the terminal closing, stops it at
once. In a student's folder on the runner computer a start queues for the
runner (app/core/runner.py), as the page's Start does.

Module imports are typer's and the standard library's only: every app.core
import is inside a command, so `flubnf app` never loads pandas
(test_cli_import_stays_light).
"""

from __future__ import annotations

import json
import os
import signal
import sys
from typing import NoReturn, Optional

import typer

_JSON_HELP = ("Print one JSON document on stdout (the page's JSON); the "
              "words go to stderr.")
_HELP_TAIL = (" --json prints the page's JSON. Exit 0 done, 1 refused, 2 "
              "usage, 3 this computer (docs/CONTRIBUTING.md).")

model_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="The Sandbox's models for replays, as its page has them: the "
         "Oracle SIHRS template start, Check, Register and the list an "
         "experiment picks from." + _HELP_TAIL)

experiment_app = typer.Typer(
    add_completion=False, no_args_is_help=True,
    help="Experiments, as the Experiments card and an experiment's page "
         "have them: start (or resume), show, list, stop, delete. On the "
         "students' Mac Studio a start queues for the runner; elsewhere it "
         "runs in this terminal." + _HELP_TAIL)

#: the run record's stop reason when the console opens during a
#: foreground start (cancelled(), before its next week)
_CONSOLE_OPENED = ("Stopped before the next week: the console was opened on "
                   "this computer. Finished weeks are kept; Start on its "
                   "page resumes it.")


# ------------------------------------------------------------ the helpers


def _finite(obj):
    """obj with every NaN or infinite float as None: JSON has no NaN (a
    copy of routes/sandbox.py's _json_finite, which a command cannot
    import)."""
    from math import isfinite
    if isinstance(obj, float):
        return obj if isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def _emit(as_json: bool, obj, lines, code: int | None) -> None:
    """A command's answer: with as_json, obj as the one JSON document on
    stdout (none when obj is None) and the lines on stderr; else the lines
    on stdout. Then exit with `code`; None returns instead (the start's
    answer, printed before anything is fitted)."""
    if as_json and obj is not None:
        sys.stdout.write(json.dumps(_finite(obj), indent=1, sort_keys=True,
                                    default=str) + "\n")
        sys.stdout.flush()
    for line in lines:
        print(line, file=sys.stderr if as_json else sys.stdout, flush=True)
    if code is not None:
        raise typer.Exit(code)


def _interruptible(cmd):
    """cmd with a Ctrl-C that reaches it (KeyboardInterrupt) said as
    "Interrupted." and exit 3, this computer's code, instead of Typer's
    130: every command exits 0, 1, 2 or 3."""
    from functools import wraps

    @wraps(cmd)
    def run(*args, **kwargs):
        try:
            return cmd(*args, **kwargs)
        except KeyboardInterrupt:
            _emit(bool(kwargs.get("as_json")), None, ["Interrupted."], 3)
    return run


def _code(findings) -> int:
    """The exit code of a refusal: 1 when a finding is the model's or the
    request's (problem tier), else 3 when one is this computer's (MACHINE),
    else 1."""
    tiers = {f.get("tier") for f in findings or ()}
    return 1 if "problem" in tiers else 3 if "machine" in tiers else 1


def _said(findings, prefix: str) -> str:
    """'<prefix>: <text> (<CODE>)' of the first finding, in the order
    given (each caller orders them as its route does)."""
    f = findings[0]
    return f"{prefix}: {f['text']} ({f['code']})"


def _relwis(fig) -> str:
    """'relWIS 1.272 (shipped 1.219)' of a group's figures, '' for none."""
    if not fig:
        return ""

    def num(x):
        return "n/a" if x is None else f"{x:.3f}"
    words = f"relWIS {num(fig['model']['rel'])}"
    if fig.get("shipped") is not None:
        words += f" (shipped {num(fig['shipped']['rel'])})"
    return words


def _retro_root():
    """The install's retro root, runs.APP_STATE/retro (job_main's, and
    where `flubnf retro` replays), read at call time."""
    from app.core import runs
    return runs.APP_STATE / "retro"


def _terminal_registry():
    """The foreground start's fits registry, beside the console's
    (pf_runners.json): a console launch sweeps only its own, so it never
    kills a terminal's fits. Read at call time (the tests move
    APP_PID_FILE)."""
    from flubnf import cli
    return cli.APP_PID_FILE.parent / "pf_runners.terminal.json"


def _apart(run_kwargs):
    """pf.bng_run_kwargs for a foreground start: each BNG2.pl run (a
    week's netgen, in this process) in a process group of its own, as the
    fits are. A terminal's Ctrl-C reaches its whole foreground group, and
    the first, the page's Stop, must not kill a netgen: prepare would
    record that location as failed, and a resume reuses the week's
    preparation. A second still ends it: subprocess.run kills its child
    on the KeyboardInterrupt."""
    from app.core.engines import pf

    def kwargs(*args, **kw):
        out = run_kwargs(*args, **kw)
        if os.name == "posix":
            out["start_new_session"] = True
        else:
            out["creationflags"] = (int(out.get("creationflags", 0))
                                    | pf._CREATE_NEW_PROCESS_GROUP)
        return out
    return kwargs


def _student() -> str | None:
    """The student's name when this Sandbox is a student's folder on the
    runner computer (a start then queues); None everywhere else, at one
    failed stat."""
    from app.core import runner
    from app.core import sandbox as sb
    return runner.folder_of(sb.SANDBOX)


def _local_refusal(eid: str) -> dict | None:
    """Why a foreground start may not begin on this computer, as a MACHINE
    finding, else None; tried in this order: this clone's console is open;
    the runner here replays (busy_words); an experiment of this Sandbox is
    under way (eid named first when it is one); then, with no terminal run
    left alive, an earlier terminal run's orphaned fits are swept, before
    the runner's probe (_replay_elsewhere), which would otherwise wait for
    them; any other replay on this computer; no particle-filter engine
    (a probe that raises counts as none); an engine older than this
    console (pf.prepare would refuse every week), in its own words."""
    from flubnf import cli
    from app.core import experiments as X
    from app.core import retro, runner
    from app.core.engines import pf
    from app.core.problem_codes import finding
    if cli._console_open():
        return finding("MACHINE", "the console is open on this computer: "
                       "start the experiment from its Sandbox page, or quit "
                       "the console first")
    why = runner.busy_words()
    if why:
        return finding("MACHINE", f"{why}: one replay at a time")
    live = [r["id"] for r in X.list_experiments()
            if r["status"]["status"] in retro.ACTIVE_STATUSES]
    if live:
        return finding("MACHINE", f"experiment "
                       f"{eid if eid in live else live[0]} is replaying on "
                       "this computer: one replay at a time")
    cli._sweep_runner_groups(_terminal_registry())
    why = runner._replay_elsewhere()
    if why:
        return finding("MACHINE", f"{why}: one replay at a time")
    try:
        ready = runner._engine_ready()
        stale = ready and not pf.engine_current()
    except Exception:
        ready = stale = False
    if not ready:
        return finding("MACHINE", "an experiment needs the particle-filter "
                       "engine, which is not ready on this computer (flubnf "
                       "doctor says why)")
    if stale:
        return finding("MACHINE", pf.engine_stale_message())
    return None


def _on_signal(flag: dict, folder):
    """The foreground start's handler for SIGINT, SIGTERM and SIGHUP. The
    first SIGINT is the page's Stop: STOP written in the folder (once it is
    one), flag["stop"] set for cancelled() (a stop asked before run_season
    cleared the flags), said, and nothing raised, so the fits in flight
    finish. A second SIGINT, SIGTERM or SIGHUP (the terminal closing)
    writes STOP and raises KeyboardInterrupt: retro's round kills its fits
    and the record closes as stopped. Once it has raised, a further signal
    does nothing, so that kill and the put-back run to their end.
    flag["err"]: say it on stderr."""
    from app.core import retro

    def handler(signum, frame):
        if flag.get("now"):
            return              # stopping now: the round ends its fits first
        try:
            retro.request_stop(folder)        # never creates the folder
        except OSError:
            pass
        if signum == signal.SIGINT and not flag["stop"]:
            flag["stop"] = True
            try:
                print("Stopping after the fits in flight (Ctrl-C again to "
                      "stop now).", file=sys.stderr if flag["err"]
                      else sys.stdout, flush=True)
            except Exception:
                pass                          # a print it interrupted
            return
        flag["stop"] = flag["now"] = True
        raise KeyboardInterrupt
    return handler


def _foreground(s: dict, eid: str, p: dict, a: dict,
                as_json: bool = False) -> int:
    """A start that replays in this terminal, after its preflight p: the
    start's answer (a, experiments.started(p)) printed (flushed) before
    anything is fitted, then experiments.run with the fits registered
    apart (_terminal_registry), the sleep guard held (macOS, in a session
    of its own), the signals handled (_on_signal; one
    ignored before, as under nohup, is left ignored), cancelled() before
    every week not yet stored (a stop asked, or this clone's console
    opened, its reason then recorded) and a line after every week. Then
    the flags cleared and everything put back. Returns the exit code of
    its outcome, said in words. BNG2.pl's runs here sit in a group of
    their own meanwhile (_apart), so the first Ctrl-C leaves them be."""
    from flubnf import cli
    from app.core import experiments as X
    from app.core import retro, runner, runs
    from app.core import sandbox as sb
    from app.core.engines import pf
    from app.core.problem_codes import Refusal
    folder = X.root() / eid
    flag = {"stop": False, "now": False, "err": as_json}

    def cancelled() -> bool:
        if flag["stop"]:
            return True
        if cli._console_open():
            try:
                retro._record_stop_reason(folder, _CONSOLE_OPENED)
            except Exception:
                pass                      # a raising check fails the week
            return True
        return False

    def progress(asof: str) -> None:
        # a raising callback would end run_season: it only says
        try:
            st = X.status(folder)
            how = ("stored" if retro.week_done(folder, asof) else
                   "not stored (its folder's failures.log says why)")
            print(f"  {asof}: {how} · {st['weeks_done']} of "
                  f"{st['weeks_total']} weeks",
                  file=sys.stderr if as_json else sys.stdout, flush=True)
        except Exception:
            pass

    def stopped() -> list:
        st = X.status(folder)
        why = f" {st['stop_reason']}" if st["stop_reason"] else ""
        return [f"Stopped {eid}: {st['weeks_done']} of {st['weeks_total']} "
                f"weeks stored; the same command resumes it.{why}"]

    registry, run_kwargs = pf.RUNNER_PIDS_FILE, pf.bng_run_kwargs
    guard, saved = None, {}
    try:
        _emit(as_json, {"ok": True, "id": eid,
                        "url": f"/sandbox/experiments/{eid}", "started": True,
                        "resumed": p["resume"], "complete": False,
                        "text": a["text"], "codes": p["findings"],
                        "plan": a["plan"]},
              [a["text"]] + ([f"  {a['detail']}"] if a["detail"] else [])
              + ["Ctrl-C once stops it after the fits in flight; finished "
                 "weeks are kept, and the same command resumes it."], None)
        pf.RUNNER_PIDS_FILE = _terminal_registry()
        pf.bng_run_kwargs = _apart(run_kwargs)
        guard = runner._caffeinate(os.getpid())
        handler = _on_signal(flag, folder)
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):     # no SIGHUP on Windows
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                old = signal.getsignal(sig)
                if old is signal.SIG_IGN:
                    continue                  # nohup's, a background job's
                signal.signal(sig, handler)
                saved[sig] = old
            except (ValueError, OSError):     # not the main thread
                continue
        X.run(s, retro_root=_retro_root(), flubnf_build=runs._git_sha(sb.REPO),
              cancelled=cancelled, after_week=progress)
        st = X.status(folder)
        if st["status"] == "error":
            lines, code = [f"{eid} ended in error: {st['error']}"], 1
        elif st["status"] in ("stopped", "interrupted"):
            lines, code = stopped(), 0
        else:
            summary = X.summary_or_problem(folder)[0]
            fig = _relwis(X.figures((summary or {}).get("overall")))
            lines = [f"Done: {eid}, {st['weeks_done']} of "
                     f"{st['weeks_total']} weeks stored."] + (
                [fig] if fig else [])
            code = 0
    except retro.SeasonStopped:
        lines, code = stopped(), 0
    except retro.EngineBuildChanged as e:     # before ResumeMismatch, its base
        why = X.status(folder)["stop_reason"] or str(e)
        lines, code = [f"Stopped {eid}: {why}"], 3
    except retro.ResumeMismatch as e:
        first = sb.split_reason(str(e))[0].rstrip(".")
        lines, code = [f"{eid} was not resumed: {first}. Delete it (flubnf "
                       f"experiment delete {eid}) to replay it here."], 1
    except Refusal as e:                      # the model changed since
        found = ([f for f in e.findings if f["tier"] != "warning"]
                 + [f for f in e.findings if f["tier"] == "warning"])
        lines, code = [_said(found, f"{eid} did not run") + "."], _code(found)
    except KeyboardInterrupt:
        lines, code = [f"Stopped {eid} now: the fits in flight were ended; "
                       "finished weeks are kept, and the same command "
                       "resumes it."], 3
    except Exception as e:
        lines, code = [f"{eid} did not run: {str(e)[:200]}"], 1
    finally:
        try:
            if folder.is_dir():
                retro.clear_flags(folder)     # a leftover STOP stops the next
        except OSError:
            pass
        pf.RUNNER_PIDS_FILE, pf.bng_run_kwargs = registry, run_kwargs
        for sig, old in saved.items():
            try:
                signal.signal(sig, old if old is not None else signal.SIG_DFL)
            except (ValueError, OSError, TypeError):
                pass
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
    _emit(as_json, None, lines, None)
    return code


def _view(eid: str) -> dict | None:
    """What `experiment show` says, built from core as the experiment's
    JSON builds it (routes/sandbox.py api_sandbox_experiment), plus its
    "badge"; None when eid names no experiment. In a student's folder on
    the runner computer it reads the queue and never scores; elsewhere a
    summary stale() names a reason for is scored again first, here. No
    console's claim is seen from here: "claimed" is false."""
    from app.core import experiments as X
    from app.core import retro, runner
    from app.core.problem_codes import Refusal
    folder = X.find(eid)
    if folder is None:
        return None
    try:
        settings = X.read(folder / X.SETTINGS)
    except Refusal:
        return None                           # changed since find
    name = _student()
    state = runner.read_state() if name else {}
    queued = runner.position(name, eid, state=state) if name else None
    refused = runner.refusal(name, eid, state=state) if name else ""
    held = "runner" if name and runner.job_of(state, name) == eid else False
    st = X.status(X.root() / eid)
    live = (bool(held) or queued is not None
            or st["status"] in retro.ACTIVE_STATUSES)
    scoring = {"pending": False, "why": "", "error": ""}
    why = "" if name else X.stale(folder)
    if why:
        try:
            X.score(folder, retro_root=_retro_root(), flubnf_build=None)
        except Exception as e:
            scoring["error"] = str(e)[:300]
    summary, problem = X.summary_or_problem(folder)
    figures = (None if summary is None else
               {"overall": X.figures(summary.get("overall")),
                "us": X.figures(summary.get("us"))})
    return {"id": eid, "settings": settings, "live": live, "claimed": False,
            "queued": queued,
            "status": {**st, "line": X.line(st, held, queued)},
            "scoring": scoring, "summary": summary, "figures": figures,
            "problem": problem, "badge": X.badge(st, held, queued, refused)}


def _view_lines(view: dict) -> list:
    """`experiment show`'s words: the badge, the four choices, the line
    while live, the figures overall and for the US (the model's, the
    shipped replay's and the one over the other), the two fingerprints
    review compares, and why there are none."""
    s, figs = view["settings"], view["figures"]

    def num(x, pct=False):
        return "n/a" if x is None else f"{x * 100:.0f}" if pct else f"{x:.3f}"

    def side(g, n=None):
        cov = g["cov"] or {}
        return (f"relWIS {num(g['rel'])} · log relWIS {num(g['log_rel'])} · "
                + " · ".join(f"{b}% {num(cov.get(b), True)}"
                             for b in ("50", "80", "95"))
                + (f" (n {n})" if n is not None else ""))
    lines = [f"{view['id']}: {view['badge'][1]}",
             f"  {s['model']} · {s['season']} · {s['size']} · Oracle step "
             f"{'on' if s['oracle'] else 'off'}"]
    if view["live"] and view["status"]["line"]:
        lines.append(f"  {view['status']['line']}")
    for label, key in (("overall", "overall"), ("US", "us")):
        if figs is None:
            break
        fig = figs[key]
        if fig is None:
            lines.append(f"  {label}: n/a")
            continue
        lines.append(f"  {label}: {side(fig['model'], fig['n'])}")
        if fig["shipped"] is not None:
            lines.append(f"    shipped: {side(fig['shipped'])}")
            vs = fig["vs_shipped"]
            lines.append(f"    vs shipped {num(vs['wis'])} "
                         f"(log {num(vs['log_wis'])})")
    summary = view["summary"] or {}
    if summary.get("model_fingerprint") and summary.get("experiment"):
        lines.append(f"  model {str(summary['model_fingerprint'])[:8]} · "
                     f"experiment {str(summary['experiment'])[:8]}")
    if view["problem"]:
        lines.append(f"  {view['problem']}")
    if view["scoring"]["error"]:
        lines.append(f"  Not scored: {view['scoring']['error']}")
    return lines


def _finding_line(f: dict) -> str:
    """'  <tier>  <CODE>  <text> (<file>:<line>)' of one finding."""
    where = f.get("file") or ""
    if where and f.get("line") is not None:
        where += f":{f['line']}"
    return (f"  {f['tier']}  {f['code']}  {f['text']}"
            + (f" ({where})" if where else ""))


# ---------------------------------------------------------------- models


@model_app.command("new")
@_interruptible
def model_new_cmd(
    name: str = typer.Argument(..., help="The new model's name (a space "
                                         "becomes _)."),
    location: str = typer.Option("", "--location", help="The hub location "
                                 "whose data data.exp holds, e.g. "
                                 "California."),
    forecast_date: str = typer.Option("", "--forecast-date", help="The "
                                      "Saturday the data is as of "
                                      "(YYYY-MM-DD), a hub vintage."),
    season_start: str = typer.Option("", "--season-start", help="data.exp's "
                                     "first week (YYYY-MM-DD); default: "
                                     "August 1 of the forecast's season."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Start a Sandbox model from the Oracle SIHRS template, for replays,
    with one location's data as of a forecast date (New model)."""
    import re

    from app.core import sandbox as sb
    from app.core.problem_codes import finding
    # a space reads as part of a name; the folder takes _ for it
    name = re.sub(r"\s+", "_", (name or "").strip())
    try:
        sb.from_shipped(name, location, forecast_date,
                        season_start=season_start, template=True)
    except Exception as e:
        reason = " ".join(str(e).split())
        code = e.code if isinstance(e, sb.SandboxError) else ""
        codes = [finding(code, reason)] if code else []
        text = f"Not created: {reason}"
        _emit(as_json, {"ok": False, "name": name, "text": text,
                        "codes": codes}, [text], _code(codes))
    text = (f"{name}: the Oracle SIHRS template, with data for "
            f"{location.strip()} as of {forecast_date.strip()}.")
    _emit(as_json, {"ok": True, "name": name, "text": text, "codes": []},
          [text], 0)


@model_app.command("check")
@_interruptible
def model_check_cmd(
    name: str = typer.Argument(..., help="The Sandbox model's name."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Check a Sandbox model's saved files and say whether it is ready for
    replays (Check)."""
    from app.core import sandbox as sb
    from app.core.problem_codes import finding
    try:
        out = sb.check(sb.read_model(name), work=sb.SANDBOX / "check",
                       name=name)
    except Exception as e:
        said = str(e)[:1500]
        out = {"ok": False, "problems": [said], "warnings": [], "facts": {},
               "codes": [finding("CHECK_FAILED", said)]}
    probs, warns = out["problems"], out["warnings"]
    machine = (out.get("facts") or {}).get("machine") or ""
    notes = "1 note" if len(warns) == 1 else f"{len(warns)} notes"
    if probs:
        head = (f"{len(probs)} problem{'' if len(probs) == 1 else 's'}: a "
                "run would fail.")
    elif warns:
        # never "can run" above a note when this computer cannot fit
        head = f"Worth a look: {notes}" + ("." if machine
                                           else "; the model can run.")
    elif machine:
        head = "No problems found in the model."
    else:
        head = "No problems found: the model can run."
    lines = [f"{name}: {head}"]
    lines += [_finding_line(f) for f in out["codes"]
              if not (f["code"] == "MACHINE" and f["text"] == machine)]
    if machine:
        lines.append(f"This computer cannot fit yet: {machine}")
    rp = out.get("replays")
    if rp:
        found = rp.get("findings") or []
        bad = [f for f in found if f["tier"] == "problem"]
        rest = [f for f in found if f["tier"] != "problem"]
        if bad:
            lines.append("Not ready for replays: "
                         + ("1 thing" if len(bad) == 1 else
                            f"{len(bad)} things") + " to fix before Register.")
        else:
            reg = rp.get("registered")
            lines.append(
                "Ready for replays: "
                + (f"these files are {reg['ref']} ({reg['short']})." if reg
                   else "Register freezes these files as a new version.")
                + ("" if not rest else " 1 note." if len(rest) == 1
                   else f" {len(rest)} notes."))
        # one already listed above is not said twice
        seen = probs + warns + ([machine] if machine else [])
        lines += [_finding_line(f) for f in bad + rest
                  if f["text"] not in seen]
    ok = bool(out["ok"]) and (rp is None or bool(rp.get("ready")))
    _emit(as_json, out, lines, 0 if ok else 1)


@model_app.command("register")
@_interruptible
def model_register_cmd(
    name: str = typer.Argument(..., help="The Sandbox model's name, exactly "
                                         "(letter case counts)."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Register a Sandbox model's saved files as the library's next version
    (Register)."""
    from app.core import library
    from app.core import sandbox as sb
    from app.core.problem_codes import Refusal, finding
    # the exact name first: where folders ignore case, BETA reads beta's
    if not (sb.MODELS.is_dir()
            and name in {p.name for p in sb.MODELS.iterdir()}):
        said = f"no Sandbox model is named {name!r} (letter case counts)"
        text = f"Not registered: {said}."
        _emit(as_json, {"ok": False, "ref": None, "text": text,
                        "codes": [finding("NAME_INVALID", said)]}, [text], 1)
    try:
        r = library.register(name)
    except Refusal as e:
        # the problems first, each with its code
        found = ([f for f in e.findings if f["tier"] == "problem"]
                 + [f for f in e.findings if f["tier"] != "problem"])
        text = _said(found, "Not registered")
        _emit(as_json, {"ok": False, "ref": None, "text": text,
                        "codes": found},
              [text] + [f"  {f['text']} ({f['code']})" for f in found[1:]],
              _code(found))
    except Exception as e:                    # the computer, not the model
        text = f"Not registered: {sb.split_reason(str(e))[0]}"
        _emit(as_json, {"ok": False, "ref": None, "text": text, "codes": []},
              [text], 1)
    s = library.short(r["fingerprint"])
    text = (f"Registered {r['ref']} ({s})." if r["new"] else
            f"{r['ref']} already holds these files ({s}); nothing new was "
            "registered.")
    notes = "; ".join(f"{f['text']} ({f['code']})" for f in r["findings"])
    _emit(as_json, {"ok": True, "ref": r["ref"], "version": r["version"],
                    "fingerprint": r["fingerprint"], "new": r["new"],
                    "text": text, "codes": r["findings"]},
          [text] + ([f"Worth a look: {notes}"] if notes else []), 0)


@model_app.command("list")
@_interruptible
def model_list_cmd(
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """The models an experiment can name: the shipped ones, then each
    registered version (the Experiments card)."""
    from app.core import experiments as X
    from app.core import library
    rows = [{**m, "oracle": m["ref"] in X.ORACLE_ON_BY_DEFAULT}
            for m in library.list_models()]
    lines = []
    for m in rows:
        when = "shipped" if m["shipped"] else str(m["registered_utc"] or "")
        lines.append(f"{m['ref']}  {m['short']}  {when}  {m['note']}".rstrip()
                     + ("" if m["intact"] else
                        "  (changed since Register: cannot be picked)"))
    _emit(as_json, rows, lines, 0)


# ----------------------------------------------------------- experiments


@experiment_app.command("start")
@_interruptible
def experiment_start_cmd(
    model: str = typer.Argument(..., help="A shipped model (sihrs) or a "
                                          "registered version (beta2@1)."),
    season: str = typer.Argument(..., help="The season to replay, e.g. "
                                           "2024-25."),
    size: Optional[str] = typer.Option(None, "--size", help="smoke, pilot or "
                                       "full; default smoke."),
    oracle: Optional[bool] = typer.Option(None, "--oracle/--no-oracle",
                                          help="The Oracle step; default: on "
                                          "for sihrs only."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Start or resume an experiment (Start); on the students' Mac Studio
    it queues for the runner, elsewhere it replays in this terminal until
    it ends."""
    # as the page's form posts them: each stripped, and a choice left out
    # or blank takes its default
    raw = {k: v.strip() for k, v in (("model", model), ("season", season),
                                      ("size", size)) if v and v.strip()}
    if oracle is not None:
        raw["oracle"] = oracle
    eid = None

    def refused(found, prefix="Not started") -> NoReturn:
        found = ([f for f in found if f["tier"] != "warning"]
                 + [f for f in found if f["tier"] == "warning"])
        said = [f"{f['text']} ({f['code']})" for f in found]
        if prefix == "Not queued":
            # the runner's floor: its detail is a second MACHINE finding,
            # a sentence of its own, said as it is
            said[1:] = [f["text"] if f["code"] == found[0]["code"]
                        == "MACHINE" else w
                        for f, w in zip(found[1:], said[1:])]
        body = {"ok": False, "id": eid, "url": None, "started": False,
                "text": _said(found, prefix) + ".", "codes": found}
        if prefix == "Not queued":
            body["queued"] = None
        _emit(as_json, body, [body["text"]] + [f"  {w}" for w in said[1:]],
              _code(found))

    try:
        from app.core import experiments as X
        from app.core import runner
        from app.core.problem_codes import Refusal, finding
        try:
            s = X.read(raw)
            eid = X.experiment_id(s)
        except Refusal as e:
            refused(e.findings)
        page = f"/sandbox/experiments/{eid}"

        def complete() -> NoReturn:
            text = f"{eid} is complete: every week is stored, nothing to fit."
            _emit(as_json, {"ok": True, "id": eid, "url": page,
                            "started": False, "resumed": False,
                            "complete": True, "text": text, "codes": []},
                  [text], 0)
        folder = X.find(eid)
        if folder is not None and X.status(folder)["complete"]:
            complete()
        name = _student()
        if name:
            try:
                q = runner.enqueue(s)
            except Refusal as e:
                refused(e.findings, "Not queued")
            except Exception as e:            # the computer, not the model
                refused([finding("MACHINE", str(e)[:300])], "Not queued")
            body = {"ok": True, "id": eid, "url": page, "started": False,
                    "resumed": False, "complete": q["state"] == "complete",
                    "text": q["text"], "codes": q["findings"],
                    "queued": runner.position(name, eid)}
            if q.get("plan"):
                body["plan"] = q["plan"]
            _emit(as_json, body, [q["text"]] + (
                [f"  {q['detail']}"] if q["detail"] else []), 0)
        why = _local_refusal(eid)
        if why is not None:
            refused([why])
        try:
            p = X.preflight(s, retro_root=_retro_root())
        except Refusal as e:
            refused(e.findings)
        except Exception as e:                # the computer, not the model
            refused([finding("MACHINE", str(e)[:300])])
        if p["complete"]:
            complete()
        a = X.started(p)
    except KeyboardInterrupt:
        text = "Not started: interrupted."
        _emit(as_json, {"ok": False, "id": eid, "url": None,
                        "started": False, "text": text, "codes": []},
              [text], 3)
    raise typer.Exit(_foreground(s, eid, p, a, as_json))


@experiment_app.command("show")
@_interruptible
def experiment_show_cmd(
    eid: str = typer.Argument(..., metavar="ID", help="The experiment's id, "
                              "as list prints it."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """One experiment: where it stands and its figures (its page and its
    JSON)."""
    view = _view(eid)
    if view is None:
        said = f"no experiment is named '{eid}'"
        _emit(as_json, {"error": said}, [said], 1)
    _emit(as_json, {k: v for k, v in view.items() if k != "badge"},
          _view_lines(view), 0)


@experiment_app.command("list")
@_interruptible
def experiment_list_cmd(
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """This Sandbox's experiments, newest first (the Experiments card)."""
    from app.core import experiments as X
    from app.core import runner
    name = _student()
    state = runner.read_state() if name else {}
    on_runner = runner.job_of(state, name) if name else ""
    rows, lines = [], []
    for r in X.list_experiments():
        queued = runner.position(name, r["id"], state=state) if name else None
        refused = runner.refusal(name, r["id"], state=state) if name else ""
        held = "runner" if on_runner and on_runner == r["id"] else False
        row = {"id": r["id"], "settings": r["settings"], "status": r["status"],
               "badge": X.badge(r["status"], held, queued, refused),
               "figures": X.figures((r["summary"] or {}).get("overall")),
               "queued": queued}
        rows.append(row)
        lines.append(f"{row['id']}  {row['badge'][1]}  "
                     f"{_relwis(row['figures'])}".rstrip())
    _emit(as_json, rows, lines or ["No experiments in this Sandbox."], 0)


@experiment_app.command("stop")
@_interruptible
def experiment_stop_cmd(
    eid: str = typer.Argument(..., metavar="ID", help="The experiment's id."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Stop an experiment after the fits in flight, or take a queued one out
    of the queue (Stop)."""
    from app.core import experiments as X
    from app.core import retro, runner
    stopping = (f"Stopping {eid} after the fits in flight; finished weeks "
                "are kept.")
    name = _student()
    if name:
        said = runner.stop(name, eid)
        ok = bool(said)
        text = (f"Took {eid} out of the queue; nothing was fitted."
                if said == "dequeued" else stopping if said == "stopping"
                else "")
    else:
        # any process's replay, a terminal's start included, polls STOP
        folder = X.find(eid)
        ok = (folder is not None
              and X.status(folder)["status"] in retro.ACTIVE_STATUSES)
        if ok:
            retro.request_stop(folder)
        text = stopping if ok else ""
    text = text or f"Nothing to stop: {eid} is not replaying."
    _emit(as_json, {"ok": ok, "id": eid, "text": text}, [text],
          0 if ok else 1)


@experiment_app.command("delete")
@_interruptible
def experiment_delete_cmd(
    eid: str = typer.Argument(..., metavar="ID", help="The experiment's id."),
    yes: bool = typer.Option(False, "--yes", help="Delete without asking."),
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """Delete an experiment's folder; the library keeps its model
    (Delete)."""
    from app.core import experiments as X
    from app.core import retro, runner
    from app.core import sandbox as sb
    try:
        tty = sys.stdin.isatty()
    except (AttributeError, ValueError):
        tty = False
    # with --json, or no terminal to answer, it never asks
    if not yes and not (tty and not as_json and typer.confirm(
            f"Delete {eid} and its stored weeks? The library keeps the "
            "model.", default=False, err=True)):
        text = "Not deleted: not confirmed."
        _emit(as_json, {"ok": False, "id": eid, "text": text, "codes": []},
              [text], 1)
    name = _student()
    try:
        # the runner's run job only, as the page's Delete: X.delete refuses
        # a record under way in any process
        n = X.delete(eid, live=runner.job_of(runner.read_state(), name)
                     if name else "")
    except Exception as e:
        text = f"Not deleted: {sb.split_reason(str(e))[0]}"
        _emit(as_json, {"ok": False, "id": eid, "text": text, "codes": []},
              [text], 1)
    text = f"Deleted {eid}; {retro.human_bytes(n)} freed."
    _emit(as_json, {"ok": True, "id": eid, "text": text, "freed": n}, [text],
          0)


# -------------------------------------------------------------- storage


@_interruptible
def storage_cmd(
    as_json: bool = typer.Option(False, "--json", help=_JSON_HELP),
):
    """The Storage tab's Sandbox line and, on the runner computer's main
    install, the students' experiments."""
    from app.core import experiments as X
    from app.core import retro, runner
    from app.core import sandbox as sb
    out = {"sandbox": sb.storage(), "students": None}
    sbx = out["sandbox"]
    lines = [f"Sandbox models and runs: {retro.human_bytes(sbx['bytes'])} "
             f"({sbx['models']} model{'' if sbx['models'] == 1 else 's'}, "
             f"{sbx['runs']} run{'' if sbx['runs'] == 1 else 's'})"]
    # the runner computer's main install only (routes/storage.py
    # _students_here): one failed stat elsewhere
    if runner.state_dir().is_dir() and not runner._in_students(sb.SANDBOX):
        su = runner.storage(size=retro.dir_size)
        state = runner.read_state()
        for r in su["rows"]:
            r["path"] = str(r["path"])
            held = ("runner" if runner.job_of(state, r["folder"]) == r["id"]
                    else False)
            r["badge"] = X.badge(r["status"], held, r["queued"], r["refused"])
        out["students"] = su
        lines.append(f"Student experiments: {len(su['rows'])} (not in the "
                     "total)")
        lines.append(f"The runner is not running. {su['why']}" if su["down"]
                     else " · ".join(su["runner"]))
        lines += [f"{r['ident']}  {r['badge'][1]}  {r['size_h']}"
                  + (f"  {' · '.join(r['parts'])}" if r["parts"] else "")
                  for r in su["rows"]]
    _emit(as_json, out, lines, 0)
