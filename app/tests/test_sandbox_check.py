"""The sandbox's Check: what can be known about a model without the
engine (app/core/sandbox.py check; POST /api/sandbox/models/<name>/check).
Fatal problems are only what makes a run fail; the rest are warnings.
BNG2.pl is faked; without Perl the network reads 'not checked'.
"""
import re
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
    unless the model says 'broken', after BioNetGen's banner either way."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = (cwd / "cm.bngl").read_text()
        if "broken" not in src:
            (cwd / "cm.net").write_text(NET)
        return types.SimpleNamespace(
            stdout="BioNetGen version 2.9.3\nABORT: Molecule Q not defined\n",
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
     "names kk__FREE, which model.bngl does not define, and k__FREE has no "
     "prior line"),
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


def test_dated_rows_point_to_the_upload(box):
    """Rows pasted from a dated file once read 'could not convert string
    to float': time in data.exp is weeks, and the upload reads dates."""
    files = _files()
    files["data.exp"] = "# time T_weekly\n2024-10-05 120\n2024-10-12 98\n"
    r = sb.check(files)
    assert ("data.exp holds dates (row '2024-10-05 120'): for dated rows "
            "use Load data, Upload a CSV") in r["problems"]
    assert not any("convert" in p for p in r["problems"])
    # a CSV pasted with its header, and a date written M/D/YYYY, too
    for text in ("week_ending,cases\n2024-10-05,120\n",
                 "# time T_weekly\n10/5/2024 120\n"):
        with pytest.raises(sb.SandboxError, match="^data.exp holds dates"):
            sb.read_exp(text)
    # numbers, negative or with exponents, are not dates
    assert sb.read_exp("# t y\n0 -1\n1 1e-05\n2 3.5\n")["rows"][1] == [1, 1e-05]


def test_a_spread_prior_is_not_a_range(box):
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "uniform_var = k__FREE 0.05 2.0", "normal_var = k__FREE 5.0 0.5")
    assert sb.check(files)["ok"]                      # mu 5 > sigma 0.5 is fine
    files["priors.conf"] = files["priors.conf"].replace("5.0 0.5", "5.0 0")
    assert any("spread" in p for p in sb.check(files)["problems"])


def test_warnings(box, tmp_path, monkeypatch):
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "pf_cumulative_observable = Tobs\n", "pf_shrink = 1\n")
    files["data.exp"] = "# time T_weekly\n0 5\n"
    r = sb.check(files)
    assert r["ok"], r["problems"]                        # warnings never block
    text = " ".join(r["warnings"])
    assert "no pf_cumulative_observable" in text
    assert "pf_shrink is not a setting the installed engine knows" in text   # the fake engine lists it not
    assert "one data row" in text


def test_a_row_at_or_before_the_start_time_is_named(box):
    files = _files()
    files["data.exp"] = "# time T_weekly\n-1 3\n0 5\n1 8\n"
    assert any("a row at t = -1, at or before the model's start time -1"
               in w for w in sb.check(files)["warnings"])
    files["data.exp"] = "# time T_weekly\n0 3\n1 5\n2 8\n"
    assert not any("start time" in w for w in sb.check(files)["warnings"])
    files["priors.conf"] += "pf_start_time = 0\n"
    assert any("a row at t = 0, at or before the model's start time 0"
               in w for w in sb.check(files)["warnings"])


def test_a_free_parameter_without_a_prior_is_a_problem(box):
    # the engine pairs __FREE names with prior lines both ways and refuses
    # a run that does not, so Check must not say "the model can run"
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace(
        "N            100000", "N            100000\nextra__FREE 1.0")
    r = sb.check(files)
    assert not r["ok"]
    assert any(p.startswith("extra__FREE ends in __FREE but has no prior line")
               for p in r["problems"]), r["problems"]


