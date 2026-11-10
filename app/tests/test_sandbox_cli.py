"""The Sandbox's commands (flubnf/cli_sandbox.py): `flubnf model new |
check | register | list`, `flubnf experiment start | show | list | stop |
delete` and `flubnf storage`, each held to the route it mirrors on the
same fixtures. The help panels and a light import; each command's JSON
(one document on stdout, the words then on stderr), its words and its
exit code; a start's refusals in their order, its foreground run (the
fits registered apart, the sleep guard, the flags cleared, a line after
every week), its outcomes, its signal handlers called directly, the
console opening during the run, and its queueing in a student's folder
on the runner computer; the engine a start needs read as the console
reads it, and a terminal without the engine its clone records refused;
and the console probe (cli._console_open).

Nothing here fits, runs BNG2.pl, reads a hub, starts a console or sends
a signal: experiments.preflight and run are faked where a start would
fit, the probes of this computer (_console_open, _sweep_runner_groups,
_replay_elsewhere, _engine_ready, _caffeinate) are recorders, and the
Sandbox, STUDENTS and APP_PID_FILE live under tmp_path.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
import typer                                             # noqa: E402
from typer.testing import CliRunner                      # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.problem_codes import Refusal, finding      # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402
from app.ui.routes import storage as ui_storage          # noqa: E402
from flubnf import cli                                   # noqa: E402
from flubnf import cli_sandbox as CS                     # noqa: E402
from test_experiment_summary import _q, _store           # noqa: E402
from test_experiments import (SMOKE_FP, SMOKE_WEEKS,     # noqa: E402,F401
                              _replay, _stale_fork, season, truth)
from test_runner_folders import (experiment, student,    # noqa: E402,F401
                                 students)
from test_runner_queue import state as runner_state      # noqa: E402
from test_sandbox_experiments import (BETA, DEAD, FORM,  # noqa: E402,F401
                                      JSON, SMOKE, _hand_written, _join,
                                      alice, client, world, world_root)
from test_sandbox_placeholders import strict_bng        # noqa: E402,F401
from test_sandbox_shipped import FD, hub                 # noqa: E402,F401

REPO = Path(__file__).resolve().parents[2]
CLI = CliRunner()
#: the real probes the `here` fixture and conftest replace
_ENGINE_READY = runner._engine_ready
_RECORDED_ENGINE = runner._recorded_engine
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _cmd(*args):
    """`flubnf <args>` in this process; its result (stdout and stderr
    apart)."""
    return CLI.invoke(cli.app, [str(a) for a in args], env={"NO_COLOR": "1"},
                      terminal_width=200, catch_exceptions=False)


def _doc(r):
    """The one JSON document on stdout (json.loads refuses a second)."""
    return json.loads(r.stdout)


def _plain(obj):
    """obj as its JSON reads back: the route's answer beside the
    command's."""
    return json.loads(json.dumps(CS._finite(obj), default=str))


def _body(r):
    """A route's answer: a JSONResponse's body, else the dict it returned."""
    return json.loads(r.body) if hasattr(r, "body") else _plain(r)


class _Guard:
    def __init__(self):
        self.ended = False

    def terminate(self):
        self.ended = True


class _Here:
    """This computer as a foreground start probes it, recorded in order;
    each answer settable."""

    def __init__(self):
        self.calls, self.swept, self.guards = [], [], []
        self.console, self.busy, self.elsewhere = False, "", ""
        self.engine = True


@pytest.fixture
def here(season, tmp_path, monkeypatch):
    """No console open, the runner idle, no other replay, the engine
    ready and the sleep guard faked, each call recorded; APP_PID_FILE
    under tmp_path and the retro root the season's."""
    h = _Here()
    monkeypatch.setattr(cli, "APP_PID_FILE", tmp_path / "state" / "app.pid")

    def console_open(pidfile=None):
        h.calls.append("console")
        return h.console

    def busy():
        h.calls.append("busy")
        return h.busy

    def sweep(registry=None, wait=5.0):
        h.calls.append("sweep")
        h.swept.append(Path(registry))
        return 0

    def elsewhere():
        h.calls.append("elsewhere")
        return h.elsewhere

    def engine():
        h.calls.append("engine")
        return h.engine

    def caffeinate(pid):
        assert pid == os.getpid()
        h.guards.append(_Guard())
        return h.guards[-1]
    monkeypatch.setattr(cli, "_console_open", console_open)
    monkeypatch.setattr(runner, "busy_words", busy)
    monkeypatch.setattr(cli, "_sweep_runner_groups", sweep)
    monkeypatch.setattr(runner, "_replay_elsewhere", elsewhere)
    monkeypatch.setattr(runner, "_engine_ready", engine)
    monkeypatch.setattr(runner, "_caffeinate", caffeinate)
    monkeypatch.setattr(CS, "_retro_root", lambda: season)
    return h


def _folder(settings: dict, *, status="done", weeks=(), stored=(),
            **meta) -> Path:
    """An experiment's folder in this Sandbox: experiment.json, a run
    record freezing `weeks`, each week of `stored` stored."""
    f = X.root() / X.experiment_id(settings)
    f.mkdir(parents=True, exist_ok=True)
    L.write_json(f / X.SETTINGS, json.loads(X.settings_text(settings)))
    retro.write_meta(f, {"status": status, "started_utc": time.time() - 100,
                         "settings": {"experiment": SMOKE_FP,
                                      "weeks": list(weeks)}, **meta})
    for w in stored:
        _store(f, w, {"pf": _q(10.0)})
    return f


def _running(settings: dict, pid=None) -> Path:
    """A folder whose record says a replay of it is under way in another
    live process (os.getppid() by default)."""
    return _folder(settings, status="running", weeks=SMOKE_WEEKS,
                   pid=os.getppid() if pid is None else pid,
                   heartbeat_utc=time.time(), segment_start_utc=time.time())


# ----------------------------------------------------- 1. help and imports


def test_the_commands_sit_in_the_existing_panels_and_list_their_actions():
    group = typer.main.get_command(cli.app)
    panels = {n: group.commands[n].rich_help_panel
              for n in ("model", "storage", "experiment")}
    assert panels == {"model": "Console", "storage": "Console",
                      "experiment": "Replay & verification"}
    out = _ANSI.sub("", _cmd("--help").stdout)
    console = out.split("─ Console ", 1)[1].split("─ Replay", 1)[0]
    replay = out.split("─ Replay & verification ", 1)[1].split("─ Donor", 1)[0]
    assert re.search(r"│ model\s", console) and re.search(r"│ storage\s",
                                                           console)
    assert re.search(r"│ experiment\s", replay)
    for group_name, names in (("model", ("new", "check", "register", "list")),
                              ("experiment", ("start", "show", "list", "stop",
                                              "delete"))):
        r = _cmd(group_name, "--help")
        assert r.exit_code == 0
        listed = re.findall(r"│ (\w+)\s", _ANSI.sub("", r.stdout).split(
            "─ Commands ", 1)[1])
        assert listed == list(names), listed
    assert _cmd("storage", "--help").exit_code == 0


