"""A missing hub clone, the Setup card and the component versions (bug
hunt 2026-10-25, G17).

  * No hub folder: Data and Forecast say so and name the setup step that
    fetches it; a run is refused before it starts; the Data tab's check
    reads "missing", not "offline" with a Python error.
  * The Setup card's action lines start with the most basic piece (the
    FluSight data and BioNetGen, through setup.sh), the engine's parts
    are one component in the badge, the rows and the versions, and the
    bngsim pin note stays off beside "not installed".
  * A cold launch paints "checking…" until the version probe lands; the
    badge then names what is missing.
  * Perl shows its version, on Home and on Methods.
  * Right after Update data the hub badge reads "up to date", once.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import flubnf.settings as fs                          # noqa: E402
from app.core import data as data_mod                 # noqa: E402
from app.ui import server as srv                      # noqa: E402
from app.ui import state as ui_state                  # noqa: E402
from app.ui import templating                         # noqa: E402
from app.ui import versions as V                      # noqa: E402
from app.ui.routes import data as D                   # noqa: E402
from app.ui.routes import home as H                   # noqa: E402

client = TestClient(srv.app)
ENGINE = "Particle-filter engine"


@pytest.fixture()
def nohub(tmp_path, monkeypatch, hub_check_real):
    """A hub path that does not exist, as FLUBNF_HUB can name (the real
    test of its presence, which the suite otherwise fakes)."""
    gone = tmp_path / "nohub"
    monkeypatch.setattr(data_mod, "HUB", gone)
    monkeypatch.setattr(D, "_pulled", {})
    monkeypatch.setattr(templating, "_platform", lambda: "linux")
    for k in ("flash", "flash_kind", "flash_detail", "running"):
        ui_state._status[k] = None
    return gone


# ------------------------------------------- WI-08 and DA-06: no hub folder

def test_the_hubs_absence_is_one_tested_state(nohub):
    assert data_mod.hub_missing() == f"there is no hub folder at {nohub}"
    nohub.mkdir()
    assert data_mod.hub_missing(data=False) == ""
    assert data_mod.hub_missing() == f"the hub folder {nohub} is empty"
    (nohub / "auxiliary-data").mkdir()
    assert data_mod.hub_missing() == ""


def test_data_says_the_clone_is_missing_and_what_fetches_it(nohub):
    html = client.get("/data").text
    line = html.split('id="hub-missing"', 1)[1].split("</div>", 1)[0]
    assert f"No FluSight data: there is no hub folder at {nohub}. To fetch " \
        "it, run <code>./setup.sh</code> and relaunch the console." in line
    assert "Update data downloads it" not in html
    pill = html.split('id="hub-pill"', 1)[1].split("</span></span>", 1)[0]
    assert 'data-state="error"' in pill and pill.endswith(
        '<span class="uk-badge-t">missing')
    # the check says the same, as words, not a Python error
    r = client.post("/freshness", headers={"Accept": "application/json"})
    assert r.json()["pill"] == "bad" and r.json()["words"] == "missing"
    assert r.json()["detail"] == f"no hub clone: there is no hub folder at {nohub}"
    assert "Errno" not in r.text and "PosixPath" not in r.text
    # Update data cannot clone one: refused with the step that does
    r = client.post("/data/pull", headers={"Accept": "application/json"})
    assert r.json()["ok"] is False
    assert r.json()["message"] == (
        f"Could not update the hub clone: there is no hub folder at {nohub}. "
        "To fetch it, run ./setup.sh and relaunch the console.")


def test_with_no_hub_data_the_comparators_row_does_not_offer_update_data(nohub):
    # no folder: Update data is refused, so the row's hint would send the
    # user to a button that cannot help; the alert above names the step
    html = client.get("/data").text
    assert 'id="hub-missing"' in html and 'id="comp-missing"' in html
    assert "Update data adds them" not in html
    # a clone without its data directories: the alert says the same
    nohub.mkdir()
    html = client.get("/data").text
    assert 'id="hub-missing"' in html and 'id="comp-missing"' in html
    assert "Update data adds them" not in html
    # the clone's data there, its comparators not: Update data adds them
    (nohub / "auxiliary-data").mkdir()
    html = client.get("/data").text
    assert 'id="hub-missing"' not in html
    assert ("baseline, ensemble missing</span></span> "
            '<span class="hint">Update data adds them.</span>') in html


def test_forecast_says_the_clone_is_missing_and_refuses_a_run(nohub):
    html = client.get("/forecast").text
    alert = html.split('id="fc-hub-missing"', 1)[1].split("</div>", 1)[0]
    assert f"No FluSight data: there is no hub folder at {nohub}. To fetch " \
        "it, run <code>./setup.sh</code> and relaunch the console." in alert
    r = client.post("/run", data={"forecast_date": "2026-04-25",
                                  "locations": ["Arizona"],
                                  "engine": "analogue"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert ui_state._status.get("flash") == \
        f"Not run: no FluSight data (there is no hub folder at {nohub})."
    assert ui_state._status.get("flash_detail") == \
        "To fetch it, run ./setup.sh and relaunch the console."
    assert not ui_state._status.get("running")


# --------------------------------------------- HM-08 and HM-11: the Setup card

def _home(missing, versions, engine_build=None, platform="linux"):
    """Home under this check, these versions and this engine build:
    unknown unless given, never the build this machine's own engine
    snapshot holds (the badge, the build line and the versions row all
    read it)."""
    # the startup warm pass fills VERSIONS and ENGINE_BUILD in place: it
    # finishes first, or it may overwrite what the page is given here
    assert ui_state._WARM_DONE.wait(60)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fs, "check", lambda verbose=True: missing)
        mp.setattr(V, "ENGINE_BUILD", dict(engine_build or {}))
        mp.setattr(templating, "_platform", lambda: platform)
        for k, v in versions.items():
            mp.setitem(V.VERSIONS, k, v)
        return client.get("/").text


INSTALLED = {"pybnf": "1.0", "bngsim": "0.15.1", "bionetgen": "2.9",
             "perl": "5.38", "fastapi": "0.1", "plotly": "7.0"}
#: the private engine's production build, as its checkout reads to git
KNOWN_BUILD = {"branch": "feature/particle-filter", "commit": "2fdadee0",
               "dirty": False, "source": "git", "path": "/p"}
HUB_GONE = ("FLUBNF_HUB", "/x/auxiliary-data",
            "FluSight hub clone (truth vintages, locations)")
BNG_GONE = ("FLUBNF_BNG", "/x/BNG2.pl", "BioNetGen BNG2.pl (network generation)")
ENGINE_GONE = [("FLUBNF_PY_ENGINE", "/v/bin/python",
                "engine venv python (pybnf + bngsim)"),
               ("FLUBNF_PYBNF", "/p/pybnf/pf.py", "PyBNF fork with fit_type=pf")]


def test_a_missing_hub_gets_its_action_line_first():
    html = _home([HUB_GONE], INSTALLED)
    fix = html.split('id="hm-fix-data"', 1)[1].split("</div>", 1)[0]
    assert "To add the FluSight data, run <code>./setup.sh</code> and " \
        "relaunch the console." in fix
    assert 'id="hm-fix"' not in html                # no engine line
    # with the engine missing too, the data line comes first
    html = _home([HUB_GONE, BNG_GONE] + ENGINE_GONE,
                 dict(INSTALLED, pybnf="not installed", bngsim="not installed",
                      bionetgen="not installed"))
    assert "To add the FluSight data and BioNetGen, run <code>./setup.sh" in html
    assert html.index('id="hm-fix-data"') < html.index('id="hm-fix"')
    # Windows names its own setup
    html = _home([HUB_GONE], INSTALLED, platform="win32")
    assert "run <code>setup.ps1</code> and open FluBNF.bat again" in html


def test_the_engines_parts_are_one_component_in_the_badge_rows_and_versions():
    html = _home(ENGINE_GONE,
                 dict(INSTALLED, pybnf="not installed", bngsim="not installed"))
    # the badge counts; the row below names it, so the badge has no "?"
    assert ">1 not installed<" in html and 'id="tip-hm-missing"' not in html
    rows = html.split('class="hm-missing"', 1)[1].split("</ul>", 1)[0]
    assert rows.count("<li>") == 1 and f"<span>{ENGINE}</span>" in rows
    assert "fit_type=pf" not in rows and "venv" not in rows
    assert "(FLUBNF_PY_ENGINE) and <span class=\"hm-mono\">/p/pybnf/pf.py" in rows
    assert 'id="hm-v-engine"' in html and 'id="hm-v-pybnf"' not in html
    assert "<dt>PyBNF</dt>" not in html and "<dt>bngsim</dt>" not in html
    assert H._setup_gaps(ENGINE_GONE, {"pybnf": "not installed",
                                       "bngsim": "not installed"}) == [ENGINE]
    # installed: PyBNF and bngsim read their versions, as before
    html = _home([], INSTALLED)
    assert 'id="hm-v-pybnf"' in html and 'id="home-pin"' in html
    assert 'id="hm-v-engine"' not in html


def test_a_known_build_without_its_python_is_one_engine_entry():
    """The fork checkout is there (its build is known) but the engine's own
    Python is not: the versions row names the engine once, as with no
    engine at all, never "PyBNF <build>" beside "bngsim not installed"."""
    venv_gone = [ENGINE_GONE[0]]
    html = _home(venv_gone, dict(INSTALLED, pybnf="not installed",
                                 bngsim="not installed"),
                 engine_build=KNOWN_BUILD)
    assert ">1 not installed<" in html
    row = html.split('aria-label="Component versions"', 1)[1].split("</dl>", 1)[0]
    assert 'id="hm-v-engine"' in row and f"<dt>{ENGINE}</dt>" in row
    assert '<span data-vkey="pybnf">not installed</span>' in row
    assert 'id="hm-v-pybnf"' not in row and 'id="home-pin"' not in row
    assert "<dt>PyBNF</dt>" not in row and "<dt>bngsim</dt>" not in row
    assert row.count("not installed") == 1
    # still resolving: the one entry waits, as the badge does
    html = _home(venv_gone, dict(INSTALLED, pybnf=V.VERSION_PENDING,
                                 bngsim=V.VERSION_PENDING),
                 engine_build=KNOWN_BUILD)
    assert 'id="hm-v-engine"' in html and 'id="home-pin"' not in html
    # the Python there too: PyBNF names the build, bngsim its version
    html = _home([], INSTALLED, engine_build=KNOWN_BUILD)
    row = html.split('aria-label="Component versions"', 1)[1].split("</dl>", 1)[0]
    assert 'id="hm-v-pybnf"' in row and 'id="home-pin"' in row
    assert "<span data-engine-label>2fdadee0 (feature/particle-filter)" in row
    assert 'id="hm-v-engine"' not in row and "not installed" not in row


def test_a_machine_without_the_engine_says_so_once_in_setup():
    """No engine (a student laptop): the Setup card names it once, with
    its fix and one "?" (where it was looked for); the build line that
    would repeat it is not shown."""
    from test_fewer_marks import marks
    html = _home(ENGINE_GONE,
                 dict(INSTALLED, pybnf="not installed", bngsim="not installed"),
                 engine_build={"engine": "public",
                               "error": "there is no Python at /v/bin/python"})
    setup = html.split('class="card hm-setup"', 1)[1]
    assert setup.count("To add the particle-filter engine") == 1
    assert "data-engine-build" not in setup
    assert [m for m in marks(html) if m.startswith("tip-")] == ["tip-hm-miss-1"]


def test_the_bngsim_pin_note_stays_off_beside_not_installed():
    html = _home([], dict(INSTALLED, bngsim="not installed"))
    assert 'id="tip-home-pin"' not in html


# ------------------------------------------ HM-13: a cold launch's badge

def test_a_cold_launch_says_checking_until_the_probe_lands():
    html = _home([], dict(INSTALLED, pybnf=V.VERSION_PENDING,
                          bngsim=V.VERSION_PENDING))
    assert 'id="hm-checking"' in html and ">checking…<" in html
    assert 'id="hm-installed"' not in html and 'id="hm-missing"' not in html
    assert 'id="hm-setup-state"' in html
    # the recount waits for every value and draws the badge (the list and
    # the values name what it counts, so it has no "?")
    script = html.split("function recount()", 1)[1].split("</script>", 1)[0]
    assert "indexOf('resolving') >= 0) return" in script
    assert "slot.innerHTML = FluBNFUI.badge('warn', word);" in script
    assert "FluBNFUI.tip(" not in script
    assert "FluBNFUI.badge('ok', 'All components installed')" in script


# ----------------------------------------- HM-14 and ME-19: Perl's version

def test_perl_shows_its_version_not_its_path(monkeypatch):
    import subprocess

    class R:
        returncode, stdout = 0, "v5.38.2\n"
    monkeypatch.setattr(fs, "resolve_perl", lambda: "/usr/bin/perl")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert V._component_versions()["perl"] == "5.38.2"
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(V.VERSIONS, "perl", "5.38.2")
        home = client.get("/").text
        methods = client.get("/methods").text
    assert '<span data-vkey="perl">5.38.2</span>' in home
    assert '<span data-vkey="perl">5.38.2</span>' in methods
    assert "/usr/bin/perl" not in home and "/usr/bin/perl" not in methods


# ------------------------------------- DA-22: the badge after Update data

def test_right_after_update_data_the_clone_reads_up_to_date(monkeypatch):
    monkeypatch.setattr(data_mod, "pull_hub", lambda: (True, "pulled"))
    monkeypatch.setattr(data_mod, "newest_week", lambda: "2026-10-17")
    monkeypatch.setattr(D, "_live_values", lambda: None)
    D._pulled.clear()
    r = client.post("/data/pull", headers={"Accept": "application/json"})
    assert r.json()["ok"] is True
    after = client.get("/data").text
    pill = after.split('id="hub-pill"', 1)[1].split("</span></span>", 1)[0]
    assert 'data-state="ok"' in pill and pill.endswith(
        '<span class="uk-badge-t">up to date')
    assert "up to date with origin" in after
    # one-shot: a later visit has not checked, so it does not claim it
    assert '<span class="uk-badge-t">not checked' in client.get("/data").text

