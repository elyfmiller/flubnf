"""One Host guard: the global middleware (app/ui/shared._same_host_guard).

The dataset routes (datasets_ui.local_only) and the sandbox downloads
(routes/sandbox) repeated its Host check; the duplicates are gone, and the
behaviour is unchanged: a foreign Host is refused on every one of those
routes (by the middleware, with its words), a localhost Host is served,
and the sandbox downloads still refuse a foreign Origin on a GET (the one
check the middleware does not make for GETs)."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                              # noqa: E402
from fastapi.testclient import TestClient                  # noqa: E402

from app.ui import datasets_ui as DU                       # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui.routes import sandbox as sbr                   # noqa: E402

client = TestClient(srv.app)
FOREIGN = {"host": "rebind.example"}
HOST_WORDS = "Refused: the Host header does not name localhost."


def test_no_route_repeats_the_middlewares_host_check():
    import app.ui.routes.data as data_routes
    import app.ui.routes.forecast as fc_routes
    reads_host = 'headers.get("host"'
    assert reads_host not in inspect.getsource(DU)
    for fn in (sbr._sandbox_same_origin_get, sbr.sandbox_model_download,
               sbr.sandbox_run_download):
        assert reads_host not in inspect.getsource(fn), fn
    assert not hasattr(sbr, "_sandbox_local_get")
    # the dataset routes no longer call the (now empty) shim
    for mod in (DU, data_routes, fc_routes):
        assert "local_only(request)" not in inspect.getsource(mod), mod


@pytest.mark.parametrize("method, url", [
    ("get", "/data?source=ds-x"),
    ("get", "/api/series?source=ds-x&locs=Adult"),
    ("get", "/forecast?source=ds-x"),
    ("get", "/runs/20980103T000000-abcdef"),
    ("get", "/retro/dataset/ds-x/20260101T000000Z"),
    ("post", "/data/datasets/check"),
    ("get", "/sandbox/models/kinetics_example/download"),
    ("get", "/sandbox/runs/sb-run-1/download"),
])
def test_a_foreign_host_is_refused_on_every_formerly_guarded_route(method,
                                                                   url):
    r = getattr(client, method)(url, headers=FOREIGN)
    assert r.status_code == 403 and HOST_WORDS in r.text, url


def test_sandbox_downloads_keep_their_origin_check(sandbox_root):
    from app.core import sandbox as sb
    sb.new_model("mine")
    url = "/sandbox/models/mine/download"
    assert client.get(url).status_code == 200
    assert client.get(url, headers={"origin": "http://localhost:8710"}
                      ).status_code == 200
    for origin in ("http://evil.example", "null"):
        r = client.get(url, headers={"origin": origin})
        assert r.status_code == 403, origin
        assert "not a localhost request" in r.text