def test_the_module_loads_neither_pandas_nor_scipy():
    code = ("import sys; import flubnf.cli_sandbox; "
            "sys.exit(2 if 'pandas' in sys.modules else "
            "3 if 'scipy' in sys.modules else "
            "4 if any(m.startswith('app.') for m in sys.modules) else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                       capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode()[-400:]


# -------------------------------------------------------- 2. model new


def test_model_new_starts_the_template_with_the_name_folded(sandbox_root,
                                                          monkeypatch):
    calls = []

    def fake(name, location, forecast_date, **kw):
        calls.append((name, location, forecast_date, kw))
        return sb.MODELS / name
    monkeypatch.setattr(sb, "from_shipped", fake)
    r = _cmd("model", "new", " beta  2 ", "--location", "California",
             "--forecast-date", "2024-12-28", "--json")
    assert r.exit_code == 0
    assert calls == [("beta_2", "California", "2024-12-28",
                      {"season_start": "", "template": True})]
    assert _doc(r) == {"ok": True, "name": "beta_2", "codes": [],
                       "text": "beta_2: the Oracle SIHRS template, with data "
                       "for California as of 2024-12-28."}
    assert r.stderr == _doc(r)["text"] + "\n"
    # the words alone, on stdout
    r = _cmd("model", "new", "beta3", "--location", "California",
             "--forecast-date", "2024-12-28")
    assert (r.exit_code, r.stdout) == (0, "beta3: the Oracle SIHRS template, "
                                       "with data for California as of "
                                       "2024-12-28.\n")


def test_model_new_refuses_in_from_shippeds_words(sandbox_root, monkeypatch):
    r = _cmd("model", "new", "beta2", "--forecast-date", "2024-12-28",
             "--json")
    assert r.exit_code == 1
    assert _doc(r) == {"ok": False, "name": "beta2", "codes": [],
                       "text": "Not created: choose a location for the "
                       "Oracle SIHRS template"}
    assert not sb.MODELS.exists() or not any(sb.MODELS.iterdir())
    # a name Register would refuse carries its code
    r = _cmd("model", "new", "SIHRS", "--location", "California",
             "--forecast-date", "2024-12-28", "--json")
    got = _doc(r)
    assert r.exit_code == 1 and got["ok"] is False
    assert [c["code"] for c in got["codes"]] == ["NAME_RESERVED"]
    assert got["text"] == "Not created: " + got["codes"][0]["text"]

    def reserved(*a, **k):
        raise sb.SandboxError("beta is\n  taken", code="NAME_RESERVED")
    monkeypatch.setattr(sb, "from_shipped", reserved)
    r = _cmd("model", "new", "beta", "--json")
    assert r.exit_code == 1
    assert _doc(r)["text"] == "Not created: beta is taken"
    assert _doc(r)["codes"] == [finding("NAME_RESERVED", "beta is taken")]


# ------------------------------------------------------- 3. model check


def _route_check(name: str) -> dict:
    return _body(ui_sandbox.api_sandbox_check(name, "", "", ""))


def test_model_check_answers_the_routes_json(strict_bng, hub, monkeypatch):
    sb.from_shipped("beta", "Alabama", FD, template=True)
    r = _cmd("model", "check", "beta", "--json")
    got = _doc(r)
    assert got == _route_check("beta")
    assert got["ok"] and got["replays"]["ready"] and r.exit_code == 0
    assert r.stderr.startswith("beta: ")
    assert "Ready for replays: Register freezes these files as a new " \
           "version." in r.stderr
    # not ready for replays: a key a replay's model may not set
    d = sb.MODELS / "beta"
    good = (d / "priors.conf").read_text(encoding="utf-8")
    (d / "priors.conf").write_text(good + "pf_jitter = 0.2\n",
                                   encoding="utf-8", newline="\n")
    r = _cmd("model", "check", "beta", "--json")
    got = _doc(r)
    assert got == _route_check("beta")
    assert got["ok"] and not got["replays"]["ready"] and r.exit_code == 1
    assert "Not ready for replays: 1 thing to fix before Register." in r.stderr
    assert "  problem  KEY_NOT_ALLOWED  " in r.stderr
    (d / "priors.conf").write_text(good, encoding="utf-8", newline="\n")
    # a problem: no location to fill the placeholders for
    (d / sb.SOURCE_FILE).unlink()
    r = _cmd("model", "check", "beta", "--json")
    got = _doc(r)
    assert got == _route_check("beta")
    assert not got["ok"] and r.exit_code == 1
    assert "  problem  PLACEHOLDERS_UNFILLED  " in r.stderr
    n = len(got["problems"])
    assert r.stderr.startswith(f"beta: {n} problem{'' if n == 1 else 's'}: a "
                               "run would fail.\n")

    # only this computer's: Check answered, exit 0
    def machine_only(files, **kw):
        return {"ok": True, "problems": [], "warnings": [],
                "facts": {"machine": "BNG2.pl is missing"},
                "codes": [finding("MACHINE", "BNG2.pl is missing")]}
    monkeypatch.setattr(sb, "check", machine_only)
    r = _cmd("model", "check", "beta")
    assert r.exit_code == 0
    assert r.stdout == ("beta: No problems found in the model.\n"
                        "This computer cannot fit yet: BNG2.pl is missing\n")


def test_model_check_of_no_model_is_the_routes_fallback(sandbox_root):
    r = _cmd("model", "check", "nope", "--json")
    got = _doc(r)
    assert r.exit_code == 1 and got == _route_check("nope")
    assert [c["code"] for c in got["codes"]] == ["CHECK_FAILED"]
    assert (got["ok"], got["warnings"], got["facts"]) == (False, [], {})


# ---------------------------------------------------- 4. model register


def test_model_register_in_the_routes_words(strict_bng, hub, monkeypatch):
    sb.from_shipped("beta", "Alabama", FD, template=True)
    r = _cmd("model", "register", "beta", "--json")
    got = _doc(r)
    assert r.exit_code == 0
    v = L.resolve("beta@1")
    assert got == {"ok": True, "ref": "beta@1", "version": 1,
                   "fingerprint": v["fingerprint"], "new": True,
                   "text": f"Registered beta@1 ({v['fingerprint'][:8]}).",
                   "codes": got["codes"]}
    r = _cmd("model", "register", "beta")
    assert r.exit_code == 0
    assert r.stdout.splitlines()[0] == (
        f"beta@1 already holds these files ({v['fingerprint'][:8]}); "
        "nothing new was registered.")
    assert L._versions("beta") == [1]
    # refused: the problem first, with its code
    d = sb.MODELS / "beta"
    (d / "priors.conf").write_text(
        (d / "priors.conf").read_text(encoding="utf-8") + "pf_jitter = 0.2\n",
        encoding="utf-8", newline="\n")
    r = _cmd("model", "register", "beta", "--json")
    got = _doc(r)
    assert r.exit_code == 1 and (got["ok"], got["ref"]) == (False, None)
    assert got["codes"][0]["code"] == "KEY_NOT_ALLOWED"
    assert re.fullmatch(r"Not registered: priors\.conf line \d+: pf_jitter "
                        r"is not a key .* \(KEY_NOT_ALLOWED\)", got["text"])
    assert L._versions("beta") == [1]
    # the problems before the rest, whatever order the core gave
    note = finding("GAMMA_ASSUMED", "beta lacks {{GAMMA}}")
    bad = finding("KEY_NOT_ALLOWED", "priors.conf line 9: pf_jitter")

    def refuse(name):
        raise Refusal([note, bad])
    monkeypatch.setattr(L, "register", refuse)
    r = _cmd("model", "register", "beta", "--json")
    assert r.exit_code == 1
    assert _doc(r) == {"ok": False, "ref": None, "codes": [bad, note],
                       "text": "Not registered: priors.conf line 9: "
                       "pf_jitter (KEY_NOT_ALLOWED)"}
    assert r.stderr.splitlines()[1] == "  beta lacks {{GAMMA}} (GAMMA_ASSUMED)"


def test_model_register_needs_the_exact_name(strict_bng, hub, monkeypatch):
    sb.from_shipped("beta", "Alabama", FD, template=True)

    def never(name):
        raise AssertionError("registered")
    monkeypatch.setattr(L, "register", never)
    r = _cmd("model", "register", "BETA", "--json")
    said = "no Sandbox model is named 'BETA' (letter case counts)"
    assert r.exit_code == 1
    assert _doc(r) == {"ok": False, "ref": None,
                       "text": f"Not registered: {said}.",
                       "codes": [finding("NAME_INVALID", said)]}
    assert not L.root().exists()


# -------------------------------------------------------- 5. model list


def test_model_list_is_the_cards_list(strict_bng, hub):
    sb.from_shipped("beta", "Alabama", FD, template=True)
    L.register("beta")
    r = _cmd("model", "list", "--json")
    want = [{**m, "oracle": m["ref"] in X.ORACLE_ON_BY_DEFAULT}
            for m in L.list_models()]
    assert r.exit_code == 0 and _doc(r) == _plain(want)
    assert [m["oracle"] for m in _doc(r)] == [True, False, False, False]
    lines = _cmd("model", "list").stdout.splitlines()
    assert lines[0].startswith(f"sihrs  {want[0]['short']}  shipped")
    assert lines[-1].startswith(f"beta@1  {want[-1]['short']}  "
                                f"{want[-1]['registered_utc']}")
    assert "cannot be picked" not in lines[-1]
    # a version whose files changed since Register
    f = L.root() / "beta" / "1" / "model.bngl"
    f.write_text(f.read_text(encoding="utf-8") + "# later\n",
                 encoding="utf-8", newline="\n")
    line = _cmd("model", "list").stdout.splitlines()[-1]
    assert line.endswith("  (changed since Register: cannot be picked)")


# --------------------------------------------------- 6. start's refusals


def _no_run(monkeypatch):
    def never(*a, **k):
        raise AssertionError("the command replayed")
    monkeypatch.setattr(X, "run", never)
    monkeypatch.setattr(X, "replay", never)


def test_start_refuses_this_computer_in_order_and_writes_nothing(
        here, monkeypatch):
    _no_run(monkeypatch)

    def refused(words, calls):
        here.calls.clear()
        r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
        got = _doc(r)
        assert r.exit_code == 3, r.stderr
        assert got == {"ok": False, "id": SMOKE, "url": None,
                       "started": False, "text": f"Not started: {words} "
                       "(MACHINE).",
                       "codes": [finding("MACHINE", words)]}
        assert here.calls == calls
        assert not (X.root() / SMOKE).exists()
    here.console = True
    refused("the console is open on this computer: start the experiment "
            "from its Sandbox page, or quit the console first", ["console"])
    here.console = False
    here.busy = "the runner on this computer is replaying alice's x"
    refused("the runner on this computer is replaying alice's x: one replay "
            "at a time", ["console", "busy"])
    here.busy = ""
    # an experiment of this Sandbox under way: no sweep of its fits
    pilot = {**FORM, "size": "pilot"}
    live = _running(pilot)
    refused(f"experiment {live.name} is replaying on this computer: one "
            "replay at a time", ["console", "busy"])
    assert here.swept == []
    retro.write_meta(live, {**retro.read_meta(live), "status": "stopped"})
    here.elsewhere = "a replay is running on this computer (its fits, pid 7)"
    refused("a replay is running on this computer (its fits, pid 7): one "
            "replay at a time", ["console", "busy", "sweep", "elsewhere"])
    # the terminal's registry, never the console's
    assert here.swept == [cli.APP_PID_FILE.parent / "pf_runners.terminal.json"]
    assert here.swept[0] != Path(cli.PF_RUNNER_PIDS_FILE)
    here.elsewhere, here.engine = "", False
    refused("an experiment needs the particle-filter engine, which is not "
            "ready on this computer (flubnf doctor says why)",
            ["console", "busy", "sweep", "elsewhere", "engine"])
    assert not here.guards


def test_a_start_on_an_engine_older_than_the_console_is_refused(
        here, monkeypatch, tmp_path):
    # ready, but pf.prepare would refuse every week: said with this
    # computer's refusals, before the plan is read, in the engine's words
    _no_run(monkeypatch)

    def never(*a, **k):
        raise AssertionError("the plan was read")
    monkeypatch.setattr(X, "preflight", never)
    monkeypatch.setattr(pf, "PYBNF_PF", _stale_fork(tmp_path))
    words = pf.engine_stale_message()
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 3, r.stderr
    assert _doc(r) == {"ok": False, "id": SMOKE, "url": None,
                       "started": False, "text": f"Not started: {words} "
                       "(MACHINE).", "codes": [finding("MACHINE", words)]}
    assert here.calls == ["console", "busy", "sweep", "elsewhere", "engine"]
    assert not (X.root() / SMOKE).exists() and not here.guards


def test_a_start_on_the_public_engine_needs_its_venv_alone(here, tmp_path,
                                                           monkeypatch):
    # the real _engine_ready (the console's test): the private venv and
    # fork missing, the public venv there
    from flubnf import settings
    monkeypatch.setattr(runner, "_engine_ready", _ENGINE_READY)
    gone = tmp_path / "no-private"
    monkeypatch.setattr(settings, "PY_ENGINE", gone / "bin" / "python")
    monkeypatch.setattr(settings, "PYBNF", gone / "fork")
    monkeypatch.setattr(pf, "PYBNF_PF", gone / "fork")
    py = tmp_path / "public" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(py))
    monkeypatch.setattr(pf, "engine_current", lambda: True)  # no venv probe
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert CS._local_refusal(SMOKE) is None
    assert here.calls == ["console", "busy", "sweep", "elsewhere"]
    # the private engine, which this computer lacks, is refused there
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    assert CS._local_refusal(SMOKE) == finding(
        "MACHINE", "an experiment needs the particle-filter engine, which is "
        "not ready on this computer (flubnf doctor says why)")