def test_a_half_written_prior_is_one_problem(box):
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "uniform_var = k__FREE 0.05 2.0", "uniform_var = k__FREE 0.05")
    probs = sb.check(files)["problems"]
    assert any("needs a parameter name and two numbers" in p for p in probs), probs
    assert not any("k__FREE ends in __FREE but has no prior" in p for p in probs), probs


def test_a_prior_on_a_fixed_parameter_is_named(box):
    # N is defined, yet only a __FREE parameter is fitted: a problem
    files = _files()
    files["priors.conf"] += "uniform_var = N 1000 200000\n"
    r = sb.check(files)
    assert not r["ok"]
    assert any(w.startswith("N has a prior line but its name does not end "
                            "in __FREE") for w in r["problems"]), r["problems"]


def test_parameters_read_continuations_and_whole_expressions():
    bngl = ("begin parameters\n"
            "N_y 120000\nN_o 80000\n"
            "N     N_y + N_o     # an expression with spaces\n"
            "r__FREE \\\n    8.0\n"
            "beta  Reff*gamma \\\n       / 1.2   # continued\n"
            "end parameters\n")
    assert sb.bngl_parameters(bngl) == ["N_y", "N_o", "N", "r__FREE", "beta"]
    vals = sb.bngl_parameter_values(bngl)
    assert vals["N"] == "N_y + N_o"
    assert vals["r__FREE"] == "8.0"                 # simulate_data's dispersion
    assert vals["beta"] == "Reff*gamma / 1.2"


def test_a_written_expression_is_not_read_as_its_first_number(box):
    # k__FREE 10 / 20 is 0.5, inside the prior 0.05 to 2: no warning
    files = _files()
    files["model.bngl"] = re.sub(r"(?m)^k__FREE\s+\S+", "k__FREE 10 / 20",
                                 files["model.bngl"])
    assert "k__FREE 10 / 20" in files["model.bngl"]
    assert not any("k__FREE is written as" in w
                   for w in sb.check(files)["warnings"])


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


def test_a_retired_key_says_so(box):
    files = _files()
    files["priors.conf"] += "pf_observable_mode = integrated\n"
    text = " ".join(sb.check(files)["warnings"])
    assert "pf_observable_mode is retired" in text
    assert "not a setting the installed engine knows" not in text


def test_a_model_without_begin_model_generates_its_network(box):
    """BNG itself accepts BNGL with no begin model / end model lines; the
    Check's network step must not report such a model as failing."""
    files = _files()
    files["model.bngl"] = (files["model.bngl"].replace("begin model\n", "")
                           .replace("end model\n", ""))
    assert "begin model" not in files["model.bngl"]
    r = sb.check(files)
    assert r["facts"]["network"] == "generates", r
    assert r["ok"] and r["problems"] == []


# ---------------------------------------------- the 2026-10-13 Sandbox audit

def test_a_commented_out_simulate_action_does_not_name_the_suffix(box):
    # BNG2.pl writes the live action's suffix; the run names the data file
    # after the one Check reports, so a comment above must not win
    files = _files()
    live = sb.simulate_suffix(files["model.bngl"])
    files["model.bngl"] = files["model.bngl"].replace(
        "simulate(", '# simulate({suffix=>"old"})\nsimulate(', 1)
    assert sb.simulate_suffix(files["model.bngl"]) == live != "old"
    assert sb.check(files)["facts"]["suffix"] == live
    only_comment = files["model.bngl"].replace(f'suffix=>"{live}"', "")
    with pytest.raises(sb.SandboxError, match="must name a suffix"):
        sb.simulate_suffix(only_comment)


@pytest.mark.parametrize("line, fix", [
    ("uniform_var k__FREE 0.05 2.0", "write it as 'uniform_var = k__FREE 0.05 2.0'"),
    ("k__FREE 0.05 2.0", "a prior reads 'uniform_var = name low high'"),
])
def test_a_prior_line_without_equals_is_refused_in_words(box, line, fix):
    # the engine reads 'key = value' only: refused by Check and by the run
    files = _files()
    files["priors.conf"] = files["priors.conf"].replace(
        "uniform_var = k__FREE 0.05 2.0", line)
    r = sb.check(files)
    assert not r["ok"]
    assert any("has no '='" in p and fix in p for p in r["problems"]), r["problems"]
    # the one problem, not one more per fitted parameter
    assert not any("has no prior line" in p for p in r["problems"]), r["problems"]
    with pytest.raises(sb.SandboxError, match="has no '='"):
        sb.split_priors(files["priors.conf"])


