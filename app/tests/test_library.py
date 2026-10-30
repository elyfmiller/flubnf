"""The model library (app/core/library.py): the replay normal form and the
fingerprint, the shipped models' pins, register, resolve and validate.

BNG2.pl is faked (the sandbox_root fixture and a stub BNG2.pl, as
test_sandbox_check.py's box), so Check's network step reads "generates"
for any model without the word 'broken'.
"""
import errno
import hashlib
import json
import os
import re
import sys
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf as PF                    # noqa: E402
from app.core.problem_codes import Refusal, finding      # noqa: E402

#: measured on dev at 0e9e90b and again at 53f1acf
SIHRS_FP = "5edca88e28ad6dbdeb97bf1aafd4f236bb89ee0b58dbb45e09c2f9179003fb7b"
SIHRS_FILES = {
    "model.bngl": "083c1a643a56c597bb1206a23955233a5105a49b8d77472c5ec26b183ded0ba1",
    "priors.conf": "426e6214c3333aafd47d6653c52cef2811b85645c2877ad3bf838e016f539e8d"}
SHIPPED_FPS = {
    "sihrs": SIHRS_FP,
    "sihrs-2strain": "c0c1ec978fd96af1fb828cf7e8ba21ddf1ecde0d3cf79a39660748ee5aaafca5",
    "sihrs-natg": "cfc22b4e6e4ca12efcf2763c873a85fd14b28dc8d1679b7b4c3266e3fbcfaf5f"}