def test_a_start_from_a_terminal_without_the_clones_engine_is_refused(
        here, tmp_path, monkeypatch):
    # the clone records public (setup_engine.sh --public) and this
    # terminal never read it: refused with this computer's refusals,
    # before the engine is probed, and nothing written
    from flubnf import settings
    _no_run(monkeypatch)
    monkeypatch.setattr(runner, "_recorded_engine", _RECORDED_ENGINE)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    clone = tmp_path / "clone"
    clone.mkdir()
    monkeypatch.setattr(sb, "REPO", clone)
    monkeypatch.setattr(pf, "engine_current", lambda: True)  # no venv probe
    words = ("this install records FLUBNF_ENGINE=public (.flubnf.env) but "
             "this Terminal runs the private engine: run `. ./.flubnf.env` "
             "in the clone first")
    (clone / ".flubnf.env").write_text("export FLUBNF_ENGINE=public\n",
                                       encoding="utf-8")
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 3, r.stderr
    assert _doc(r) == {"ok": False, "id": SMOKE, "url": None,
                       "started": False, "text": f"Not started: {words} "
                       "(MACHINE).", "codes": [finding("MACHINE", words)]}
    assert here.calls == ["console", "busy", "sweep", "elsewhere"]
    assert not (X.root() / SMOKE).exists() and not here.guards
    # the terminal that read it, and a clone that records none, pass
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert CS._local_refusal(SMOKE) is None
    monkeypatch.delenv("FLUBNF_ENGINE")
    (clone / ".flubnf.env").unlink()
    assert CS._local_refusal(SMOKE) is None
    # the clone records the private engine (setup_engine.sh --private) and
    # this terminal names the public one: refused the same way
    (clone / ".flubnf.env").write_text("export FLUBNF_ENGINE=private\n",
                                       encoding="utf-8")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    words = ("this install records FLUBNF_ENGINE=private (.flubnf.env) but "
             "this Terminal runs the public engine: run `. ./.flubnf.env` "
             "in the clone first")
    assert CS._local_refusal(SMOKE) == finding("MACHINE", words)


