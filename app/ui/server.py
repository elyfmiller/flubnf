"""FastAPI operations console: the app, assembled from the tab routers.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710

This module only assembles the console, in this order: the app and its
/static mount; the middleware (the CSRF guard, the sandbox engine guard
around it, and the slow-request log outermost); the tab routers; the sandbox_storage Jinja global;
datasets_ui's router, last, and the dataset_upload_mb global; then the
startup warm pass, started last. Its public names are app, templates,
VERSIONS and RUNNING_SHA (app/core/site_build.py reads the last three
here); every other name lives in the module that defines it.

The modules, the rules between them and the route map: app/ui/README.md.
"""
from __future__ import annotations

import time
import sys
from pathlib import Path

from app.ui import state

sys.path.insert(0, str(state.REPO))
state._trace("import begin (fastapi + app.core next)")

from fastapi import FastAPI                                     # noqa: E402

from app.ui import perflog, shared, templating, versions        # noqa: E402
from app.ui.routes import data as data_routes                   # noqa: E402
from app.ui.routes import forecast as forecast_routes           # noqa: E402
from app.ui.routes import home as home_routes                   # noqa: E402
from app.ui.routes import methods as methods_routes             # noqa: E402
from app.ui.routes import models as models_routes               # noqa: E402
from app.ui.routes import output as output_routes               # noqa: E402
from app.ui.routes import retro as retro_routes                 # noqa: E402
from app.ui.routes import sandbox as sandbox_routes             # noqa: E402
from app.ui.routes import shell as shell_routes                 # noqa: E402
from app.ui.routes import storage as storage_routes             # noqa: E402
from app.ui.templating import templates                         # noqa: E402
from app.ui.versions import RUNNING_SHA, VERSIONS               # noqa: E402

# === Bootstrap: app, static mount, middleware, the tab routers ===
app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
# the same-host (CSRF) guard first: the sandbox engine guard, added next,
# wraps it (Starlette puts the last-added middleware outermost)
app.middleware("http")(shared._same_host_guard)
app.middleware("http")(sandbox_routes._sandbox_engine_guard)
# outermost: the slow-request log times everything, guards included
app.middleware("http")(perflog.slow_request_log)
# the tab routers. Order matters only where one path reaches two routes:
# storage before forecast, so POST /runs/clear precedes GET /runs/{run_id}
# (the first route a path matches names the Allow header of a wrong-method
# request); datasets_ui's router comes after every tab (below)
app.include_router(shell_routes.router)
app.include_router(home_routes.router)
app.include_router(data_routes.router)
app.include_router(storage_routes.router)
app.include_router(forecast_routes.router)
app.include_router(output_routes.router)
app.include_router(sandbox_routes.router)
app.include_router(models_routes.router)
app.include_router(methods_routes.router)
app.include_router(retro_routes.router)
# the Storage panel's read-only sandbox line (a tab's own Jinja global)
templates.env.globals["sandbox_storage"] = sandbox_routes._sandbox_storage_line


# === Startup warm (the version probe itself: app/ui/versions.py) ===
def _start_background_warm() -> None:
    """Daemon thread started at import: version probe, home template and
    outlook (always, since even the empty silhouette pays the science
    imports), latest vintage frame and report modules. Best-effort: never
    delays the first request, failures are silent."""
    import threading

    def _warm():
        t0 = time.perf_counter()
        state._trace("warm: thread begin (versions probe)")
        versions._warm_versions()
        state._trace(
            f"warm: versions done at +{time.perf_counter() - t0:.2f}s")
        try:
            # compile once, here
            templating.templates.env.get_template("home.html")
        except Exception:
            pass
        state._trace(
            f"warm: template done at +{time.perf_counter() - t0:.2f}s")
        try:
            rid, _res = shared._latest_results()
            home_routes._outlook_block(rid)
        except Exception:
            pass
        finally:
            state._WARM_DONE.set()
        state._trace(
            f"warm: outlook done at +{time.perf_counter() - t0:.2f}s")
        # pre-fill the latest vintage frame for the Forecast tab's first click
        try:
            vs = state.data_mod.vintages()
            if vs:
                data_routes._vintage_frame(
                    str(state.data_mod.vintage_path(vs[-1])))
            templating.templates.env.get_template("forecast.html")
            # model-name/color maps ride the report modules (~0.6 s import)
            from app.core import report_season, report_v2   # noqa: F401
        except Exception:
            pass
        state._trace(
            f"warm: forecast done at +{time.perf_counter() - t0:.2f}s")

    threading.Thread(target=_warm, daemon=True,
                     name="flubnf-startup-warm").start()


# === Custom datasets: upload, browse, forecast, replay (app/ui/datasets_ui.py) ===
from app.ui import datasets_ui as _datasets_ui              # noqa: E402
app.include_router(_datasets_ui.router)
# the upload box's size limit, wherever the box is placed
templates.env.globals["dataset_upload_mb"] = _datasets_ui.max_mb


# === Public names (app/core/site_build.py reads the last three here) ===
__all__ = ["app", "templates", "VERSIONS", "RUNNING_SHA"]


# === Startup warm (LAST, so every function it reaches is defined) ===
state._trace("import complete, starting background warm")
_start_background_warm()
