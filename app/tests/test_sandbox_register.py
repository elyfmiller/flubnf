"""Register for replays from the Sandbox (POST /sandbox/models/<name>/
register; app/core/library.py register, and Check's Ready for replays
line in app/ui/static/sandbox.js): the editor's text saved first, then
frozen as the library's next version of the name, or named as the
version that already holds it; refused in words, each finding with its
code; a name that is not exactly a Sandbox model's saves nothing; a
double click registers once. Hub-free and engine-free (strict_bng).
"""
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                # noqa: E402

from app.core import library as L                        # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402
from test_sandbox_placeholders import strict_bng         # noqa: E402,F401
from test_sandbox_shipped import FD, hub                 # noqa: E402,F401

client = TestClient(srv.app)
SCRIPT = (Path(__file__).resolve().parents[1] / "ui" / "static"
          / "sandbox.js").read_text(encoding="utf-8")


def _beta() -> dict:
    sb.from_shipped("beta", "Alabama", FD, template=True)
    return sb.read_model("beta")


def _register(name: str = "beta", **fields):
    ui_state._status.pop("flash", None)
    ui_state._status.pop("flash_detail", None)
    r = client.post(f"/sandbox/models/{name}/register", data=fields,
                    follow_redirects=False)
    assert r.status_code == 303
    return r


def _flash() -> str:
    return ui_state._status.get("flash") or ""


def test_register_saves_the_posted_text_first_then_freezes_it(strict_bng, hub):
    files = _beta()
    posted = files["model.bngl"].replace("Reff__FREE 1.20", "Reff__FREE 1.30")
    r = _register(model_bngl=posted)
    assert r.headers["location"] == "/sandbox?model=beta"
    assert "Saved beta." in _flash() and "Registered beta@1 (" in _flash()
    assert ui_state._status.get("flash_kind") == "ok"
    assert sb.read_model("beta")["model.bngl"] == posted
    v = L.resolve("beta@1")
    assert v["files"]["model.bngl"] == L.replay_text("model.bngl", posted)
    assert re.search(rf"Registered beta@1 \({v['fingerprint'][:8]}\)\.",
                     _flash())


def test_a_new_versions_notes_are_in_the_tip(strict_bng, hub):
    files = _beta()
    _register(model_bngl=files["model.bngl"].replace("{{GAMMA}}", "2.1875"))
    assert _flash().startswith("Saved beta.  Registered beta@1 ("), _flash()
    tip = ui_state._status.get("flash_detail") or ""
    assert tip.startswith("Worth a look: ") and "(GAMMA_ASSUMED)" in tip, tip


def test_the_same_files_name_their_version(strict_bng, hub):
    _beta()
    _register()
    assert _flash().startswith("Registered beta@1 (")
    _register()
    assert re.fullmatch(r"beta@1 already holds these files \([0-9a-f]{8}\); "
                        r"nothing new was registered\.", _flash()), _flash()
    assert L._versions("beta") == [1]


def test_an_edit_registers_the_next_version_and_check_names_it(strict_bng,
                                                               hub):
    files = _beta()
    _register()
    # any edit is a new version, a comment's too
    edited = files["model.bngl"] + "# a second thought\n"
    _register(model_bngl=edited.replace("# A replay", "# Each replay"))
    assert "Registered beta@2 (" in _flash()
    r = client.post("/api/sandbox/models/beta/check").json()
    reg = r["replays"]["registered"]
    assert reg["ref"] == "beta@2" and reg["version"] == 2
    assert re.fullmatch(r"[0-9a-f]{8}", reg["short"])
    assert reg["fingerprint"] == L.resolve("beta@2")["fingerprint"]
    # the editor's text, not the saved file: not registered
    r = client.post("/api/sandbox/models/beta/check",
                    data={"model_bngl": files["model.bngl"].replace(
                        "Reff__FREE 1.20", "Reff__FREE 1.25")}).json()
    assert r["replays"]["ready"] is True
    assert r["replays"]["registered"] is None
    # the first version's files are still named
    r = client.post("/api/sandbox/models/beta/check",
                    data={"model_bngl": files["model.bngl"]}).json()
    assert r["replays"]["registered"]["ref"] == "beta@1"


def test_register_refuses_in_words_and_codes(strict_bng, hub):
    files = _beta()
    r = client.post("/api/sandbox/models/beta/check", data={
        "priors_conf": files["priors.conf"] + "pf_jitter = 0.2\n"}).json()
    assert r["ok"]                                # the Sandbox runs it
    assert r["replays"]["ready"] is False
    assert [f["code"] for f in r["replays"]["findings"]] == ["KEY_NOT_ALLOWED"]
    _register(priors_conf=files["priors.conf"] + "pf_jitter = 0.2\n")
    assert ui_state._status.get("flash_kind") == "warn"
    assert re.search(r"Not registered: priors\.conf line \d+: pf_jitter is "
                     r"not a key a model for replays may set .*"
                     r"\(KEY_NOT_ALLOWED\)", _flash()), _flash()
    # the posted text stays saved, as with Save and run
    assert sb.read_model("beta")["priors.conf"].endswith("pf_jitter = 0.2\n")
    assert not (L.root() / "beta").exists()
    # a reserved name is said the same way
    sb.from_shipped("x", "Alabama", FD)
    sb.copy_model("x", "SIHRS")
    _register("SIHRS")
    assert "Not registered: SIHRS is a shipped model's name" in _flash()
    assert "(NAME_RESERVED)" in _flash()


def test_a_wrong_case_or_missing_name_saves_nothing(strict_bng, hub):
    files = _beta()
    before = {p.name: p.read_bytes() for p in (sb.MODELS / "beta").iterdir()}
    r = _register("BETA", model_bngl=files["model.bngl"] + "# changed\n")
    assert r.headers["location"] == "/sandbox"
    assert _flash() == ("Not registered: no Sandbox model is named 'BETA' "
                        "(letter case counts).")
    assert ui_state._status.get("flash_kind") == "warn"
    assert {p.name: p.read_bytes()
            for p in (sb.MODELS / "beta").iterdir()} == before
    _register("nobody", model_bngl=files["model.bngl"])
    assert "no Sandbox model is named 'nobody'" in _flash()
    assert not (sb.MODELS / "nobody").exists()
    assert not L.root().exists()


def test_a_double_click_registers_once(strict_bng, hub, monkeypatch):
    _beta()
    real = L._match

    def slow(*a, **k):
        # each click has looked for the version before either writes one
        v = real(*a, **k)
        time.sleep(0.2)
        return v
    monkeypatch.setattr(L, "_match", slow)
    errors = []

    def click():
        try:
            ui_sandbox.sandbox_register("beta", "", "", "")
        except Exception as e:                       # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=click) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors and L._versions("beta") == [1]


def test_the_check_report_says_it_in_its_words():
    # the template start shows the hub start's Location and dates
    for words in ("v === 'template:sihrs'", "'Ready for replays:'",
                  "'Not ready for replays:'",
                  "'Register freezes these files as a new version.'",
                  "' to fix before Register.'",
                  "'/register\" formnovalidate>Register</button>",
                  "pl && pl.location", "'Placeholders filled for'",
                  "'Simulate suffix'"):
        assert words in SCRIPT, words
