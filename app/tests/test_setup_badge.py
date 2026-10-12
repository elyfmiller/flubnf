"""Home's Setup badge counts what the version probe reads as "not
installed" as well as what settings.check() reports missing, each
component once, so it never says "All components installed" beside a
"not installed" value."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

import flubnf.settings as fs                        # noqa: E402
from app.ui import versions as V                    # noqa: E402
from app.ui.routes import home as H                 # noqa: E402
from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)


def test_setup_gaps_union_each_component_once():
    missing = [("FLUBNF_BNG", "/x", "BioNetGen"), ("perl", "perl", "Perl")]
    vers = {"pybnf": "not installed", "bngsim": "0.15.1",
            "bionetgen": "not installed", "perl": "not installed",
            "fastapi": "0.1", "plotly": "resolving…"}
    assert H._setup_gaps(missing, vers) == ["BioNetGen", "Perl", "PyBNF"]
    # a known engine build names PyBNF by its build, not its probe
    assert H._setup_gaps(missing, vers, engine_known=True) == ["BioNetGen", "Perl"]
    assert H._setup_gaps([], {"bngsim": "0.15.1"}) == []


def test_home_badge_never_says_all_installed_beside_not_installed(monkeypatch):
    monkeypatch.setattr(fs, "check", lambda verbose=True: [])
    monkeypatch.setattr(H, "_engine_known", lambda: False)
    for k in ("bngsim", "bionetgen", "perl", "fastapi", "plotly"):
        monkeypatch.setitem(V.VERSIONS, k, "1.0")
    monkeypatch.setitem(V.VERSIONS, "pybnf", "not installed")
    html = client.get("/").text
    assert ">All components installed<" not in html
    assert ">1 not installed<" in html and 'id="hm-missing"' in html
    monkeypatch.setitem(V.VERSIONS, "pybnf", "1.0")
    html = client.get("/").text
    assert ">All components installed<" in html