def test_start_refuses_the_settings_and_answers_complete(here, monkeypatch):
    _no_run(monkeypatch)
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--size", "huge",
             "--json")
    got = _doc(r)
    assert r.exit_code == 1 and (got["id"], got["url"]) == (None, None)
    assert [c["code"] for c in got["codes"]] == ["SIZE_UNKNOWN"]
    assert got["text"] == ("Not started: size 'huge' is not one of smoke, "
                           "pilot, full (SIZE_UNKNOWN).")
    assert here.calls == []
    # the Oracle step as given, else the model's default
    here.console = True
    for flag, eid in (("--no-oracle", "sihrs_2024-25_smoke"),
                      ("--oracle", "nope-v1_2024-25_smoke_oracle")):
        model = "sihrs" if flag == "--no-oracle" else "nope@1"
        r = _cmd("experiment", "start", model, "2024-25", flag, "--json")
        assert (r.exit_code, _doc(r)["id"]) == (3, eid)
    # as the page's form posts them: stripped, a blank choice its default
    r = _cmd("experiment", "start", " sihrs ", " 2024-25", "--size", " ",
             "--json")
    assert (r.exit_code, _doc(r)["id"]) == (3, SMOKE)
    here.console = False
    r = _cmd("experiment", "start", " ", "2024-25", "--json")
    assert r.exit_code == 1
    assert [c["code"] for c in _doc(r)["codes"]] == ["FIELD_MISSING"]
    r = _cmd("experiment", "start", "nope@1", "2024-25", "--json")
    got = _doc(r)
    assert r.exit_code == 1 and got["id"] == "nope-v1_2024-25_smoke"
    assert [c["code"] for c in got["codes"]] == ["MODEL_NOT_FOUND"]
    assert not X.root().exists() or not any(X.root().iterdir())
    # complete: answered before anything is probed or run
    _folder(FORM, weeks=SMOKE_WEEKS, stored=SMOKE_WEEKS)
    here.calls.clear()
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 0 and here.calls == []
    assert _doc(r) == {"ok": True, "id": SMOKE,
                       "url": f"/sandbox/experiments/{SMOKE}",
                       "started": False, "resumed": False, "complete": True,
                       "codes": [], "text": f"{SMOKE} is complete: every "
                       "week is stored, nothing to fit."}


# ------------------------------------------------------ 7. a local start


@pytest.fixture
def planned(world, here, monkeypatch):
    """The smoke's real preflight (a shipped replay of 2024-25 to compare
    with), then experiments.preflight faked to answer it; the plan."""
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    p = X.preflight(dict(FORM), retro_root=world_root())
    seen = []

    def preflight(settings, *, retro_root):
        seen.append((dict(settings), retro_root))
        return p
    monkeypatch.setattr(X, "preflight", preflight)
    return {"p": p, "seen": seen}


def test_a_local_start_answers_as_the_page_before_it_fits(planned, here,
                                                          monkeypatch):
    # the page's answer to the same plan (its replay faked: nothing fits)
    monkeypatch.setattr(X, "replay", lambda *a, **k: planned["p"])
    page = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    _join()
    registry, run_kwargs = pf.RUNNER_PIDS_FILE, pf.bng_run_kwargs
    calls = []

    def run(settings, **kw):
        sys.stdout.flush()
        calls.append({"settings": dict(settings), **kw,
                      "printed": sys.stdout.buffer.getvalue().decode(),
                      "registry": pf.RUNNER_PIDS_FILE,
                      "bng": pf.bng_run_kwargs({"A": "1"}),
                      "guards": len(here.guards)})
        folder = X.root() / SMOKE
        folder.mkdir(parents=True, exist_ok=True)
        retro.request_stop(folder)            # cleared at the end
        return planned["p"]
    monkeypatch.setattr(X, "run", run)
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 0, r.stderr
    got = _doc(r)
    assert got == page
    assert (got["started"], got["resumed"], got["complete"]) == (True, False,
                                                                 False)
    # the page's start and the command's, the same settings and root
    assert planned["seen"] == [(X.read(FORM), world_root())] * 2
    # the answer was on stdout before the replay began
    [c] = calls
    assert json.loads(c["printed"]) == got
    assert c["settings"] == X.read(FORM)
    assert c["retro_root"] == world_root()
    assert isinstance(c["flubnf_build"], str) and c["flubnf_build"]
    assert callable(c["cancelled"]) and callable(c["after_week"])
    # the fits registered apart while it ran, put back after
    assert c["registry"] == (cli.APP_PID_FILE.parent
                             / "pf_runners.terminal.json")
    assert pf.RUNNER_PIDS_FILE == registry
    # BNG2.pl's runs (a week's netgen) in a group of their own meanwhile,
    # out of the terminal's Ctrl-C, as the fits are; put back after
    apart = ({"start_new_session": True} if os.name == "posix" else
             {"creationflags": pf._CREATE_NEW_PROCESS_GROUP})
    assert c["bng"] == {**run_kwargs({"A": "1"}), **apart}
    assert pf.bng_run_kwargs is run_kwargs
    assert c["guards"] == 1 and here.guards[0].ended
    assert not retro.stop_path(X.root() / SMOKE).exists()
    words = r.stderr.splitlines()
    assert words[0] == got["text"]
    assert words[2] == ("Ctrl-C once stops it after the fits in flight; "
                        "finished weeks are kept, and the same command "
                        "resumes it.")
    assert words[-1] == f"Done: {SMOKE}, 0 of 0 weeks stored."