@pytest.fixture
def box(sandbox_root, monkeypatch, tmp_path):
    """BNG2.pl present (a stub file) and faked: it writes a network unless
    the model says 'broken'."""
    bng = tmp_path / "BNG2.pl"
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))

    def fake_bng(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        src = cwd / "cm.bngl"            # not the console's own probes
        if src.is_file() and "broken" not in src.read_text():
            (cwd / "cm.net").write_text("begin species\n 1 S() 1\nend species\n")
        return types.SimpleNamespace(
            stdout="BioNetGen version 2.9.3\nABORT: bad rule\n", stderr="",
            returncode=0)
    monkeypatch.setattr(cm.subprocess, "run", fake_bng)
    return sandbox_root


def _good() -> dict:
    """A model ready for replays: the shipped SIHRS as a student starts it."""
    return L.shipped_files("sihrs")


def _sandbox_model(name: str, files: dict, info: dict | None = None) -> Path:
    d = sb.MODELS / name
    d.mkdir(parents=True, exist_ok=True)
    for f, t in {**files, "data.exp": L.SAMPLE_EXP}.items():
        (d / f).write_bytes(t if isinstance(t, bytes) else t.encode("utf-8"))
    if info is not None:
        (d / "model.json").write_text(json.dumps(info), encoding="utf-8")
    return d


def _fp(files: dict) -> str:
    return L.fingerprint(L.file_hashes(files))


def _codes(found: list) -> list:
    return [f["code"] for f in found]


def _refused(code: str, fn, *a):
    with pytest.raises(Refusal) as e:
        fn(*a)
    assert e.value.code == code, e.value.findings
    return str(e.value)


# ------------------------------------------- normal form and fingerprint


def test_newlines_a_bom_and_outer_whitespace_leave_the_fingerprint():
    files = _good()
    for edit in (lambda t: t.replace("\n", "\r\n"),
                 lambda t: t.replace("\n", "\r"),
                 lambda t: "\ufeff" + t,
                 lambda t: "\n\n  " + t + "\n\n\t \n"):
        assert _fp({f: edit(t) for f, t in files.items()}) == _fp(files)


def test_a_comment_edit_changes_it_and_an_actions_edit_does_not():
    files = _good()
    commented = dict(files, **{"model.bngl": files["model.bngl"].replace(
        "# census -- do NOT fit", "# census, never fit")})
    assert _fp(commented) != _fp(files)
    acted = dict(files, **{"model.bngl": files["model.bngl"].replace(
        "t_end=>48,n_steps=>48", "t_end=>10,n_steps=>10") + "# more\n"})
    assert _fp(acted) == _fp(files)
    assert _fp(dict(files, **{"priors.conf": files["priors.conf"]
                              + "# a note\n"})) != _fp(files)


def test_data_exp_and_model_json_are_outside_it():
    files = _good()
    more = dict(files, **{"data.exp": "# time H_weekly\n1 5\n",
                          "model.json": "{}"})
    assert L.file_hashes(more) == L.file_hashes(files)
    assert set(L.file_hashes(files)) == set(L.REPLAY_FILES)


def test_replay_text_is_idempotent():
    for f, t in _good().items():
        once = L.replay_text(f, t)
        assert L.replay_text(f, once) == once


def test_the_join_after_end_model_is_one_blank_line():
    want = "begin model\nend model\n\n" + L.REPLAY_ACTIONS + "\n"
    for tail in ("", "\n", "\n\n\n", "\n\n# old actions\nbegin actions\n"
                 "simulate({suffix=>\"x\"})\nend actions\n"):
        assert L.replay_text("model.bngl", "begin model\nend model" + tail) == want
    with pytest.raises(Refusal) as e:
        L.replay_text("model.bngl", "begin parameters\nend parameters\n")
    assert e.value.code == "NO_MODEL_BLOCK"


# ------------------------------------------------------------------ pins


def _independent(tmpl: Path, start: str, priors: str) -> dict:
    """The shipped composition hashed by the standard library alone: the
    template with its starting values, cut after end model, FluBNF's
    actions after one blank line, one final newline."""
    text = tmpl.read_text(encoding="utf-8").replace("begin parameters\n",
                                                    start, 1)
    cut = text.index("\nend model\n") + len("\nend model")
    files = {"model.bngl": text[:cut] + "\n\nbegin actions\n"
             "generate_network({overwrite=>1})\n"
             'simulate({suffix=>"SIHRS_flu",method=>"ode",t_start=>0,'
             't_end=>48,n_steps=>48,print_functions=>1})\nend actions\n',
             "priors.conf": priors + "pf_cumulative_observable = Hobs\n"}
    hashes = {f: hashlib.sha256(t.encode("utf-8")).hexdigest()
              for f, t in files.items()}
    canon = json.dumps(hashes, sort_keys=True, separators=(",", ":"))
    return {"files": hashes,
            "fingerprint": hashlib.sha256(canon.encode("utf-8")).hexdigest()}


def test_the_shipped_fingerprints_are_pinned():
    changed = ("the shipped model's files changed (a template, its starting "
               "values or its priors in app/core/engines/pf.py): every "
               "experiment of it gets a new fingerprint, so update this pin "
               "on purpose")
    ind = _independent(PF.TEMPLATE, PF.DEFAULTS_BLOCK, PF.VARS_1S)
    assert ind == {"files": SIHRS_FILES, "fingerprint": SIHRS_FP}, changed
    assert L.file_hashes(L.shipped_files("sihrs")) == SIHRS_FILES, changed
    for n, (tmpl, start, priors) in {
            "sihrs-2strain": (PF.TEMPLATE_2S, PF.DEFAULTS_2S, PF.VARS_2S),
            "sihrs-natg": (PF.TEMPLATE_NATG, PF.DEFAULTS_BLOCK, PF.VARS_1S)
            }.items():
        assert _independent(tmpl, start, priors)["fingerprint"] == SHIPPED_FPS[n], changed
    for n, fp in SHIPPED_FPS.items():
        assert _fp(L.shipped_files(n)) == fp, changed
        assert L.resolve(n)["fingerprint"] == fp, changed


# --------------------------------------------------------------- register


def test_register_writes_a_version_once_and_the_next_on_an_edit(box):
    src = _sandbox_model("beta", _good())
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    r = L.register("beta")
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before
    assert (r["ref"], r["version"], r["new"]) == ("beta@1", 1, True)
    assert r["fingerprint"] == SIHRS_FP
    assert not [f for f in r["findings"] if f["tier"] == "problem"]
    again = L.register("beta")
    assert (again["version"], again["new"]) == (1, False)
    # data.exp and the Sandbox model.json are not the model
    before["data.exp"] = b"# time H_weekly\n3 9\n"
    (src / "data.exp").write_bytes(before["data.exp"])
    assert L.register("beta")["new"] is False
    with open(src / "model.bngl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write("# a second thought\n")      # after the actions: dropped
    assert L.register("beta")["version"] == 1
    (src / "model.bngl").write_bytes(before["model.bngl"].replace(
        b"# FluBNF SIHRS", b"# My SIHRS"))
    r2 = L.register("beta")
    assert (r2["ref"], r2["new"]) == ("beta@2", True)
    assert r2["fingerprint"] != SIHRS_FP
    (src / "model.bngl").write_bytes(before["model.bngl"])
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before


def test_a_version_folder_holds_three_files_and_shasum_checks_them(box):
    _sandbox_model("beta", _good())
    L.register("beta")
    d = L.root() / "beta" / "1"
    assert sorted(p.name for p in d.iterdir()) == ["model.bngl", "model.json",
                                                    "priors.conf"]
    raw = (d / "model.json").read_bytes()
    m = json.loads(raw)
    assert set(m) == {"format_version", "fingerprint", "files",
                      "registered_utc"}                # no origin: none given
    assert m["format_version"] == 1 and m["fingerprint"] == SIHRS_FP
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", m["registered_utc"])
    for f in L.REPLAY_FILES:
        assert hashlib.sha256((d / f).read_bytes()).hexdigest() == m["files"][f]
        assert b"\r" not in (d / f).read_bytes()
    # the house JSON style, LF only
    assert raw.decode("utf-8") == json.dumps(m, indent=1, sort_keys=True) + "\n"


def test_the_origin_is_copied_when_the_sandbox_model_has_one(box):
    _sandbox_model("beta", _good(), info={"origin": "template:sihrs",
                                          "created_utc": "2026-11-01T00:00:00Z"})
    L.register("beta")
    m = json.loads((L.root() / "beta" / "1" / "model.json").read_text())
    assert m["origin"] == "template:sihrs" and "created_utc" not in m


def test_a_premade_folder_moves_the_next_version_past_it(box):
    _sandbox_model("beta", _good())
    (L.root() / "beta" / "3").mkdir(parents=True)
    assert L.register("beta")["version"] == 4


def test_a_failed_write_leaves_nothing(box, monkeypatch):
    _sandbox_model("beta", _good())

    def full(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(L, "write_json", full)
    with pytest.raises(OSError, match="disk full"):
        L.register("beta")
    left = list((L.root() / "beta").glob("*")) if (L.root() / "beta").exists() else []
    assert left == []


def test_two_registrations_at_once_get_distinct_versions(box, monkeypatch):
    _sandbox_model("beta", _good())
    real, gate, waited = os.rename, threading.Barrier(2), set()

    def rename(a, b):
        # both reach the rename before either makes it: one wins n
        if threading.current_thread() not in waited:
            waited.add(threading.current_thread())
            gate.wait(timeout=30)
        return real(a, b)
    monkeypatch.setattr(L.os, "rename", rename)
    out, errors = [], []

    def go():
        try:
            out.append(L.register("beta"))
        except Exception as e:                       # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors and sorted(r["version"] for r in out) == [1, 2]
    assert not list((L.root() / "beta").glob(".reg-*"))


def test_a_leftover_is_no_version_and_a_refused_rename_leaves_nothing(
        box, monkeypatch):
    _sandbox_model("beta", _good())
    left = L.root() / "beta" / ".reg-1-deadbeef"     # a crash's leftover
    left.mkdir(parents=True)
    (left / "model.bngl").write_text("begin model\n", encoding="utf-8")
    assert L.register("beta")["ref"] == "beta@1"
    assert [r["ref"] for r in L.list_models() if not r["shipped"]] == [
        "beta@1"]
    _sandbox_model("gamma", _good())

    def refused(a, b):
        raise PermissionError(errno.EACCES, "refused")
    monkeypatch.setattr(L.os, "rename", refused)
    with pytest.raises(PermissionError):
        L.register("gamma")
    assert not (L.root() / "gamma").exists()


def test_a_changed_version_is_not_the_one_registered_again(box):
    _sandbox_model("beta", _good())
    L.register("beta")
    with open(L.root() / "beta" / "1" / "priors.conf", "ab") as fh:
        fh.write(b"# edited\n")
    r = L.register("beta")
    assert (r["ref"], r["new"]) == ("beta@2", True)


def test_a_bom_and_crlf_model_registers_as_the_same(box):
    # Windows Notepad's "UTF-8 with BOM"
    _sandbox_model("win", {f: b"\xef\xbb\xbf" + t.replace("\n", "\r\n")
                           .encode("utf-8") for f, t in _good().items()})
    r = L.register("win")
    assert (r["fingerprint"], _codes(r["findings"])) == (SIHRS_FP, [])


def test_register_refuses_a_model_not_ready_for_replays(box):
    files = _good()
    files["priors.conf"] += "pf_jitter = 0.2\n"
    _sandbox_model("beta", files)
    with pytest.raises(Refusal) as e:
        L.register("beta")
    assert e.value.code == "KEY_NOT_ALLOWED"
    assert not (L.root() / "beta").exists()
    _sandbox_model("gamma", {"model.bngl": b"\xff\xfe" + b"begin model",
                             "priors.conf": files["priors.conf"]})
    _refused("FILE_UNREADABLE", L.register, "gamma")


def test_a_machine_finding_never_blocks(box, monkeypatch):
    monkeypatch.setattr(PF, "perl_available", lambda: False)
    _sandbox_model("beta", _good())
    r = L.register("beta")
    assert r["new"] and "MACHINE" in _codes(r["findings"])


# ---------------------------------------------------------------- names


def test_the_name_rules(box):
    _sandbox_model("SIHRS", _good())
    assert "shipped" in _refused("NAME_RESERVED", L.register, "SIHRS")
    _refused("NAME_INVALID", L.register, "no spaces")
    _sandbox_model("Beta2", _good())
    L.register("Beta2")
    _sandbox_model("beta2", _good())
    said = _refused("NAME_INVALID", L.register, "beta2")
    assert "the same as Beta2 ignoring case: macOS folders ignore case" in said
    _refused("NAME_INVALID", L.register, "beta3\n")
    # the Sandbox model's own spelling only, on every folder system
    _sandbox_model("beta3", _good())
    _refused("FILE_UNREADABLE", L.register, "BETA3")
    assert L.register("beta3")["ref"] == "beta3@1"


# ---------------------------------------------------------------- resolve


def test_resolve_hashes_the_bytes_again(box):
    _sandbox_model("beta", _good())
    L.register("beta")
    r = L.resolve("beta@1")
    assert (r["name"], r["version"], r["fingerprint"]) == ("beta", 1, SIHRS_FP)
    assert r["folder"] == L.root() / "beta" / "1" and not r["shipped"]
    assert r["files"] == {f: L.replay_text(f, t) for f, t in _good().items()}
    d = r["folder"]
    p = d / "priors.conf"
    good = p.read_bytes()
    p.write_bytes(good.replace(b"0.6 2.5", b"0.6 2.6"))
    assert "priors.conf" in _refused("MODEL_CHANGED", L.resolve, "beta@1")
    p.write_bytes(good)
    m = json.loads((d / "model.json").read_text())
    (d / "model.json").write_text(json.dumps(dict(m, fingerprint="0" * 64)))
    assert "model.json" in _refused("MODEL_CHANGED", L.resolve, "beta@1")
    for v in (2, True, 1.0):                           # true == 1 in Python
        (d / "model.json").write_text(json.dumps(dict(m, format_version=v)))
        _refused("FORMAT_UNKNOWN", L.resolve, "beta@1")
    (d / "model.json").unlink()
    assert "model.json" in _refused("MODEL_CHANGED", L.resolve, "beta@1")


#: a statement BNG2.pl would run through Perl before end model
STMT = 'setOption("SpeciesLabel","HNauty")'
#: the line breaks str.splitlines reads (PyBNF's reading of a model)
#: besides \n and \r, which BNG2.pl reads as none
PY_BREAKS = ("\x0b\x0c\x1c\x1d\x1e\x85\N{LINE SEPARATOR}"
             "\N{PARAGRAPH SEPARATOR}")


def suffixed(text: str) -> str:
    """model.bngl with a suffix before end model that passes every other
    rule, and that materialize_model's rewrite (suffix=>"..." over the whole
    file) turns into a statement outside every block: it eats end
    parameters ... begin functions, and BNG2.pl then runs the writeXML
    line through Perl."""
    return text.replace("end parameters\n", 'end parameters # suffix=>"\n'
                        'begin functions # "\nwriteXML({prefix=>\'x\'})\n'
                        "end functions\n", 1)


def _by_hand(name: str, files: dict) -> None:
    """library/<name>/1 written without register, its hashes agreeing."""
    d = L.root() / name / "1"
    d.mkdir(parents=True)
    hashes = {}
    for f, t in files.items():
        (d / f).write_bytes(t.encode("utf-8"))
        hashes[f] = hashlib.sha256(t.encode("utf-8")).hexdigest()
    L.write_json(d / "model.json", {
        "format_version": 1, "files": hashes,
        "fingerprint": L.fingerprint(hashes),
        "registered_utc": "2026-11-01T00:00:00Z"})


def test_a_version_written_by_hand_is_not_one(box):
    stored = {f: L.replay_text(f, t) for f, t in _good().items()}
    _by_hand("same", stored)                   # what register would write
    assert L.resolve("same@1")["fingerprint"] == SIHRS_FP
    _by_hand("stmt", dict(stored, **{"model.bngl": stored["model.bngl"]
                                     .replace("begin model\n",
                                              f"begin model\n{STMT}\n")}))
    assert "model.bngl (OUTSIDE_MODEL)" in _refused("MODEL_CHANGED",
                                                    L.resolve, "stmt@1")
    _by_hand("keys", dict(stored, **{"priors.conf": "anything = goes\n"
                                     + stored["priors.conf"]}))
    assert "priors.conf (KEY_NOT_ALLOWED)" in _refused("MODEL_CHANGED",
                                                       L.resolve, "keys@1")
    _by_hand("acts", _good())                  # its own actions kept
    assert "model.bngl (not in its replay normal form)" in _refused(
        "MODEL_CHANGED", L.resolve, "acts@1")
    assert [r["intact"] for r in L.list_models() if not r["shipped"]] == [
        False, False, True, False]
    # what the engine would run from a version written by hand is refused
    # too: a suffix before end model, an unbounded prior, a dropped prior
    _by_hand("sfx", dict(stored, **{"model.bngl": suffixed(
        stored["model.bngl"])}))
    assert "model.bngl (SUFFIX_IN_MODEL)" in _refused("MODEL_CHANGED",
                                                      L.resolve, "sfx@1")
    _by_hand("wide", dict(stored, **{"priors.conf": stored["priors.conf"]
                                     .replace("r__FREE 0.1 40.0",
                                              "r__FREE 0.1 1e999 u")}))
    assert "priors.conf (PRIOR_MALFORMED)" in _refused("MODEL_CHANGED",
                                                       L.resolve, "wide@1")
    _by_hand("nor", dict(stored, **{"priors.conf": stored["priors.conf"]
                                    .replace("loguniform_var = r__FREE "
                                             "0.1 40.0\n", "")}))
    assert "priors.conf (FREE_NO_PRIOR)" in _refused("MODEL_CHANGED",
                                                     L.resolve, "nor@1")


def test_references(box):
    for ref in ("x", "x@0", "x@01", "sihrs@1", "SIHRS", "a b@1", "", "x@",
                "sihrs\n", "beta@1\n"):
        _refused("MODEL_REF", L.resolve, ref)
    assert "the library has no model" in _refused("MODEL_NOT_FOUND",
                                                  L.resolve, "y@9")
    _sandbox_model("beta", _good())
    L.register("beta")
    assert "its versions are 1" in _refused("MODEL_NOT_FOUND", L.resolve,
                                            "beta@2")
    _refused("MODEL_NOT_FOUND", L.resolve, "BETA@1")    # the exact name only
    s = L.resolve("sihrs")
    assert (s["ref"], s["version"], s["folder"], s["shipped"]) == (
        "sihrs", None, None, True)
    assert L.parse_ref("beta@12") == ("beta", 12)
    assert L.short(SIHRS_FP) == "5edca88e"


def test_the_list_puts_the_shipped_models_first(box):
    for n in ("zeta", "Alpha"):
        _sandbox_model(n, _good())
        L.register(n)
    rows = L.list_models()
    assert [r["ref"] for r in rows] == list(L.SHIPPED_NAMES) + ["Alpha@1",
                                                                 "zeta@1"]
    assert all(r["intact"] for r in rows)
    assert rows[-1]["short"] == SIHRS_FP[:8] and rows[-1]["note"] == ""
    (L.root() / "zeta" / "1" / "priors.conf").write_text("changed\n")
    assert L.list_models()[-1]["intact"] is False
    assert {"ref", "name", "version", "fingerprint", "short",
            "registered_utc", "note", "origin", "intact", "shipped"} == set(rows[0])


# --------------------------------------------------------------- validate


def _edit(**changes) -> dict:
    files = _good()
    for f, (old, new) in changes.items():
        assert old in files[f], old
        files[f] = files[f].replace(old, new, 1)
    return files


def _tail(files: dict, more: str) -> dict:
    """The files with `more` after model.bngl's own actions, which a
    replay drops."""
    return dict(files, **{"model.bngl": files["model.bngl"] + more})


@pytest.mark.parametrize("files, code", [
    ({"model.bngl": b"begin model\n\xff\n", "priors.conf": "x"}, "FILE_UNREADABLE"),
    ({"model.bngl": _good()["model.bngl"]}, "FILE_UNREADABLE"),
    (_edit(**{"model.bngl": ("begin model\n", "")}), "NO_MODEL_BLOCK"),
    # a form feed: BNG2.pl's end model, not the one replay_text cuts at
    (_edit(**{"model.bngl": ("\nend model\n", "\nend model\x0c\n")}),
     "NO_MODEL_BLOCK"),
    (_edit(**{"model.bngl": ("begin model\n", 'setOption("SpeciesLabel",'
                             '"HNauty")\nbegin model\n')}), "OUTSIDE_MODEL"),
    (_edit(**{"model.bngl": ("begin molecule types",
                             "version(\"2.9.3\")\nbegin molecule types")}),
     "OUTSIDE_MODEL"),
    (_edit(**{"model.bngl": ("\nend model", "\nbegin actions\nsimulate()\n"
                             "end actions\nend model")}), "BLOCK_NOT_ALLOWED"),
    (_edit(**{"model.bngl": ("{{POP}}", "{{ POP }}")}), "TOKEN_MALFORMED"),
    (_edit(**{"model.bngl": ("{{S0FRAC}}", "{{s0frac}}")}), "TOKEN_MALFORMED"),
    (_edit(**{"priors.conf": ("pf_cum", "# {{X}}\npf_cum")}), "TOKEN_MALFORMED"),
    (_edit(**{"model.bngl": ("begin model\n", "begin model\n# {{FOO}}\n")}),
     "TOKEN_UNKNOWN"),
    (_edit(**{"model.bngl": ("{{RHO}}", "{{A0SHARE}}")}), "TOKEN_UNKNOWN"),
    ({f: t.replace("{{POP}}", "1000").replace("{{I0FRAC}}", "1e-5")
      for f, t in _good().items()}, "NO_STATE_TOKENS"),
    # what a replay drops counts for nothing
    (_tail({f: t.replace("{{POP}}", "1000").replace("{{I0FRAC}}", "1e-5")
            for f, t in _good().items()}, "# {{POP}}\n"), "NO_STATE_TOKENS"),
    (_edit(**{"model.bngl": ("H_weekly() =", "Hw() =")}), "NO_H_WEEKLY"),
    (_tail(_edit(**{"model.bngl": ("H_weekly() =", "Hw() =")}),
           "begin functions\nH_weekly() = 1\nend functions\n"), "NO_H_WEEKLY"),
    (_edit(**{"model.bngl": ("r__FREE 8.0\n", "")}), "NO_DISPERSION"),
    (_edit(**{"priors.conf": ("pf_cum", "postprocess = x\npf_cum")}),
     "KEY_NOT_ALLOWED"),
    (_edit(**{"priors.conf": ("pf_cum", "pf_jitter = 0.2\npf_cum")}),
     "KEY_NOT_ALLOWED"),
    (_edit(**{"priors.conf": ("pf_cumulative_observable = Hobs\n", "")}),
     "CUMULATIVE_REQUIRED"),
    # a priors.conf the engine reads only as written again (replay_conf):
    # 'kind = name low high', PyBNF's number form, finite, nothing after
    *[(_edit(**{"priors.conf": ("r__FREE 0.1 40.0", f"r__FREE {v}")}),
       "PRIOR_MALFORMED") for v in ("0.1 40.0 u", "0.1 1e999", "nan 40.0",
                                    "0.1 2_5", ".5 40.0", "0.1 \u0664\u0660",
                                    "0.1")],
    (_edit(**{"priors.conf": ("loguniform_var = r__FREE",
                              "loguniform_var = 9a__FREE")}),
     "PRIOR_MALFORMED"),
    (_edit(**{"priors.conf": ("r__FREE 0.1 40.0", "r__FREE 0 40.0")}),
     "PRIOR_BOUNDS"),
    (_edit(**{"priors.conf": ("loguniform_var = r__FREE 0.1 40.0",
                              "normal_var = r__FREE 8 0")}), "PRIOR_BOUNDS"),
    (_edit(**{"priors.conf": ("pf_cum", "uniform_var = N 1 2\npf_cum")}),
     "PRIOR_NOT_FREE"),
    (_edit(**{"priors.conf": ("pf_cum", "uniform_var = gone__FREE 1 2\n"
                              "pf_cum")}), "PRIOR_UNDEFINED"),
    (_edit(**{"priors.conf": ("pf_cum", "uniform_var k__FREE 1 2\npf_cum")}),
     "PRIORS_LINE"),
    (_edit(**{"priors.conf": ("= Hobs", "= Nope")}), "CUMULATIVE_NOT_OUTPUT"),
    (_edit(**{"priors.conf": ("= Hobs", "= Hobs Hcum")}),
     "CUMULATIVE_NOT_OUTPUT"),
    # every __FREE parameter has its prior: none dropped, r__FREE's either
    (_edit(**{"priors.conf": ("loguniform_var = r__FREE 0.1 40.0\n", "")}),
     "FREE_NO_PRIOR"),
    # a suffix before end model, in a comment inside a block or not
    (_edit(**{"model.bngl": ("end parameters\n", "# simulate({suffix=>\"x\"})"
                             "\nend parameters\n")}), "SUFFIX_IN_MODEL"),
    (_edit(**{"model.bngl": ("\nend model", "\n# suffix =>\nend model")}),
     "SUFFIX_IN_MODEL"),
    ({**_good(), "model.bngl": suffixed(_good()["model.bngl"])},
     "SUFFIX_IN_MODEL"),
    # a line break PyBNF reads and BNG2.pl does not, in a comment before
    # end model or on its line: PyBNF would write the statement back out
    *[(_edit(**{"model.bngl": ("end parameters\n", f"end parameters\n# a{c}"
                               f"{STMT}\n")}), "LINE_BREAK_NOT_ALLOWED")
      for c in PY_BREAKS],
    (_edit(**{"model.bngl": ("\nend model", f"\nend model # a\x0c{STMT}")}),
     "LINE_BREAK_NOT_ALLOWED"),
])
def test_each_replay_problem_fires(box, files, code, monkeypatch):
    def check(*a, **k):
        raise AssertionError("Check ran: the library's own rules found no "
                             "problem")
    # each code from the library's own rules, never from Check's
    monkeypatch.setattr("app.core.sandbox_check.check", check)
    found = L.validate(files)
    assert code in _codes(found), found
    hit = next(f for f in found if f["code"] == code)
    assert hit["tier"] == "problem" and hit["text"]


@pytest.mark.parametrize("old, new", [
    # a tab inside the block's name: BNG2.pl's \s
    ("end molecule types\n", f"end molecule\ttypes\n{STMT}\n"),
    # a backslash going on to a blank line
    ("end molecule types\n", f"end molecule types \\\n\n{STMT}\n"),
    # a line break only Python reads (NEL), inside comments
    ("end molecule types\n", "end molecule types\n# a\x85begin parameters\n"
     f"{STMT}\n# a\x85end parameters\n"),
    # a no-break space, which is not BNG2.pl's whitespace
    ("end molecule types\n", "end molecule types\n\u00a0begin parameters\n"
     f"{STMT}\n\u00a0end parameters\n"),
    # an end model inside a comment
    ("end reaction rules\n", f"end reaction rules\n# a\x1cend model\n{STMT}\n"),
])
def test_a_statement_is_found_where_bng2_reads_one(box, old, new):
    found = L.validate(_edit(**{"model.bngl": (old, new)}))
    assert [f for f in found if f["code"] == "OUTSIDE_MODEL"
            and "setOption" in f["text"]], found


def test_every_line_break_pybnf_reads_is_refused():
    """PyBNF reads model.bngl through str.splitlines: every break that
    reads but LF and CR (pinned to LF before the rules) is one the library
    refuses, so PyBNF and BNG2.pl read the same lines."""
    breaks = {chr(c) for c in range(sys.maxunicode + 1)
              if len(f"a{chr(c)}b".splitlines()) == 2}
    assert breaks == set(PY_BREAKS) | {"\n", "\r"}
    assert all(L._BREAKS.fullmatch(c) for c in PY_BREAKS)


def test_the_problems_name_their_lines(box):
    found = L.validate(_edit(**{"priors.conf": (
        "pf_cum", "postprocess = x\npf_jitter = 0.2\npf_cum")}))
    keys = [f for f in found if f["code"] == "KEY_NOT_ALLOWED"]
    assert [(f["file"], f["line"]) for f in keys] == [("priors.conf", 6),
                                                       ("priors.conf", 7)]
    assert "postprocess" in keys[0]["text"] and "pf_jitter" in keys[1]["text"]
    bare = L.validate(_edit(**{"model.bngl": ("begin model\n", "")}))
    assert _codes(bare) == ["NO_MODEL_BLOCK"]          # one, not one per line
    # one FREE_NO_PRIOR per parameter, in the model's order; a malformed
    # prior still names its parameter: one problem, not two
    files = _good()
    for gone in ("uniform_var = eps1__FREE 0.0 1.0\n",
                 "loguniform_var = r__FREE 0.1 40.0\n"):
        assert gone in files["priors.conf"]
        files["priors.conf"] = files["priors.conf"].replace(gone, "")
    found = L.validate(files)
    assert _codes(found) == ["FREE_NO_PRIOR", "FREE_NO_PRIOR"]
    assert [f["text"].split()[0] for f in found] == ["eps1__FREE", "r__FREE"]
    assert _codes(L.validate(_edit(**{"priors.conf": (
        "r__FREE 0.1 40.0", "r__FREE 0.1 40.0 u")}))) == ["PRIOR_MALFORMED"]


def test_the_replay_warnings(box):
    found = L.validate(_edit(**{"model.bngl": ("{{GAMMA}}", "2.1875")}))
    assert _codes(found) == ["GAMMA_ASSUMED"]
    # a model that fits i0 keeps {{POP}} alone, and assumes no gamma
    assert _codes(L.validate({f: t.replace("{{I0FRAC}}", "1e-5")
                              .replace("{{GAMMA}}", "2.1875")
                              for f, t in _good().items()})) == []
    # a block's name read with its spaces collapsed, as BNG2.pl reads it
    assert _codes(L.validate(_edit(**{"model.bngl": (
        "begin reaction rules", "begin  reaction   rules")}))) == []
    found = L.validate(_edit(**{"model.bngl": (
        "generate_network({overwrite=>1})", "generate_network({overwrite=>1})"
        + "".join(f"\nwriteXML{i}()" for i in range(6)))}))
    assert found[0]["text"].endswith("writeXML4() (and 1 more)")
    found = L.validate(_edit(**{"model.bngl": (
        "generate_network({overwrite=>1})",
        "generate_network({overwrite=>1})\nsetParameter(\"Reff\",2)\n"
        "writeSBML()\nsimulate({method=>\"ode\",\\\n t_end=>5})")}))
    assert _codes(found) == ["ACTIONS_DROPPED"]
    assert found[0]["tier"] == "warning"
    assert 'setParameter("Reff",2); writeSBML()' in found[0]["text"]
    assert "t_end" not in found[0]["text"]             # a continued simulate


def test_check_runs_last_and_keeps_its_own_codes(box, monkeypatch):
    # a prior out of order is the library's own problem, with Check's code
    found = L.validate(_edit(**{"priors.conf": ("Reff__FREE 0.6 2.5",
                                                "Reff__FREE 2.5 0.6")}))
    assert _codes(found) == ["PRIOR_BOUNDS"]
    # BNG2.pl's own refusal of the network, through the fake
    found = L.validate(_edit(**{"model.bngl": ("begin model\n",
                                               "begin model\n# broken\n")}))
    assert _codes(found) == ["NETWORK_FAILS"] and "bad rule" in found[0]["text"]
    # the data and actions codes never come through (SAMPLE_EXP, FluBNF's
    # actions), nor NO_CUMULATIVE; the rest do, a machine finding too
    from app.core import sandbox_check
    seen = []

    def check(files, work=None):
        seen.append(files)
        return {"codes": [finding(c, c) for c in (
            "EXP_UNREADABLE", "EXP_TIME_ORDER", "ROW_BEFORE_START", "ONE_ROW",
            "SCALE_OFF", "NO_CUMULATIVE", "NO_SUFFIX", "NO_GENERATE_NETWORK",
            "START_OUTSIDE_PRIOR", "MACHINE")]}
    monkeypatch.setattr(sandbox_check, "check", check)
    assert _codes(L.validate(_good())) == ["START_OUTSIDE_PRIOR", "MACHINE"]
    sent = seen[0]
    assert sent["data.exp"] == L.SAMPLE_EXP
    assert "{{" not in sent["model.bngl"] and "N       1000000" in sent["model.bngl"]
    assert sent["model.bngl"].endswith(L.REPLAY_ACTIONS + "\n")
    # an earlier problem: Check is never run
    seen.clear()
    L.validate(_edit(**{"model.bngl": ("{{POP}}", "{{ POP }}")}))
    assert seen == []


def test_replay_conf_rewrites_every_line():
    assert L.replay_conf(L.shipped_files("sihrs")) == ("Hobs", PF.VARS_1S)
    assert L.replay_conf(L.shipped_files("sihrs-2strain")) == ("Hobs",
                                                                PF.VARS_2S)
    # comments, spaces and any number PyBNF reads become canonical lines;
    # the first cumulative line is written, its comment cut
    files = _good()
    files["priors.conf"] = (
        "# by hand\n"
        "  uniform_var   =   Reff__FREE   0.60  +2.5E0   # wide\n\n"
        "uniform_var = eps1__FREE 0 1\n"
        "uniform_var=phi1__FREE 0.0 52\n"
        "loguniform_var = mult__FREE 2e-3 1\n"
        "loguniform_var = r__FREE 1E-1 40.\n"
        "pf_cumulative_observable = Hobs#x\n"
        "pf_cumulative_observable = H_weekly\n")
    assert L.replay_conf(files) == ("Hobs", PF.VARS_1S)
    # a bad second cumulative line is refused all the same
    files["priors.conf"] += "pf_cumulative_observable = Nope\n"
    _refused("CUMULATIVE_NOT_OUTPUT", L.replay_conf, files)
    # what lies after end model counts for nothing
    files = _tail(_good(), "begin functions\nHcum2() = Hobs\nend functions\n")
    files["priors.conf"] = files["priors.conf"].replace("= Hobs", "= Hcum2")
    _refused("CUMULATIVE_NOT_OUTPUT", L.replay_conf, files)


def test_the_shipped_models_validate_clean(box):
    for n in L.SHIPPED_NAMES:
        found = L.validate(L.shipped_files(n), shipped=True)
        assert [f for f in found if f["tier"] != "machine"] == [], (n, found)
    found = L.validate(L.shipped_files("sihrs-2strain"))
    assert _codes(found) == ["TOKEN_UNKNOWN"]
    assert "{{A0SHARE}}" in found[0]["text"]


def test_every_example_is_refused_for_replays(box):
    for e in sb.list_examples():
        files = {f: (sb.EXAMPLES / e / f).read_text(encoding="utf-8")
                 for f in L.REPLAY_FILES}
        codes = _codes(L.validate(files))
        assert "NO_STATE_TOKENS" in codes, (e, codes)
        assert ("NO_H_WEEKLY" in codes) == (e != "sihrs_example"), (e, codes)
