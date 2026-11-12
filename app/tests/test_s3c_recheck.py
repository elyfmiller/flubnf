"""The reviewer's re-check of #98 and #100 (dev fd76172), its five S3s.

  * Output: a request that writes the kept hub check results while another
    request is still reading them back after a relaunch keeps every entry
    on disk, not its own one (finding 1).
  * Sandbox: a dataset label's "uploaded" day is the day where the
    console runs, not the UTC day; the stored stamp is unchanged
    (finding 2).
  * Forecast's Data issues box: a select the last form left on "Both
    from" for a state whose rule was on comes back to its own choice when
    the rule goes off or Reset to defaults runs (finding 3, FC-13).
  * reclaim.inside_any: a volume whose folders all report inode 0 does
    not make every folder protected; a name match still protects
    (finding 4).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import hubcheck                                  # noqa: E402
from app.ui.routes import output as O                          # noqa: E402


def _ok(path):
    """hubcheck.summary's shape for a file that passes."""
    return {"ok": True, "round": False, "problems": [],
            "reference_date": "", "due": None}


def _kept(state: Path) -> list:
    return json.loads((state / O.CHECKS_FILE).read_text(encoding="utf-8")
                      )["files"]


def _csv(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{name}.csv"
    f.write_bytes(b"x")
    return f


@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    yield tmp_path
    O._CHECKED.clear()
    O._CHECKS_READ.clear()


# ------------------------------------------- finding 1: read, then keep

def _in_read_checks() -> bool:
    f = sys._getframe(2)
    while f is not None:
        if f.f_code.co_name == "_read_checks":
            return True
        f = f.f_back
    return False


def test_a_result_kept_while_the_kept_file_is_read_back_keeps_every_entry(
        state, monkeypatch):
    """After a relaunch request A reads the kept results; while it reads,
    request B checks a new file and writes the results. The file on disk
    then holds A's three entries and B's, not B's alone. The second request
    waits at most 1.5 s, so a fix that makes it wait for the read cannot
    hang here."""
    monkeypatch.setattr(hubcheck, "summary", _ok)
    olds = [_csv(state / "f", n) for n in "abc"]
    for f in olds:
        O._check_summary(str(f))
    assert len(_kept(state)) == 3
    # a relaunch: nothing in memory, the folder not read yet
    O._CHECKED.clear()
    O._CHECKS_READ.clear()
    calls = []
    monkeypatch.setattr(hubcheck, "summary",
                        lambda p: calls.append(p) or _ok(p))
    new = _csv(state / "f", "d")
    errors = []

    def second():
        try:
            O._check_summary(str(new))
        except BaseException as e:                 # noqa: BLE001
            errors.append(e)
    t2 = threading.Thread(target=second, daemon=True)
    real = O._rules_digest
    fired = threading.Event()

    def hooked():
        # A is reading the kept file back: B checks and writes now
        if (not fired.is_set() and threading.current_thread() is not t2
                and _in_read_checks()):
            fired.set()
            t2.start()
            end = time.monotonic() + 1.5
            while time.monotonic() < end and t2.is_alive():
                time.sleep(0.005)
        return real()
    monkeypatch.setattr(O, "_rules_digest", hooked)
    O._check_summary(str(olds[0]))
    t2.join(10)
    assert fired.is_set() and not t2.is_alive() and errors == []
    assert calls == [str(new)]                 # the kept ones are not checked
    on_disk = sorted(r[0] for r in _kept(state))
    in_memory = sorted(k if isinstance(k, str) else k[0] for k in O._CHECKED)
    assert in_memory == sorted(str(f) for f in olds + [new])
    assert on_disk == in_memory, (f"in memory: {len(in_memory)}, "
                                  f"on disk: {len(on_disk)}")


# --------------------------------- finding 2: the upload day where it runs

needs_tzset = pytest.mark.skipif(not hasattr(time, "tzset"),
                                 reason="time.tzset is POSIX only")


@pytest.fixture()
def arizona():
    """This process on Arizona time (UTC-7, no daylight time)."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "America/Phoenix"
    time.tzset()
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def _ds(ident, created, name="cases"):
    """A stored dataset as dataset_choices reads it."""
    import types
    meta = {"groups": [{"name": "Springfield", "first": "2024-01-06",
                        "last": "2024-06-29", "population": 100000}],
            "created": created}
    return types.SimpleNamespace(id=ident, name=name, kind="count",
                                 pf_eligible=True, meta=meta)


@needs_tzset
def test_the_upload_day_in_a_label_is_the_local_day(arizona, monkeypatch):
    """Two uploads of cases.csv over the same weeks, at 6 pm and 1 pm
    Arizona time a day apart: by the UTC day both read 2026-11-10 and
    were told apart by their ids; by the local day each has its own."""
    from app.core import datasets
    from app.core import sandbox_data as sbd
    stored = [_ds("cases-a1b2c3d4e5f6", "2026-11-10T20:00:00Z"),
              _ds("cases-0f9e8d7c6b5a", "2026-11-10T01:00:00Z")]
    monkeypatch.setattr(datasets, "list_datasets", lambda: stored)
    labels = [d["label"] for d in sbd.dataset_choices()]
    assert labels == ["cases (2024-01-06 to 2024-06-29, uploaded 2026-11-10)",
                      "cases (2024-01-06 to 2024-06-29, uploaded 2026-11-09)"]
    # the stored stamp is left as it is, in UTC
    assert [d.meta["created"] for d in stored] == ["2026-11-10T20:00:00Z",
                                                   "2026-11-10T01:00:00Z"]


@needs_tzset
def test_an_upload_day_without_a_readable_stamp_is_none(arizona):
    from app.core import sandbox_data as sbd
    assert sbd._uploaded_day("2026-11-10T01:00:00Z") == "2026-11-09"
    assert sbd._uploaded_day("2026-11-10T08:00:00Z") == "2026-11-10"
    for bad in (None, "", "yesterday"):
        assert sbd._uploaded_day(bad) == ""


def test_the_store_still_stamps_created_in_utc():
    """Only the label reads the local day: the stored stamp stays UTC."""
    store = (Path(__file__).resolve().parents[1] / "core" / "datasets"
             / "store.py").read_text(encoding="utf-8")
    assert ('"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),'
            in store)


# -------------------- finding 3 (FC-13): a page shown again after a run

JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (NODE or JSC.is_file()),
    reason="no JavaScript engine (node or JavaScriptCore jsc)")
UI = Path(__file__).resolve().parents[1] / "ui"


def _run_js(tmp_path, text: str):
    """Run one script under node, else jsc; its last printed line as JSON."""
    f = tmp_path / "box.js"
    f.write_text("var say = typeof print === 'function' ? print : "
                 "function (s) { console.log(s); };\n" + text,
                 encoding="utf-8")
    cmd = [NODE, str(f)] if NODE else [str(JSC), str(f)]
    got = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr or got.stdout
    return json.loads(got.stdout.strip().splitlines()[-1])


#: stand-in elements for the box's own script. The page as a browser loads
#: it: the box's script runs before the Model settings panel is in the
#: page (no knob found), and the panel is there at DOMContentLoaded.
_PAGE = """
function Sel(rules, values, value, rec) {
  var check = {hidden: value !== rec};          // as the server renders it
  var on = {};
  var s = {options: values.map(function (v) {
             return {value: v, hidden: false, disabled: false}; }),
           dataset: {rules: rules, rec: rec, issue: 'zero'}, _v: value,
           check: check, on: on,
           parentNode: {querySelector: function () { return check; }},
           addEventListener: function (t, f) { on[t] = f; }};
  Object.defineProperty(s, 'selectedIndex', {get: function () {
    for (var i = 0; i < s.options.length; i++)
      if (s.options[i].value === s._v) return i;
    return -1; }});
  Object.defineProperty(s, 'value', {
    get: function () { var i = s.selectedIndex; return i < 0 ? '' : s.options[i].value; },
    set: function (v) { s._v = v; }});
  return s;
}
var ALL = ['level', 'extend', 'blend', 'set_aside', 'omit'];
var sels = SELS;
var knob = {value: KNOB, disabled: false};
var panel = false;
var L = {}, D = [];
var form = {
  querySelector: function (q) {
    return panel && q === '[name="knob.data.trailing_zero"]' ? knob : null; },
  addEventListener: function (t, f) { (L[t] = L[t] || []).push(f); }};
var box = {
  closest: function () { return form; },
  querySelectorAll: function (q) {
    return q === 'select[data-rules]' || q === 'select[name^="gap."]' ? sels : []; }};
var document = {
  getElementById: function (id) { return id === 'data-issues' ? box : null; },
  addEventListener: function (t, f) { if (t === 'DOMContentLoaded') D.push(f); }};
SCRIPT
panel = true;
D.forEach(function (f) { f({type: 'DOMContentLoaded'}); });
function setting(v) {
  knob.value = v;
  L.change.forEach(function (f) { f({target: {name: 'knob.data.trailing_zero'}}); });
}
function reset() {                     // Reset to defaults, then its event
  knob.value = 'keep';
  L['ms-reset'].forEach(function (f) { f({type: 'ms-reset'}); });
}
// what a run would record: the choice, its check, and whether it is the
// rule's choice (set aside under the rule, else the recommendation)
function state(s) {
  var rec = knob.value === 'missing' ? 'set_aside' : s.dataset.rec;
  return [s.value, !s.check.hidden, s.value === rec];
}
"""


def _page(tmp_path, sels: str, knob: str, steps: str):
    box = (UI / "templates" / "_data_issues.html").read_text(encoding="utf-8")
    script = box.split("<script>", 1)[1].split("</script>", 1)[0]
    text = (_PAGE.replace("SCRIPT", script).replace("SELS", sels)
            .replace("KNOB", json.dumps(knob))
            + "var out = {};\n" + steps + "\nsay(JSON.stringify(out));\n")
    return _run_js(tmp_path, text)


@needs_js
def test_after_a_run_the_rule_off_puts_back_the_recommendation(tmp_path):
    """Utah's recommendation is Level; the rule moved it to "Both from"
    and the form was run (or refused). The page comes back with Utah on
    "Both from" and the rule on. The rule off puts Level back with its
    check, so a run records the recommendation followed."""
    got = _page(tmp_path,
                "[Sel('data.trailing_zero', ALL, 'set_aside', 'level')]",
                "missing", """
var utah = sels[0];
out.shown = state(utah);
setting('keep');
out.off = state(utah);
setting('missing');
out.on_again = state(utah);
setting('keep');
out.off_again = state(utah);
""")
    assert got == {"shown": ["set_aside", True, True],
                   "off": ["level", True, True],
                   "on_again": ["set_aside", True, True],
                   "off_again": ["level", True, True]}


@needs_js
def test_after_a_run_reset_to_defaults_puts_back_the_recommendation(
        tmp_path):
    got = _page(tmp_path,
                "[Sel('data.trailing_zero', ALL, 'set_aside', 'level')]",
                "missing", """
reset();
out.reset = state(sels[0]);
""")
    assert got == {"reset": ["level", True, True]}


@needs_js
def test_after_a_run_a_choice_made_by_hand_still_stands(tmp_path):
    """Shown again under the rule, a choice made by hand stands when the
    rule goes off: Leave out, or "Both from" picked again. A "Both from"
    the last form held with the rule off was a choice made by hand: the
    rule on and off again leaves it. A state whose recommendation is
    "Both from" keeps it."""
    got = _page(tmp_path, """[
  Sel('data.trailing_zero', ALL, 'set_aside', 'level'),
  Sel('data.trailing_zero', ALL, 'set_aside', 'level'),
  Sel('data.trailing_zero', ALL, 'set_aside', 'set_aside')]""",
                "missing", """
var ohio = sels[0], iowa = sels[1], utah = sels[2];
ohio._v = 'omit'; ohio.on.change();
iowa._v = 'set_aside'; iowa.on.change();
setting('keep');
out.ohio = state(ohio);
out.iowa = state(iowa);
out.utah = state(utah);
""")
    assert got == {"ohio": ["omit", False, False],
                   "iowa": ["set_aside", False, False],
                   "utah": ["set_aside", True, True]}
    off = _page(tmp_path,
                "[Sel('data.trailing_zero', ALL, 'set_aside', 'level')]",
                "keep", """
var utah = sels[0];
out.shown = state(utah);
setting('missing');
setting('keep');
out.off = state(utah);
""")
    assert off == {"shown": ["set_aside", False, False],
                   "off": ["set_aside", False, False]}


# ------------------------- finding 4: a volume with no file identity

class _NoInodes:
    """reclaim's os, with os.stat reporting inode 0 for every path, as a
    volume that gives no file identity does."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def stat(p, *a, **k):
        st = os.stat(p, *a, **k)
        return os.stat_result((st.st_mode, 0, st.st_dev, st.st_nlink,
                               st.st_uid, st.st_gid, st.st_size,
                               int(st.st_atime), int(st.st_mtime),
                               int(st.st_ctime)))


def test_inode_zero_does_not_make_every_folder_protected(tmp_path,
                                                         monkeypatch):
    from app.core import reclaim
    root = tmp_path / "sealed"
    (root / "inside").mkdir(parents=True)
    other = tmp_path / "work" / "run1"
    other.mkdir(parents=True)
    monkeypatch.setattr(reclaim, "os", _NoInodes())
    assert reclaim.os.stat(root).st_ino == 0      # the volume as described
    assert not reclaim.inside_any(other, [root])
    assert not reclaim.inside_any(tmp_path / "work", [root])
    # a name match still protects, the root itself and inside it
    assert reclaim.inside_any(root, [root])
    assert reclaim.inside_any(root / "inside", [root])
    assert reclaim.inside_any(root / "inside" / "not-yet", [root])
    # unresolvable still counts as inside
    monkeypatch.setattr(reclaim.Path, "resolve",
                        lambda self, *a, **k: (_ for _ in ()).throw(
                            OSError("no")))
    assert reclaim.inside_any(other, [root])


def test_with_inodes_another_spelling_still_matches(tmp_path, monkeypatch):
    """Where the volume gives inodes, a folder by another name that
    reports the root's identity still counts as inside (a stand-in for
    /users/ and /Users/ on a case-insensitive volume)."""
    from app.core import reclaim
    root = tmp_path / "sealed"
    (root / "inside").mkdir(parents=True)
    alias = tmp_path / "SEALED-alias"
    alias.mkdir()
    real = os.stat(root)

    class _Same:
        def __getattr__(self, name):
            return getattr(os, name)

        @staticmethod
        def stat(p, *a, **k):
            # the alias reports the root's identity: another spelling of it
            return real if Path(p) == alias else os.stat(p, *a, **k)
    monkeypatch.setattr(reclaim, "os", _Same())
    assert reclaim.inside_any(alias, [root])
    assert not reclaim.inside_any(tmp_path / "elsewhere", [root])