def test_a_local_start_says_each_week_and_puts_everything_back(
        planned, here, monkeypatch):
    registry, pf_bng_run_kwargs = pf.RUNNER_PIDS_FILE, pf.bng_run_kwargs

    def run(settings, *, after_week, **kw):
        folder = X.root() / SMOKE
        retro.write_meta(folder, {"status": "running", "pid": os.getpid(),
                                  "heartbeat_utc": time.time(),
                                  "settings": {"experiment": SMOKE_FP,
                                               "weeks": SMOKE_WEEKS}})
        _store(folder, SMOKE_WEEKS[0], {"pf": _q(10.0)})
        after_week(SMOKE_WEEKS[0])
        after_week(SMOKE_WEEKS[1])

        def broken(*a):
            raise OSError("gone")
        real, retro.week_done = retro.week_done, broken
        try:
            after_week(SMOKE_WEEKS[1])        # a line it cannot say: no raise
        finally:
            retro.week_done = real
        raise RuntimeError("the disk is full")
    monkeypatch.setattr(X, "run", run)
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 1
    assert _doc(r)["started"] is True                 # the one document
    lines = r.stderr.splitlines()
    assert f"  {SMOKE_WEEKS[0]}: stored · 1 of 2 weeks" in lines
    assert (f"  {SMOKE_WEEKS[1]}: not stored (its folder's failures.log "
            "says why) · 1 of 2 weeks") in lines
    assert lines[-1] == f"{SMOKE} did not run: the disk is full"
    assert pf.RUNNER_PIDS_FILE == registry
    assert pf.bng_run_kwargs is pf_bng_run_kwargs


# ------------------------------------------------------------ 8. outcomes


@pytest.mark.parametrize("raised, code, said", [
    (retro.SeasonStopped("stop requested"), 0,
     f"Stopped {SMOKE}: 0 of 0 weeks stored; the same command resumes it."),
    (retro.EngineBuildChanged("2024-25: stopped before 2025-01-11"), 3,
     f"Stopped {SMOKE}: 2024-25: stopped before 2025-01-11"),
    (retro.ResumeMismatch("2024-25 at x holds a replay of experiment "
                          "aaaaaaaa; this run is bbbbbbbb."), 1,
     f"{SMOKE} was not resumed: 2024-25 at x holds a replay of experiment "
     f"aaaaaaaa; this run is bbbbbbbb. Delete it (flubnf experiment delete "
     f"{SMOKE}) to replay it here."),
    (Refusal(finding("MODEL_CHANGED", "sihrs is 0000 now")), 1,
     f"{SMOKE} did not run: sihrs is 0000 now (MODEL_CHANGED)."),
    (RuntimeError("PF runners timed out"), 1,
     f"{SMOKE} did not run: PF runners timed out"),
    (KeyboardInterrupt(), 3,
     f"Stopped {SMOKE} now: the fits in flight were ended; finished weeks "
     "are kept, and the same command resumes it."),
], ids=["stopped", "engine-changed", "resume-mismatch", "model-changed",
        "failed", "interrupted"])
def test_each_outcome_of_a_local_start(planned, here, monkeypatch, raised,
                                       code, said):
    registry = pf.RUNNER_PIDS_FILE

    def run(*a, **k):
        raise raised
    monkeypatch.setattr(X, "run", run)
    r = _cmd("experiment", "start", "sihrs", "2024-25")
    assert r.exit_code == code, r.stdout
    assert r.stdout.splitlines()[-1] == said
    assert pf.RUNNER_PIDS_FILE == registry and here.guards[0].ended


def test_a_stop_reason_and_an_error_are_said(planned, here, monkeypatch):
    def run(*a, **k):
        retro.write_meta(X.root() / SMOKE, {
            "status": "stopped", "stop_reason": "Stopped before 2025-01-11.",
            "settings": {"experiment": SMOKE_FP, "weeks": SMOKE_WEEKS}})
        raise retro.SeasonStopped("stop requested")
    monkeypatch.setattr(X, "run", run)
    r = _cmd("experiment", "start", "sihrs", "2024-25")
    assert (r.exit_code, r.stdout.splitlines()[-1]) == (
        0, f"Stopped {SMOKE}: 0 of 2 weeks stored; the same command resumes "
        "it. Stopped before 2025-01-11.")

    def errs(*a, **k):
        retro.write_meta(X.root() / SMOKE, {
            "status": "error: 2024-12-28: no data",
            "settings": {"experiment": SMOKE_FP, "weeks": SMOKE_WEEKS}})
        return planned["p"]
    monkeypatch.setattr(X, "run", errs)
    r = _cmd("experiment", "start", "sihrs", "2024-25")
    assert (r.exit_code, r.stdout.splitlines()[-1]) == (
        1, f"{SMOKE} ended in error: 2024-12-28: no data")


