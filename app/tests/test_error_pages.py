"""Unknown pages and malformed requests (G22): every answer a student can
reach from a link or a typed address is a page of the console with the way
on, never bare text or JSON; impossible dates are refused; the report view
and its download agree; a deleted Sandbox model is said to be gone."""
import pytest
from fastapi.testclient import TestClient

import app.core.runs as runs_mod                     # noqa: E402
from app.core import sandbox as sb                   # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui import state as ui_state                 # noqa: E402

client = TestClient(srv.app)


def _notice(r):
    """The notice's text (routes/output._notice) and the shell's nav."""
    assert "text/html" in r.headers["content-type"]
    assert '<nav' in r.text or 'class="tab' in r.text
    return r.text.split('id="out-notice"', 1)[1]


# ------------------------------------------------------------ UI-10, WI-14

def test_an_unknown_address_is_a_console_page_with_the_way_home():
    r = client.get("/nope")
    assert r.status_code == 404
    body = _notice(r)
    assert "No page at this address" in body and 'href="/"' in body
    assert "<h1>Not found</h1>" in r.text
    assert 'aria-current="page"' not in r.text      # no tab is this page
    # API paths and static files keep the plain answers their callers read
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    assert client.get("/static/nope.css").status_code == 404


def test_an_unknown_model_is_a_console_page_under_models():
    r = client.get("/model/nope")
    assert r.status_code == 404
    body = _notice(r)
    assert "No model named nope" in body and 'href="/models"' in body
    assert 'aria-current="page">Models</a>' in r.text


def test_an_unknown_replay_or_season_report_is_a_console_page(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    r = client.get("/retro/dataset/nope/20260101T000000")
    assert r.status_code == 404
    assert "No such replay" in _notice(r) and 'href="/retro"' in r.text
    from app.ui import retro_seasons
    monkeypatch.setattr(retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(retro_seasons, "RETRO_SEAL", tmp_path / "retro_seal")
    monkeypatch.setattr(retro_seasons, "RETRO_RESEAL", tmp_path / "retro_reseal")
    r = client.get("/retro/2097-98/report")
    assert r.status_code == 404
    assert "no completed weeks yet" in _notice(r)
    assert 'href="/retro/2097-98"' in r.text
    # the results page's Reveal reads the API path, which stays plain
    r = client.get("/api/retro/2097-98/report_path")
    assert r.status_code == 404 and "text/plain" in r.headers["content-type"]


# -------------------------------------------------------------------- OU-16

def test_malformed_output_requests_get_the_console_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    r = client.get("/output/download")
    assert r.status_code == 404 and "File not found in app state" in _notice(r)
    r = client.post("/output/reveal", follow_redirects=False)
    assert r.status_code == 303
    assert ui_state._status.get("flash", "").startswith("Nothing opened")
    # an impossible date is refused, not "no archived report"
    r = client.get("/output/report?date=2026-13-45")
    assert r.status_code == 400 and "Invalid date" in r.text
    assert client.get("/output/report/download?date=2026-13-45").status_code == 400
    # a missing archive: the view and its download agree
    for url in ("/output/report?date=2097-01-03",
                "/output/report/download?date=2097-01-03"):
        assert client.get(url).status_code == 404, url


# -------------------------------------------------------------------- SB-16

def test_a_deleted_sandbox_model_is_said_to_be_gone(sandbox_root):
    with pytest.raises(sb.SandboxError) as e:
        sb.model_dir("del_me")
    assert str(e.value) == "no sandbox model named 'del_me'"
    r = client.get("/sandbox?model=del_me")       # the page shows the flash
    assert r.status_code == 200
    assert "Not opened: no sandbox model named &#39;del_me&#39;" in r.text
    assert "is missing model.bngl" not in r.text
    # a model whose folder lost a file still says which file
    (sb.MODELS / "half").mkdir(parents=True)
    (sb.MODELS / "half" / "model.bngl").write_text("begin model\nend model\n")
    with pytest.raises(sb.SandboxError, match="is missing data.exp, priors.conf"):
        sb.model_dir("half")
