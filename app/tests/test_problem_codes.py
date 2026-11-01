"""The problem codes (app/core/problem_codes.py): append-only, one tier
each, every code the code says registered, and Check's "codes" in step
with its strings.

golden/problem_codes.json holds {code: tier}. It may only grow: a code is
never renamed, reused or moved to another tier. A new code goes into
CODES and into the golden file together.
"""
import json
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import problem_codes as PC                 # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf as pf_engine             # noqa: E402
from app.ui import server as srv                         # noqa: E402

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "golden" / "problem_codes.json"

client = TestClient(srv.app)


def test_the_golden_codes_only_grow_and_keep_their_tiers():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gone = sorted(c for c in golden if c not in PC.CODES)
    assert not gone, f"codes are never removed or renamed: {gone}"
    moved = sorted(c for c, t in golden.items() if PC.CODES[c][0] != t)
    assert not moved, f"a code never changes tier: {moved}"
    new = sorted(c for c in PC.CODES if c not in golden)
    assert not new, (f"new codes {new}: add each to {GOLDEN.name} with its "
                     "tier, in the same change")


def test_each_code_has_one_tier_and_a_meaning():
    for code, (tier, meaning) in PC.CODES.items():
        assert re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*", code), code
        assert tier in PC.TIERS, code
        assert meaning.strip(), code
        assert "posterior" not in meaning.lower(), code


def test_a_finding_takes_its_tier_from_the_code():
    assert PC.finding("NO_SUFFIX", "words") == {
        "code": "NO_SUFFIX", "tier": "problem", "text": "words"}
    assert PC.finding("KEY_NOT_ALLOWED", "w", file="priors.conf",
                      line=3) == {"code": "KEY_NOT_ALLOWED", "tier": "problem",
                                  "text": "w", "file": "priors.conf",
                                  "line": 3}
    assert PC.finding("MACHINE", "no Perl")["tier"] == "machine"
    with pytest.raises(ValueError, match="not a problem code"):
        PC.finding("NO_SUCH_CODE", "words")


def test_a_refusal_carries_its_findings():
    found = [PC.finding("GAMMA_ASSUMED", "a warning"),
             PC.finding("NO_H_WEEKLY", "first problem"),
             PC.finding("NO_DISPERSION", "second problem")]
    e = PC.Refusal(found)
    assert isinstance(e, ValueError)
    assert e.code == "NO_H_WEEKLY" and e.findings == found
    assert str(e) == "first problem\nsecond problem"
    one = PC.Refusal(PC.finding("MODEL_REF", "not a reference"))
    assert one.code == "MODEL_REF" and str(one) == "not a reference"


#: a code where the code base says one: finding("X", ...), Check's
#: problem("X", ...) and warning("X", ...), and SandboxError(..., code="X")
_SAID = re.compile(r'\b(?:finding|problem|warning)\(\s*"([A-Z][A-Z0-9_]*)"'
                   r'|\bcode="([A-Z][A-Z0-9_]*)"')


def test_every_code_the_code_base_says_is_registered():
    said = {}
    for folder in ("app/core", "app/ui"):
        for p in (REPO / folder).rglob("*.py"):
            for m in _SAID.finditer(p.read_text(encoding="utf-8")):
                said.setdefault(m.group(1) or m.group(2), p.name)
    unknown = {c: f for c, f in said.items() if c not in PC.CODES}
    assert not unknown, f"codes said but not in CODES: {unknown}"
    # the scan reads what it should: Check's, the library's, the route's
    assert {"NO_SUFFIX", "PRIOR_BOUNDS", "MACHINE", "CHECK_FAILED",
            "KEY_NOT_ALLOWED", "SEASON_NO_WEEKS"} <= set(said)


# ------------------------------------------------- Check's codes, in step

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
    """BNG2.pl present and faked, as test_sandbox_check.py's box."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = cwd / "cm.bngl"            # not the console's own probes
        if src.is_file() and "broken" not in src.read_text():
            (cwd / "cm.net").write_text(NET)
        return types.SimpleNamespace(
            stdout="BioNetGen version 2.9.3\nABORT: Molecule Q not defined\n",
            stderr="", returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return sandbox_root


def _mirrors(r: dict) -> list:
    """r's codes, after checking they mirror its strings in order."""
    texts = r["problems"] + r["warnings"] + (
        [r["facts"]["machine"]] if r["facts"]["machine"] else [])
    assert [f["text"] for f in r["codes"]] == texts
    tiers = (["problem"] * len(r["problems"])
             + ["warning"] * len(r["warnings"])
             + ["machine"] * bool(r["facts"]["machine"]))
    assert [f["tier"] for f in r["codes"]] == tiers
    return [f["code"] for f in r["codes"]]