def test_an_interrupt_before_the_run_is_not_a_start(here, season,
                                                    monkeypatch):
    def interrupted(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(X, "preflight", interrupted)
    _no_run(monkeypatch)
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 3
    assert _doc(r) == {"ok": False, "id": SMOKE, "url": None,
                       "started": False, "codes": [],
                       "text": "Not started: interrupted."}


def test_an_interrupt_before_the_answer_is_not_a_start(planned, here,
                                                       monkeypatch):
    # after the preflight, while the start's words are worked out
    def interrupted(p):
        raise KeyboardInterrupt
    monkeypatch.setattr(X, "started", interrupted)
    _no_run(monkeypatch)
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 3
    assert _doc(r)["text"] == "Not started: interrupted."
    assert not here.guards


@pytest.mark.parametrize("args, where, name", [
    (("experiment", "show", SMOKE), CS, "_view"),
    (("model", "check", "beta"), sb, "read_model"),
    (("storage",), sb, "storage"),
], ids=["show", "check", "storage"])
def test_a_ctrl_c_in_any_command_exits_3_not_130(sandbox_root, monkeypatch,
                                                 args, where, name):
    def interrupted(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(where, name, interrupted)
    r = _cmd(*args)
    assert (r.exit_code, r.stdout) == (3, "Interrupted.\n")
    r = _cmd(*args, "--json")
    assert (r.exit_code, r.stdout, r.stderr) == (3, "", "Interrupted.\n")


# ------------------------------------------------------------- 9. signals


def test_the_first_ctrl_c_stops_after_the_fits_the_second_at_once(tmp_path,
                                                                  capsys):
    folder = tmp_path / "x"
    folder.mkdir()
    flag = {"stop": False, "err": False}
    handler = CS._on_signal(flag, folder)
    handler(signal.SIGINT, None)                 # no raise
    assert flag["stop"] and retro.stop_path(folder).exists()
    assert capsys.readouterr().out == ("Stopping after the fits in flight "
                                       "(Ctrl-C again to stop now).\n")
    retro.clear_flags(folder)
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGINT, None)
    assert retro.stop_path(folder).exists()
    # once it has raised, a third does nothing: the round's kill of its
    # fits and the put-back are not cut short
    handler(signal.SIGINT, None)
    handler(signal.SIGTERM, None)
    # SIGTERM (and SIGHUP, the terminal closing) stop at once
    retro.clear_flags(folder)
    flag = {"stop": False, "err": True}
    with pytest.raises(KeyboardInterrupt):
        CS._on_signal(flag, folder)(signal.SIGTERM, None)
    assert flag["stop"] and retro.stop_path(folder).exists()
    # a folder not made yet is never made: the flag alone stops it
    gone = tmp_path / "not-yet"
    flag = {"stop": False, "err": True}
    CS._on_signal(flag, gone)(signal.SIGINT, None)
    assert flag["stop"] and not gone.exists()
    assert "Stopping after" in capsys.readouterr().err


def test_the_handlers_are_installed_for_the_run_and_put_back(planned, here,
                                                             monkeypatch):
    before = signal.getsignal(signal.SIGINT)
    term = signal.getsignal(signal.SIGTERM)
    seen = {}

    def run(settings, *, cancelled, **kw):
        seen["int"] = signal.getsignal(signal.SIGINT)
        seen["term"] = signal.getsignal(signal.SIGTERM)
        seen["first"] = cancelled()
        here.console = True                      # the console opens
        seen["then"] = cancelled()
        seen["reason"] = retro.read_meta(X.root() / SMOKE).get("stop_reason")
        # the first Ctrl-C, as the handler is called: STOP, and a stop
        seen["int"](signal.SIGINT, None)
        seen["stop"] = retro.stop_path(X.root() / SMOKE).exists()
        here.console = False
        seen["after"] = cancelled()
        raise retro.SeasonStopped("stop requested")
    monkeypatch.setattr(X, "run", run)
    # ignored before (as under nohup): left ignored
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        r = _cmd("experiment", "start", "sihrs", "2024-25")
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGTERM, term)
    assert r.exit_code == 0, r.stdout
    assert seen["int"] is not before and callable(seen["int"])
    assert seen["term"] is signal.SIG_IGN
    assert signal.getsignal(signal.SIGINT) is before
    assert (seen["first"], seen["then"], seen["after"]) == (False, True, True)
    assert seen["reason"] == ("Stopped before the next week: the console was "
                              "opened on this computer. Finished weeks are "
                              "kept; Start on its page resumes it.")
    assert seen["stop"] and not retro.stop_path(X.root() / SMOKE).exists()
    assert "Stopping after the fits in flight (Ctrl-C again to stop now)." \
        in r.stdout


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="no SIGHUP here")
def test_the_terminal_closing_is_handled_and_nohup_left_alone(planned, here,
                                                              monkeypatch):
    hup, seen = signal.getsignal(signal.SIGHUP), []

    def run(*a, **k):
        seen.append(signal.getsignal(signal.SIGHUP))
        raise retro.SeasonStopped("stop requested")
    monkeypatch.setattr(X, "run", run)
    try:
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        assert _cmd("experiment", "start", "sihrs", "2024-25").exit_code == 0
        assert callable(seen[-1])                # the start's handler
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL
        # under nohup: ignored before, so ignored throughout
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        assert _cmd("experiment", "start", "sihrs", "2024-25").exit_code == 0
        assert seen[-1] is signal.SIG_IGN
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, hup)


def test_the_sleep_guard_has_a_session_of_its_own(monkeypatch):
    # a terminal's Ctrl-C reaches its whole process group: the first one,
    # the Stop, must leave the guard up while the fits in flight finish
    calls = []

    def popen(args, **kw):
        calls.append((args, kw))
        return "guard"
    monkeypatch.setattr(runner, "sys", types.SimpleNamespace(
        platform="darwin"))
    monkeypatch.setattr(runner, "subprocess", types.SimpleNamespace(
        Popen=popen, DEVNULL=subprocess.DEVNULL))
    assert runner._caffeinate(4242) == "guard"
    [(args, kw)] = calls
    assert args == ["caffeinate", "-i", "-w", "4242"]
    assert kw["start_new_session"] is True


# --------------------------------------- 10. a start in a student's folder


def _queued_answer(eid: str) -> dict:
    return {"id": eid, "state": "queued", "position": 1, "wait_s": 0.0,
            "estimate": {"seconds": 180.0}, "reference": None,
            "plan": {"model": "sihrs", "season": "2024-25"},
            "findings": [finding("NO_REFERENCE", "nothing to compare")],
            "runner": True, "free": 1, "text": f"Queued {eid}: 1st in line "
            "on the runner.", "detail": "It runs about 3:00 once it starts.",
            "kind": "ok"}


def test_in_a_student_folder_start_queues_as_the_page(alice, here,
                                                      monkeypatch):
    _no_run(monkeypatch)

    def never(*a, **k):
        raise AssertionError("preflighted")
    monkeypatch.setattr(X, "preflight", never)
    asked = []

    def enqueue(source):
        s = X.read(source)
        eid = X.experiment_id(s)
        asked.append(s)
        f = X.root() / eid
        f.mkdir(parents=True, exist_ok=True)
        L.write_json(f / X.SETTINGS, json.loads(X.settings_text(s)))
        (f / X.QUEUED).write_bytes(b"")
        return _queued_answer(eid)
    monkeypatch.setattr(runner, "enqueue", enqueue)
    page = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 0
    got = _doc(r)
    assert got == page and got["queued"]["position"] == 1
    assert (got["started"], got["complete"], got["plan"]) == (
        False, False, {"model": "sihrs", "season": "2024-25"})
    assert asked == [X.read(FORM)] * 2 and here.calls == []
    assert r.stderr == (f"Queued {SMOKE}: 1st in line on the runner.\n"
                        "  It runs about 3:00 once it starts.\n")


def test_in_a_student_folder_the_floor_is_not_queued(alice, here,
                                                     monkeypatch):
    first = f"{SMOKE} needs about 1.0 GB of disk while it runs"
    second = ("The experiments queued ahead of it keep 0 B. Delete "
              "experiments you no longer need, or ask Ely to free space.")

    def floor(source):
        raise Refusal([finding("MACHINE", first), finding("MACHINE", second)])
    monkeypatch.setattr(runner, "enqueue", floor)
    page = client.post("/sandbox/experiments", data=FORM, headers=JSON).json()
    r = _cmd("experiment", "start", "sihrs", "2024-25", "--json")
    assert r.exit_code == 3
    got = _doc(r)
    assert got == page
    assert (got["ok"], got["id"], got["url"], got["queued"]) == (
        False, SMOKE, None, None)
    assert got["text"] == f"Not queued: {first} (MACHINE)."
    assert r.stderr.splitlines() == [got["text"], f"  {second}"]
    assert not (alice / "experiments" / SMOKE).exists()


# ---------------------------------------------------------------- 11. show


def _route_view(eid: str) -> dict:
    return _body(ui_sandbox.api_sandbox_experiment(eid))


