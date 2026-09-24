"""The retired blend is never a choice beside the models that ship: records
from before its retirement store it under "ensemble", but the Forecast
page's model buttons and the season player's checkboxes never offer or draw
it, even when a legacy record stored nothing else (as the home outlook).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient              # noqa: E402

import app.ui.server as srv                            # noqa: E402
from app.core import report_v2                         # noqa: E402

client = TestClient(srv.app)

PLAYER = Path(__file__).resolve().parents[1] / "ui" / "static" / "player.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
needs_jsc = pytest.mark.skipif(not JSC.is_file(),
                               reason="JavaScriptCore jsc not available")

Q = {"0.025": 80.0, "0.5": 100.0, "0.975": 130.0}


def _res(*models):
    fan = {"Ohio": {str(h): dict(Q) for h in range(4)}}
    return {"models": {m: fan for m in models},
            "observed": {"Ohio": [["2026-01-03", 95.0]]}}


def _fanq(monkeypatch, *models):
    monkeypatch.setattr(srv, "_latest_results", lambda: ("r1", _res(*models)))
    r = client.get("/forecast")
    assert r.status_code == 200
    m = re.search(r"const FANQ = (\{.*?\});", r.text)
    assert m, "the page embeds no FANQ"
    return list(json.loads(m.group(1)))


def test_a_legacy_run_offers_only_the_models_that_ship(monkeypatch):
    # a run from before the retirement stored all three
    assert _fanq(monkeypatch, "ensemble", "pf", "analogue") == ["pf", "analogue"]


def test_the_ship_order_holds_whatever_order_the_run_stored(monkeypatch):
    assert _fanq(monkeypatch, "analogue", "ensemble", "pf") == ["pf", "analogue"]


def test_a_groundhog_only_legacy_run_offers_the_groundhog(monkeypatch):
    assert _fanq(monkeypatch, "analogue", "ensemble") == ["analogue"]


def test_a_legacy_run_with_nothing_else_draws_no_blend(monkeypatch):
    assert _fanq(monkeypatch, "ensemble") == []


def test_a_current_run_is_unchanged(monkeypatch):
    assert _fanq(monkeypatch, "pf", "analogue") == ["pf", "analogue"]


def _offered(tmp_path, have):
    """offeredModels, run for real under JavaScriptCore."""
    drv = tmp_path / "driver.js"
    drv.write_text(
        "var I = FluBNFPlayer._internals;\n"
        "print(JSON.stringify(I.offeredModels(" + json.dumps(have) + ")));\n")
    out = subprocess.run([str(JSC), str(PLAYER), str(drv)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr or out.stdout
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_jsc
@pytest.mark.parametrize("have,want", [
    ({"pf": 1, "analogue": 1, "ensemble": 1}, ["pf", "analogue"]),
    ({"ensemble": 1, "analogue": 1}, ["analogue"]),
    ({"pf": 1, "pf2s": 1, "ensemble": 1}, ["pf", "pf2s"]),
    ({"ensemble": 1}, []),
    ({"pf": 1, "analogue": 1}, ["pf", "analogue"]),
    ({}, []),
])
def test_the_player_never_offers_the_blend_beside_a_live_model(tmp_path, have,
                                                              want):
    assert _offered(tmp_path, have) == want


def test_the_player_and_the_pages_name_the_same_retired_models():
    src = PLAYER.read_text(encoding="utf-8")
    m = re.search(r"var RETIRED_MODELS = (\[[^\]]*\]);", src)
    assert m, "player.js no longer declares RETIRED_MODELS"
    assert tuple(json.loads(m.group(1).replace("'", '"'))) \
        == tuple(report_v2.RETIRED_MODELS)


def test_the_player_builds_its_checkboxes_from_offered_models():
    src = PLAYER.read_text(encoding="utf-8")
    assert "var ours = offeredModels(have);" in src
    assert "['pf', 'analogue', 'pf2s', 'ensemble']" not in src