def test_check_codes_mirror_its_strings_for_a_clean_model(box):
    r = sb.check(dict(sb.skeleton("mine")))
    assert r["ok"] and _mirrors(r) == []


def test_check_codes_mirror_its_strings_for_a_broken_one(box, monkeypatch):
    files = dict(sb.skeleton("mine"))
    files["model.bngl"] = (files["model.bngl"]
                           .replace('suffix=>"sim",', "")
                           .replace("N            100000",
                                    "N            100000\nlow__free 2"))
    files["priors.conf"] = (files["priors.conf"]
                            .replace("0.05 2.0", "2.0 0.05")
                            .replace("k__FREE", "kk__FREE")
                            .replace("pf_cumulative_observable = Tobs\n",
                                     "pf_observable_mode = integrated\n"))
    files["data.exp"] = "# time T_weekly\n-1 3\n1 5\n0 8\n"
    monkeypatch.setattr(pf_engine, "perl_available", lambda: False)
    r = sb.check(files)
    # PRIOR_UNDEFINED went with its string when the rename was named
    assert _mirrors(r) == [
        "NO_SUFFIX", "EXP_TIME_ORDER", "PRIOR_BOUNDS", "PRIOR_RENAMED",
        "FREE_LOWERCASE", "NO_CUMULATIVE", "ROW_BEFORE_START",
        "KEY_RETIRED", "MACHINE"]


@pytest.mark.parametrize("edit, code", [
    (lambda f: f.update({"data.exp": "# time y\n0 1\n1 x\n"}), "EXP_UNREADABLE"),
    (lambda f: f.update({"priors.conf": "uniform_var k__FREE 0.05 2.0\n"}),
     "PRIORS_LINE"),
    (lambda f: f.update({"priors.conf": f["priors.conf"] + "pf_seed = 4\n"}),
     "KEY_RESERVED"),
    (lambda f: f.update({"priors.conf": "pf_cumulative_observable = Tobs\n"}),
     "NO_FREE_PARAMETER"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace(
        "uniform_var = k__FREE 0.05 2.0", "uniform_var = k__FREE 0.05")}),
     "PRIOR_MALFORMED"),
    (lambda f: f.update({"priors.conf": f["priors.conf"]
                         + "uniform_var = N 1000 200000\n"}), "PRIOR_NOT_FREE"),
    (lambda f: f.update({"priors.conf": f["priors.conf"]
                         + "uniform_var = gone__FREE 1 2\n"}), "PRIOR_UNDEFINED"),
    (lambda f: f.update({"model.bngl": f["model.bngl"].replace(
        "N            100000", "N            100000\nextra__FREE 1.0")}),
     "FREE_NO_PRIOR"),
    (lambda f: f.update({"priors.conf": f["priors.conf"].replace(
        "= Tobs", "= Nope")}), "CUMULATIVE_NOT_OUTPUT"),
    (lambda f: f.update({"model.bngl": f["model.bngl"].replace(
        "generate_network({overwrite=>1})", "")}), "NO_GENERATE_NETWORK"),
    (lambda f: f.update({"model.bngl": "# broken\n" + f["model.bngl"]}),
     "NETWORK_FAILS"),
    (lambda f: f.update({"model.bngl": f["model.bngl"].replace(
        "k__FREE      0.5", "k__FREE      9")}), "START_OUTSIDE_PRIOR"),
])
def test_each_check_problem_has_its_code(box, edit, code):
    files = dict(sb.skeleton("mine"))
    edit(files)
    assert code in _mirrors(sb.check(files))


def test_the_check_route_says_check_failed_when_check_itself_fails(box):
    r = client.post("/api/sandbox/models/nobody/check").json()
    assert not r["ok"] and r["codes"] == [
        {"code": "CHECK_FAILED", "tier": "problem", "text": r["problems"][0]}]