def test_show_is_the_experiments_json(world, truth, here, monkeypatch):
    folder = _hand_written(monkeypatch, truth)

    def never(*a, **k):
        raise AssertionError("scored")
    monkeypatch.setattr(X, "score", never)
    r = _cmd("experiment", "show", BETA, "--json")
    assert r.exit_code == 0
    got = _doc(r)
    assert got == _route_view(BETA)
    assert got["figures"]["overall"]["model"]["rel"] == 0.75
    lines = r.stderr.splitlines()
    assert lines[:2] == [f"{BETA}: done",
                         "  beta2@3 · 2024-25 · smoke · Oracle step off"]
    assert lines[2] == ("  overall: relWIS 0.750 · log relWIS 0.900 · 50% 48 "
                        "· 80% 79 · 95% 96 (n 100)")
    assert lines[3] == ("    shipped: relWIS 0.800 · log relWIS 0.950 · 50% "
                        "40 · 80% 70 · 95% 90")
    assert lines[4] == f"    vs shipped {75 / 80:.3f} (log {18 / 19:.3f})"
    assert lines[5:] == ["  US: n/a", "  model mmmmmmmm · experiment "
                         "eeeeeeee"]
    # a newer FluBNF's summary, and one that cannot be read
    obj = json.loads((folder / X.SUMMARY).read_text(encoding="utf-8"))
    (folder / X.SUMMARY).write_text(json.dumps({**obj, "format_version": 2}),
                                    encoding="utf-8", newline="\n")
    got = _doc(_cmd("experiment", "show", BETA, "--json"))
    assert got == _route_view(BETA) and got["summary"] is None
    assert got["problem"] == ("summary.json was written by a newer FluBNF "
                              "(format_version 2); this one reads 1 only.")
    monkeypatch.setattr(X, "score", lambda *a, **k: None)
    (folder / X.SUMMARY).write_text("{not json", encoding="utf-8")
    r = _cmd("experiment", "show", BETA, "--json")
    got = _doc(r)
    assert got == _route_view(BETA)
    assert (got["summary"], got["figures"], got["problem"]) == (
        None, None, "summary.json cannot be read")
    assert r.stderr.splitlines()[-1] == "  summary.json cannot be read"
    r = _cmd("experiment", "show", "nope_2024-25_smoke", "--json")
    assert r.exit_code == 1
    assert _doc(r) == {"error": "no experiment is named 'nope_2024-25_smoke'"}


def test_show_rescores_a_stale_summary_here_and_prints_no_nan(
        world, truth, here, monkeypatch):
    nan = float("nan")
    folder = _hand_written(monkeypatch, truth,
                           us={"n": 4, "base_wis": nan, "base_log_wis": 1.0,
                               "model": {"wis": 1.0, "log_wis": nan}})
    truth.write_text(truth.read_text(encoding="utf-8") + "\n",
                     encoding="utf-8", newline="\n")
    assert X.stale(folder) == "the truth data changed"
    scored = []

    def score(f, *, retro_root, flubnf_build):
        scored.append((f, retro_root, flubnf_build))
        raise OSError("the disk is full")
    monkeypatch.setattr(X, "score", score)
    r = _cmd("experiment", "show", BETA, "--json")
    assert r.exit_code == 0
    assert scored == [(folder, world_root(), None)]
    assert "NaN" not in r.stdout
    got = json.loads(r.stdout, parse_constant=lambda c: pytest.fail(c))
    assert got["scoring"] == {"pending": False, "why": "",
                              "error": "the disk is full"}
    assert got["figures"]["us"]["model"]["log_rel"] is None
    assert "  Not scored: the disk is full" in r.stderr


def test_show_in_a_student_folder_reads_the_queue_and_never_scores(
        alice, truth, here, monkeypatch):
    folder = _hand_written(monkeypatch, truth)
    truth.write_text(truth.read_text(encoding="utf-8") + "\n",
                     encoding="utf-8", newline="\n")
    assert X.stale(folder)

    def never(*a, **k):
        raise AssertionError("scored in a student's folder")
    monkeypatch.setattr(X, "score", never)
    got = _doc(_cmd("experiment", "show", BETA, "--json"))
    assert got == _route_view(BETA) and got["queued"] is None
    # a job waiting in the queue
    f = _folder(FORM, status="stopped", weeks=SMOKE_WEEKS)
    (f / X.QUEUED).write_bytes(b"")
    r = _cmd("experiment", "show", SMOKE, "--json")
    got = _doc(r)
    assert got == _route_view(SMOKE)
    assert got["live"] is True and got["queued"]["position"] == 1
    assert got["status"]["line"].startswith("Queued · 1st in line")
    assert r.stderr.splitlines()[0] == f"{SMOKE}: queued · 1st in line"
    assert r.stderr.splitlines()[2] == "  " + got["status"]["line"]


# ---------------------------------------------------------------- 12. list


def test_list_gives_the_cards_rows_without_summaries(world, truth, here,
                                                     monkeypatch):
    _hand_written(monkeypatch, truth)
    _folder(FORM, status="stopped", weeks=SMOKE_WEEKS,
            stored=SMOKE_WEEKS[:1])
    r = _cmd("experiment", "list", "--json")
    rows = _doc(r)
    assert r.exit_code == 0
    assert [set(row) for row in rows] == [
        {"id", "settings", "status", "badge", "figures", "queued"}] * 2
    card = ui_sandbox._experiment_gallery()["rows"]
    assert [(row["id"], row["badge"], row["figures"]) for row in rows] == [
        (c["id"], list(c["badge"]), _plain(c["fig"])) for c in card]
    lines = _cmd("experiment", "list").stdout.splitlines()
    beta = next(x for x in lines if x.startswith(BETA))
    assert beta.endswith("  relWIS 0.750 (shipped 0.800)")
    assert f"{SMOKE}  stopped · 1 of 2 weeks" in lines
    retro.delete_tree(X.root())
    assert _cmd("experiment", "list").stdout == ("No experiments in this "
                                                 "Sandbox.\n")
    assert _doc(_cmd("experiment", "list", "--json")) == []


# ---------------------------------------------------------------- 13. stop


def test_stop_writes_stop_for_a_replay_under_way(here, monkeypatch):
    f = _running(FORM)
    r = _cmd("experiment", "stop", SMOKE, "--json")
    assert r.exit_code == 0
    assert _doc(r) == {"ok": True, "id": SMOKE, "text": f"Stopping {SMOKE} "
                       "after the fits in flight; finished weeks are kept."}
    assert retro.stop_path(f).exists()
    retro.clear_flags(f)
    retro.write_meta(f, {**retro.read_meta(f), "status": "stopped"})
    r = _cmd("experiment", "stop", SMOKE)
    assert (r.exit_code, r.stdout) == (1, f"Nothing to stop: {SMOKE} is not "
                                       "replaying.\n")
    assert not retro.stop_path(f).exists()
    r = _cmd("experiment", "stop", "nope_2024-25_smoke")
    assert r.exit_code == 1 and not (X.root() / "nope_2024-25_smoke").exists()


