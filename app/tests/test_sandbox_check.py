"""The sandbox's Check: what can be known about a model without the
engine (app/core/sandbox.py check; POST /api/sandbox/models/<name>/check).
Fatal problems are only what makes a run fail; the rest are warnings.
BNG2.pl is faked; without Perl the network reads 'not checked'.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf as pf_engine             # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)

NET = """begin parameters
    1 k 0.5
end parameters
begin species
    1 A() 100
    2 B() 0
    3 Tally() 0
end species
begin reactions
    1 1 2,3 k #_R1
end reactions
"""


@pytest.fixture
def box(sandbox_root, monkeypatch, tmp_path):
    """BNG2.pl present (a stub file) and faked: it writes the network
    unless the model says 'broken'."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = (cwd / "cm.bngl").read_text()
        if "broken" not in src:
            (cwd / "cm.net").write_text(NET)
        return types.SimpleNamespace(stdout="ABORT: Molecule Q not defined\n",
                                     stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return sandbox_root


def _files():
    return dict(sb.skeleton("mine"))


def test_the_skeleton_and_every_shipped_example_pass(box):
    r = sb.check(_files())
    assert r["ok"] and r["problems"] == [] and r["warnings"] == []
    f = r["facts"]
    assert f["suffix"] == "sim" and f["rows"] == sb.SKELETON_WEEKS
    assert f["free"] == ["k__FREE", "scale__FREE", "r__FREE"]
    assert f["cumulative"] == "Tobs" and f["network"] == "generates"
    assert (f["species"], f["reactions"]) == (3, 1)
    for e in sb.list_examples():
        files = {n: (sb.EXAMPLES / e / n).read_text() for n in sb.REQUIRED}
        r = sb.check(files)
        assert r["problems"] == [] and r["warnings"] == [], (e, r)


@pytest.mark.parametrize("edit, words", [
    (lambda f: f.update({"model.bngl": f["model.bngl"].replace('suffix=>"sim",', "")}),
     "must name a suffix"),
    (lambda f: f.update({"model.bngl": f["model.bngl"].replace(
        "generate_network({overwrite=>1})", "")}), "never call generate_network"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace("k__FREE", "kk__FREE")}),
     "names kk__FREE, which the parameters block does not define"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace("0.05 2.0", "2.0 0.05")}),
     "is not below the high end"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace(
        "loguniform_var = scale__FREE 0.05 1.0", "loguniform_var = scale__FREE 0 1.0")}),
     "the low end must be above 0"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace("= Tobs", "= Nope")}),
     "names Nope, which is neither an observable nor a function"),
    (lambda f: f.update({"data.exp": "# time y\n0 1\n1 2 3\n"}), "has 3 values"),
    (lambda f: f.update({"data.exp": "# time y\n0 1\n2 2\n1 3\n"}), "time must increase"),
    (lambda f: f.update({"data.exp": "# time y\n0 1\n1 x\n"}), "not a number"),
    (lambda f: f.update({"priors.conf": "pf_cumulative_observable = Tobs\n"}),
     "declares no free parameter"),
    (lambda f: f.update({"priors.conf": f["priors.conf"] + "pf_seed = 4\n"}),
     "sets pf_seed"),
    (lambda f: f.update({"model.bngl": "# broken\n" + f["model.bngl"]}),
     "ABORT: Molecule Q not defined"),
])
def test_each_problem_is_named(box, edit, words):
    files = _files()
    edit(files)
    r = sb.check(files)
    assert not r["ok"]
    assert any(words in p for p in r["problems"]), r["problems"]


def test_a_spread_prior_is_not_a_range(box):
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "uniform_var = k__FREE 0.05 2.0", "normal_var = k__FREE 5.0 0.5")
    assert sb.check(files)["ok"]                      # mu 5 > sigma 0.5 is fine
    files["priors.conf"] = files["priors.conf"].replace("5.0 0.5", "5.0 0")
    assert any("spread" in p for p in sb.check(files)["problems"])


def test_warnings(box, tmp_path, monkeypatch):
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace(
        "N            100000", "N            100000\nextra__FREE 1.0")
    files["priors.conf"] = files["priors.conf"].replace(
        "pf_cumulative_observable = Tobs\n", "pf_shrink = 1\n")
    files["data.exp"] = "# time T_weekly\n0 5\n"
    r = sb.check(files)
    assert r["ok"]                                       # warnings never block
    text = " ".join(r["warnings"])
    assert "extra__FREE ends in __FREE but has no prior" in text
    assert "no pf_cumulative_observable" in text
    assert "does not accept pf_shrink" in text           # the fake engine lists it not
    assert "one data row" in text


def test_without_perl_the_network_is_not_checked(box, monkeypatch):
    monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    r = sb.check(_files())
    assert r["ok"] and r["facts"]["network"].startswith("not checked")


def test_the_route_checks_the_posted_text_not_the_saved_file(box):
    sb.new_model("mine")
    files = sb.read_model("mine")
    r = client.post("/api/sandbox/models/mine/check",
                    data={"model_bngl": files["model.bngl"],
                          "priors_conf": files["priors.conf"].replace("= Tobs", "= Nope"),
                          "data_exp": files["data.exp"]}).json()
    assert not r["ok"] and "Nope" in " ".join(r["problems"])
    assert client.post("/api/sandbox/models/mine/check").json()["ok"]   # the saved file
    r = client.post("/api/sandbox/models/nobody/check").json()
    assert not r["ok"] and r["problems"]
    # the check works in its own scratch folder, never the diagram's
    assert not (box / "contactmap").exists()