def test_generate_network_with_a_space_before_the_parenthesis_is_accepted(box):
    # BNG2.pl 2.9 runs 'generate_network ({overwrite=>1})' as written
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace(
        "generate_network(", "generate_network (")
    assert "generate_network (" in files["model.bngl"]
    assert not any("generate_network" in p for p in sb.check(files)["problems"])
    files["model.bngl"] = files["model.bngl"].replace(
        "generate_network (", "# generate_network (")
    assert any("generate_network" in p for p in sb.check(files)["problems"])


def test_a_header_mismatch_names_the_header(box):
    with pytest.raises(sb.SandboxError) as e:
        sb.read_exp("# simulated from the skeleton\n# time T_weekly\n0 3\n1 5\n")
    msg = str(e.value)
    assert "header line '# simulated from the skeleton'" in msg
    assert "'# time H_weekly'" in msg


def test_check_says_why_the_written_values_were_not_compared(box, monkeypatch):
    monkeypatch.setattr(pf_engine, "perl_available", lambda: True)
    from app.core import sandbox_check as sc

    def no_sim(*a, **k):
        raise sb.SandboxError("simulating needs whole-number times (weeks) "
                              "in data.exp and pf_start_time")
    monkeypatch.setattr(sc, "expected_counts", no_sim)
    facts = sb.check(_files())["facts"]
    assert facts["network"] == "generates"
    assert facts["at_start"].startswith("not compared: simulating needs "
                                        "whole-number times")


def test_check_names_what_this_computer_lacks_apart_from_the_model(box, monkeypatch):
    # the model is fine; the run would be refused here: Check says both
    monkeypatch.setattr(pf_engine, "PY310", Path(sys.executable))
    r = sb.check(_files())
    assert r["ok"] and r["facts"]["machine"] == ""
    monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    r = sb.check(_files())
    assert r["ok"]                                   # not a model problem
    assert r["facts"]["machine"] == "Perl was not found on PATH."
    assert "BNG2.pl" in r["facts"]["machine_tip"]
    assert r["facts"]["network"] == "not checked (no Perl here)"
    monkeypatch.setattr(pf_engine, "perl_available", lambda: True)
    monkeypatch.setattr(pf_engine, "PY310", Path("/nonexistent/bin/python"))
    assert sb.check(_files())["facts"]["machine"].startswith(
        "The engine's Python is missing")


def test_any_name_ending_in_free_is_fitted_once_both_files_use_it(box):
    files = {f: v.replace("k__FREE", "my_rate__FREE")
             for f, v in _files().items()}
    r = sb.check(files)
    assert r["ok"], r["problems"]
    assert "my_rate__FREE" in r["facts"]["free"]


def test_a_rename_in_the_model_only_is_one_problem(box):
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace("k__FREE", "my_rate__FREE")
    assert sb.check(files)["problems"] == [
        "priors.conf names k__FREE, which model.bngl does not define, and "
        "my_rate__FREE has no prior line: use one name in both files"]


def test_free_in_small_letters_is_named(box):
    files = {f: v.replace("k__FREE", "k__free") for f, v in _files().items()}
    probs = sb.check(files)["problems"]
    assert any("rename it k__FREE in both files" in p for p in probs), probs
    files = _files()
    files["model.bngl"] = files["model.bngl"].replace(
        "N            100000", "N            100000\nbeta__free 1.0")
    r = sb.check(files)
    assert r["ok"], r["problems"]
    assert ("beta__free is not fitted: only __FREE in capitals is, so "
            "rename it beta__FREE") in r["warnings"]