def test_stop_in_a_student_folder_asks_the_runner(alice, monkeypatch):
    for said, ok, text in (
            ("dequeued", True, f"Took {SMOKE} out of the queue; nothing was "
             "fitted."),
            ("stopping", True, f"Stopping {SMOKE} after the fits in flight; "
             "finished weeks are kept."),
            ("", False, f"Nothing to stop: {SMOKE} is not replaying.")):
        monkeypatch.setattr(runner, "stop", lambda name, eid, _s=said: _s)
        page = client.post("/sandbox/stop", data={"experiment": SMOKE},
                           headers=JSON).json()
        r = _cmd("experiment", "stop", SMOKE, "--json")
        assert _doc(r) == page == {"ok": ok, "id": SMOKE, "text": text}
        assert r.exit_code == (0 if ok else 1)


# -------------------------------------------------------------- 14. delete


def test_delete_needs_its_yes_and_refuses_a_replay_under_way(here):
    f = _folder(FORM, weeks=SMOKE_WEEKS, stored=SMOKE_WEEKS[:1])
    unconfirmed = {"ok": False, "id": SMOKE, "codes": [],
                   "text": "Not deleted: not confirmed."}
    r = _cmd("experiment", "delete", SMOKE, "--json")
    assert (r.exit_code, _doc(r)) == (1, unconfirmed) and f.is_dir()
    # no terminal to answer: never asked
    r = _cmd("experiment", "delete", SMOKE)
    assert (r.exit_code, r.stdout) == (1, "Not deleted: not confirmed.\n")
    assert f.is_dir()
    n = retro.dir_size(f)
    r = _cmd("experiment", "delete", SMOKE, "--yes", "--json")
    assert r.exit_code == 0 and not f.exists()
    assert _doc(r) == {"ok": True, "id": SMOKE, "freed": n,
                       "text": f"Deleted {SMOKE}; {retro.human_bytes(n)} "
                       "freed."}
    f = _running(FORM)
    r = _cmd("experiment", "delete", SMOKE, "--yes", "--json")
    assert r.exit_code == 1 and f.is_dir()
    assert _doc(r) == {"ok": False, "id": SMOKE, "codes": [],
                       "text": f"Not deleted: {SMOKE} is replaying in "
                       "another process; stop it first"}


def test_delete_refuses_the_runners_job(alice, students):
    f = _folder(FORM, status="stopped", weeks=SMOKE_WEEKS)
    runner_state(students, job={"kind": "run", "folder": "alice",
                                "id": SMOKE, "size": "smoke",
                                "pid": os.getpid(), "keep_bytes": 0})
    r = _cmd("experiment", "delete", SMOKE, "--yes", "--json")
    assert r.exit_code == 1 and f.is_dir()
    assert _doc(r)["text"] == f"Not deleted: {SMOKE} is replaying; stop it " \
        "first"
    # once the runner is not running, its job holds nothing
    runner_state(students, job={"kind": "run", "folder": "alice",
                                "id": SMOKE}, pid=DEAD)
    assert _cmd("experiment", "delete", SMOKE, "--yes").exit_code == 0
    assert not f.exists()


# ------------------------------------------------------------- 15. storage


def test_storage_off_the_runner_is_the_sandbox_line(sandbox_root):
    r = _cmd("storage", "--json")
    got = _doc(r)
    assert r.exit_code == 0 and got == {"sandbox": sb.storage(),
                                        "students": None}
    assert ui_storage._students_here() is False
    assert _cmd("storage").stdout == ("Sandbox models and runs: 0 B "
                                      "(0 models, 0 runs)\n")


def test_storage_on_the_runner_computer_lists_the_students(sandbox_root,
                                                           students,
                                                           monkeypatch):
    monkeypatch.setattr(runner, "_free", lambda: 500 * runner.GiB)
    top = student(students, "alice")
    f = experiment(top, weeks=["2024-12-28"], queued=True,
                   meta={"status": "stopped"})
    runner_state(students)
    assert ui_storage._students_here() is True
    r = _cmd("storage", "--json")
    got = _doc(r)
    [row] = got["students"]["rows"]
    want = ui_storage._student_experiments()
    assert row["path"] == str(f) and row["ident"] == f"alice/{f.name}"
    assert row["badge"] == list(want["rows"][0]["badge"])
    assert got["students"]["runner"] == want["runner"]
    assert "free" not in got and "floor" not in got
    lines = _cmd("storage").stdout.splitlines()
    assert lines[1] == "Student experiments: 1 (not in the total)"
    assert lines[2] == " · ".join(want["runner"])
    assert lines[3].startswith(f"alice/{f.name}  {row['badge'][1]}  "
                               f"{row['size_h']}  queued ")
    # a student's clone there: its own Sandbox line only
    monkeypatch.setattr(sb, "SANDBOX", top)
    assert ui_storage._students_here() is False
    assert _doc(_cmd("storage", "--json"))["students"] is None


# ------------------------------------------------------- 16. the exit code


def test_the_exit_code_of_a_refusal():
    machine = finding("MACHINE", "x")
    assert CS._code([machine, finding("SIZE_UNKNOWN", "y")]) == 1
    assert CS._code([machine, machine]) == 3
    assert CS._code([finding("GAMMA_ASSUMED", "z"), machine]) == 3
    assert CS._code([]) == 1
    assert CS._code([finding("GAMMA_ASSUMED", "z")]) == 1


# ------------------------------------------------------ 17. _console_open


def test_console_open_reads_the_pidfile_and_never_raises(tmp_path,
                                                         monkeypatch):
    pidfile = tmp_path / "app.pid"
    alive, ancestors = {4242}, set()
    cmdline = {4242: "/x/.venv/bin/flubnf app"}
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: pid in alive)
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: cmdline.get(pid, ""))
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: set(ancestors))
    assert cli._console_open(pidfile) is False             # no pidfile
    pidfile.write_text("4242")
    assert cli._console_open(pidfile) is True
    monkeypatch.setattr(cli, "APP_PID_FILE", pidfile)
    assert cli._console_open() is True                    # read at call time
    ancestors.add(4242)
    assert cli._console_open(pidfile) is False
    ancestors.clear()
    cmdline[4242] = "/x/.venv/bin/flubnf experiment start sihrs 2024-25"
    assert cli._console_open(pidfile) is False
    cmdline[4242] = '"C:\\x\\Scripts\\flubnf.exe" window'
    assert cli._console_open(pidfile) is True
    alive.clear()
    assert cli._console_open(pidfile) is False             # dead
    alive.add(os.getpid())
    cmdline[os.getpid()] = "flubnf app"
    pidfile.write_text(str(os.getpid()))
    assert cli._console_open(pidfile) is False             # this process
    # 4242 a console again: only the reading can say no
    alive.add(4242)
    cmdline[4242] = "/x/.venv/bin/flubnf app"
    pidfile.write_text(" 4242 \n", newline="\n")
    assert cli._console_open(pidfile) is True
    for garbled in ("", "app", "-1", "4242\n4243", "4242 4243", "4242x"):
        pidfile.write_text(garbled, newline="\n")
        assert cli._console_open(pidfile) is False, garbled
    pidfile.unlink()
    pidfile.mkdir()
    assert cli._console_open(pidfile) is False             # unreadable
