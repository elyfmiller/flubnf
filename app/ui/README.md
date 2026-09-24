# app/ui/: the console (FastAPI server, Jinja pages, static assets)

The console is one FastAPI app, rendered on the server from the Jinja templates in `templates/` (no build chain). `server.py` assembles it and is what uvicorn serves (`app.ui.server:app`, which `flubnf app` runs). Each nav tab's routes live in its own module in `routes/`, the custom-dataset routes in `datasets_ui.py`, and what two or more tabs share in the support modules beside `server.py`. This page lists the modules and the rules between them, then maps each route to its module, handler, template and caller.

## Modules

One line per module. "Imports" names the app/ui modules a module imports at top level: they form layers, from `state.py` (stdlib only) up to `server.py`, with no cycles.

| Module | Holds | Imports |
|---|---|---|
| **Assembly** | | |
| `server.py` | builds the app, in this order: `app` and the `/static` mount; the middleware (the same-host guard, then the sandbox engine guard, which wraps it); the tab routers, in the order of the **Tabs** rows below; the `sandbox_storage` Jinja global; `datasets_ui.py`'s router, last, and the `dataset_upload_mb` global; then the startup warm thread (`_start_background_warm`: version probe, home template and outlook, latest vintage frame, report modules), started last. Its public names are `app`, `templates`, `VERSIONS` and `RUNNING_SHA` (`app/core/site_build.py` reads the last three there) | every module here |
| **Support** (`app/ui/`) | | |
| `state.py` | `REPO` and `UI_DIR`; the startup trace (`_trace`, on `FLUBNF_STARTUP_TRACE`); `ENGINES`; `_status` (flash, log, phase, the run claim), `_last_form`, `_engine_lock`, `_WARM_DONE`, `_sandbox_status`; `data_mod` (`app.core.data`, loaded on first use) | none (stdlib only) |
| `versions.py` | the build SHA (`RUNNING_SHA`) and restart banner; component versions (`VERSIONS`, probed by `_warm_versions`); the engine versions a run records | none |
| `templating.py` | `templates`, the one Jinja env, with its globals and filters; model names and colors; the season month axis; the harmonic figure | `state`, `versions` |
| `shared.py` | the same-host (CSRF) guard; request helpers (`_flash`, `_back`, `_phase`, `_console_elapsed`); the cached disk scans and their one invalidation hook; run labels, outcome chips, `_latest_results`; the readers of the sandbox's engine claim | `state` |
| `forms.py` | the model-settings (knob) form channel and field coercions; anchor dates (`resolve_anchor`) | `state` |
| `retro_seasons.py` | the retro roots (`RETRO_ROOT`, `RETRO_RESEAL`, `RETRO_SEAL`) and season claims; the season registry and status; completed weeks; live progress and ETA | `templating` |
| `retro_prep.py` | season results preparation (one finalize job per root); the scores and relWIS caches; week map cards | `state`, `shared`, `retro_seasons` |
| `pipeline.py` | the forecast pipeline `_run_all` (engines, submissions, scoring, weekly report, forecast archive); the OS sleep guard | `state`, `shared`, `forms`, `versions` |
| **Tabs** (`routes/`, each an APIRouter, included in this order) | | |
| `routes/shell.py` | no tab: the endpoints `base.html` itself uses (versions poller, favicon, busy guard) | support modules |
| `routes/home.py` | Home: the outlook and its cache, cold-start readiness (`home.html`) | support modules |
| `routes/data.py` | Data: the TTL-cached vintage readers, `_data_context` (also `datasets_ui.py`'s), hub pull, freshness (`data.html`) | support modules |
| `routes/storage.py` | Storage: the disk inventory, the ledger, delete, clear and reclaim (`runs.html`) | support modules |
| `routes/forecast.py` | Forecast: POST `/run` and the builders of its spec, stop, the progress and series APIs, the run pages (`forecast.html`, `run.html`) | support modules, `routes/data.py`, `routes/output.py` |
| `routes/output.py` | Output: the submission files and their download rules, the weekly report, served as stored or rebuilt (`output.html`) | support modules |
| `routes/sandbox.py` | Sandbox (`sandbox.html`), with the sandbox engine guard (middleware) and the Storage panel's sandbox line (`sandbox_storage`) | support modules |
| `routes/models.py` | Models (`model.html`) | support modules |
| `routes/methods.py` | Methods (`methods.html`) | support modules |
| `routes/retro.py` | Retrospective: the index and its APIs, the run controls and the season worker (`_retro_bg`), the season page with its playback, map swap and report APIs (`retro.html`, `retro_season.html`) | support modules |
| **Custom datasets** | | |
| `datasets_ui.py` | upload, browse, forecast and replay a dataset; an APIRouter included last. Data, Forecast and `/api/series` hand it `?source=<id>`, `/retro` `?dataset=<id>` | support modules, `routes/data.py`, `routes/storage.py` |

## Rules between the modules

`app/tests/test_ui_layout.py` checks each of these.

- **One home per name.** Every object is defined in exactly one module. Containers, locks and events (`_status`, `_engine_lock`, `VERSIONS`, `templates`, ...) are changed in place, never rebound, so another module may import them by name (`from app.ui.state import _status`) and holds the same object.
- **A patched or rebound name is read through its owner.** `data_mod` rebinds itself on first use, and the tests patch the retro roots, `_known_seasons`, `_latest_results`, `_run_all`, `_sleep_guard` and others. Every module but the owner reads such a name as `owner.X` at call time (`state.data_mod`, `retro_seasons.RETRO_ROOT`, `pipeline._run_all`), never through a from-import, whose copy a patch would miss. The tests patch the owner, with `raising` left on: `monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp)`.
- **Imports point down the layers.** No module imports `server.py` or `datasets_ui.py` at top level: a tab that hands a request to `datasets_ui.py` imports it inside the function. No tab module imports another, except `routes/forecast.py`, which reads a run's vintage, files and report from `routes/data.py` and `routes/output.py`. `server.py` imports with `from ... import x as x_routes` only: `import app.ui.x` would rebind its name `app` to the package.
- **No alias is shadowed.** No module alias is rebound in its file: `datasets_ui.py` imports `state` as `ui_state`, because its workers bind a local `state`.
- **Paths.** The support modules sit in `app/ui/` and compute their paths from `__file__`; the tab modules sit one directory deeper, so they use `state.REPO` and `state.UI_DIR` and never their own `__file__`.
- **Order.** The same-host guard is added first and the sandbox guard second (Starlette puts the last one outermost). No two routes serve one concrete path with the same method, but the first route a path matches names the `Allow` header of a wrong-method request: so `routes/storage.py` is included before `routes/forecast.py` (POST `/runs/clear` before GET `/runs/{run_id}`), `routes/retro.py` keeps POST `/retro/stop` and `/retro/run` above GET `/retro/{season}`, and `datasets_ui.py` comes last. The warm thread starts at import, last, and only from `server.py`.
- **Annotations.** Every module has `from __future__ import annotations`, so FastAPI resolves a handler's `Request`, `Form` or `BackgroundTasks` from the module's globals: each module imports what its handlers name (`ruff check --select F821` flags a missing one).

## Routes by console tab

"Caller" is the template or script that fetches, posts or links to the route. `base.html` is the shell every page extends.

| Method | Path | Module | Handler | Template | Caller |
|---|---|---|---|---|---|
| **Home** | | | | | |
| GET | `/` | `routes/home.py` | `home` | `home.html` | nav |
| GET | `/api/outlook-ready` | `routes/home.py` | `api_outlook_ready` | | `home.html` poll |
| **Data** | | | | | |
| GET | `/data` | `routes/data.py` | `data_page` (`?source=<dataset>`: `datasets_ui.data_context`) | `data.html` | nav; `data.html` vintage form |
| POST | `/data/datasets/check` | `datasets_ui.py` | `check` | JSON: the result box's HTML (`_dataset_check.html`), the inferred kind, the targets | `static/dataset_upload.js` |
| POST | `/data/datasets` | `datasets_ui.py` | `upload` | `data.html` (problems) or redirect to Data, Forecast or Retrospective (`next`) | `_dataset_upload.html` form (Data, Forecast, Retrospective) |
| POST | `/data/datasets/{id}/delete` | `datasets_ui.py` | `delete` | redirect | `_datasets_card.html` form |
| POST | `/data/pull` | `routes/data.py` | `data_pull` | redirect | `data.html` form |
| POST | `/freshness` | `routes/data.py` | `freshness` | `data.html` | `data.html` form |
| **Forecast** | | | | | |
| GET | `/forecast` | `routes/forecast.py` | `forecast_page` (`?source=<dataset>`: `datasets_ui.forecast_page`) | `forecast.html` | nav |
| POST | `/run/dataset` | `datasets_ui.py` | `run_dataset` | redirect | `forecast.html` `#fcform` with a dataset |
| POST | `/run` | `routes/forecast.py` | `run_models` | redirect | `forecast.html` `#fcform`, `model.html` form, `research_run.html` |
| POST | `/run/stop` | `routes/forecast.py` | `run_stop` | redirect | `forecast.html` form, `base.html` guard modal |
| GET | `/api/progress` | `routes/forecast.py` | `api_progress` | | `forecast.html` progress poll |
| GET | `/api/series` | `routes/forecast.py` | `api_series` (`source=<dataset>`: `datasets_ui.api_series`) | | `forecast.html`, `model.html` charts |
| GET | `/runs/{run_id}` | `routes/forecast.py` | `run_page` | `run.html` | links in `forecast.html`, `runs.html` |
| GET | `/runs/{run_id}/report` | `routes/forecast.py` | `run_report` | the run's `report.html` | `forecast.html`, `run.html` |
| GET | `/runs/{run_id}/report/download` | `routes/forecast.py` | `run_report_download` | | `run.html` |
| POST | `/runs/{run_id}/rerun` | `routes/forecast.py` | `run_rerun` | | `forecast.html`, `run.html` forms |
| **Output** | | | | | |
| GET | `/output` | `routes/output.py` | `output_page` | `output.html` | nav |
| GET | `/output/download` | `routes/output.py` | `output_download` | file | `output.html`, `run.html` |
| POST | `/output/reveal` | `routes/output.py` | `output_reveal` | redirect | `output.html` form, `retro_season.html` fetch |
| GET | `/output/report` | `routes/output.py` | `output_report` | weekly report | `output.html` link and date picker |
| GET | `/output/report/download` | `routes/output.py` | `output_report_download` | | `output.html` |
| **Retrospective** | | | | | |
| GET | `/retro` | `routes/retro.py` | `retro_index` (two tabs: the FluSight hub, or Your data: `?tab=own` opens the first dataset, `?dataset=<id>` that one) | `retro.html` | nav; the upload box's "Replay this" |
| POST | `/retro/run` | `routes/retro.py` | `retro_run` | redirect | `retro.html` start and resume forms |
| POST | `/retro/stop` | `routes/retro.py` | `retro_stop` | redirect | `base.html` guard modal |
| POST | `/retro/{season}/stop`, `/pause`, `/resume` | `routes/retro.py` | `retro_season_stop`, `_pause`, `_resume` | | `retro.html`, `retro_season.html` forms |
| POST | `/retro/{season}/archive/{stamp}/delete` | `routes/retro.py` | `retro_archive_delete` | | `retro.html` form |
| GET | `/api/retro/progress` | `routes/retro.py` | `api_retro_progress` | | `static/retro_progress.js` |
| GET | `/api/retro/startover` | `routes/retro.py` | `api_retro_startover` | | `base.html` start-over modal |
| GET | `/retro/{season}` | `routes/retro.py` | `retro_results` | `retro_season.html` | `retro.html` links |
| GET | `/api/retro/{season}/results_status` | `routes/retro.py` | `api_retro_results_status` | | `retro_season.html` preparing poll |
| GET | `/api/retro/{season}/playback/{asof}` | `routes/retro.py` | `api_retro_playback` | | `retro_season.html` player host (`static/player.js`) |
| GET | `/api/retro/{season}/mapswap/{asof}` | `routes/retro.py` | `api_retro_mapswap` | | `retro_season.html` map swap |
| GET | `/retro/{season}/report` | `routes/retro.py` | `retro_season_report` | file (`app/core/report_season.py`) | `retro_season.html` download link |
| GET | `/api/retro/{season}/report_path` | `routes/retro.py` | `api_retro_report_path` | | `retro_season.html` reveal button |
| POST | `/retro/dataset/run` | `datasets_ui.py` | `replay_start` | redirect | `_dataset_replay.html` form |
| GET | `/retro/dataset/{id}/{stamp}` | `datasets_ui.py` | `replay_page` | `retro_dataset.html` | `_dataset_replay.html` links |
| POST | `/retro/dataset/{id}/{stamp}/stop` | `datasets_ui.py` | `replay_stop` | redirect | `retro_dataset.html` form |
| **Storage** | | | | | |
| GET | `/storage`, `/runs` | `routes/storage.py` | `runs_page` | `runs.html` | nav |
| GET | `/api/storage/reclaim` | `routes/storage.py` | `api_storage_reclaim` | | `runs.html` fetch |
| POST | `/storage/reclaim` | `routes/storage.py` | `storage_reclaim` | | `runs.html` `#reclaim-form` |
| POST | `/storage/delete` | `routes/storage.py` | `storage_delete` | | `runs.html` forms |
| POST | `/storage/clear-workroots` | `routes/storage.py` | `storage_clear_workroots` | | `runs.html` `#clear-workroots` |
| POST | `/storage/datasets/{id}/delete` | `datasets_ui.py` | `storage_delete` (the dataset, its replays and its runs' workroots; the name confirms) | redirect | `runs.html` Your datasets forms |
| POST | `/runs/clear` | `routes/storage.py` | `runs_clear` | | `runs.html` `#clear-ledger` |
| **Models** | | | | | |
| GET | `/models` | `routes/models.py` | `models_page` (calls `model_page`) | `model.html` | nav |
| GET | `/model/{name}` | `routes/models.py` | `model_page` | `model.html` | `methods.html` links; `pf2s` is research only |
| **Methods** | | | | | |
| GET | `/methods` | `routes/methods.py` | `methods_page` | `methods.html` | nav |
| **Sandbox** | | | | | |
| GET | `/sandbox` (`?model=`, `?run=`, `?dataset=`, `?compare=`) | `routes/sandbox.py` | `sandbox_page` | `sandbox.html` (gallery, or one model's workbench) | nav |
| POST | `/sandbox/new` (`start=skeleton\|example:<n>\|copy:<m>\|shipped:sihrs\|shipped:dataset:<id>`), `/sandbox/add-example` (alias) | `routes/sandbox.py` | `sandbox_new`, `sandbox_add_example` | redirect | `sandbox.html` forms |
| POST | `/sandbox/models/{name}/save`, `/run` (save, then run), `/delete` | `routes/sandbox.py` | `sandbox_save`, `sandbox_model_run`, `sandbox_delete_model` | redirect | `sandbox.html` workbench form |
| POST | `/sandbox/models/{name}/fill-data`, `/upload-data` (multipart, size-capped) | `routes/sandbox.py` | `sandbox_fill_data`, `sandbox_upload_data` | redirect | `sandbox_data.html` (`formaction`) |
| POST | `/sandbox/run` (alias) | `routes/sandbox.py` | `sandbox_run` | redirect | scripts |
| POST | `/sandbox/runs/{run_id}/stop`, `/delete`; `/sandbox/stop` | `routes/sandbox.py` | `sandbox_run_stop`, `sandbox_delete_run`, `sandbox_stop` | redirect | results card; the guard modal |
| POST | `/sandbox/runs/{run_id}/oracle` (the Oracle step on an unedited Oracle SIHRS start; sandbox only) | `routes/sandbox.py` | `sandbox_run_oracle` | redirect | results card |
| GET | `/sandbox/models/{name}/download`, `/sandbox/runs/{run_id}/download` (localhost Host only) | `routes/sandbox.py` | `sandbox_model_download`, `sandbox_run_download` | zip | workbench |
| POST | `/api/sandbox/models/{name}/check` | `routes/sandbox.py` | `api_sandbox_check` | JSON | `static/sandbox.js` |
| GET | `/api/sandbox/models/{name}/contactmap`, `/network` | `routes/sandbox.py` | `api_sandbox_contactmap`, `api_sandbox_network` | | `sandbox_views.html` (drawn by `static/model-views.js`; cached by the model text) |
| GET | `/api/sandbox/runs/{run_id}` | `routes/sandbox.py` | `api_sandbox_run` | | `static/sandbox.js` poll |
| **Shell** (no tab: the endpoints `base.html` itself uses) | | | | | |
| GET | `/api/versions` | `routes/shell.py` | `api_versions` | | `base.html` versions poller |
| GET | `/favicon.ico` | `routes/shell.py` | `favicon` | | `base.html` |
| GET | `/api/busy` | `routes/shell.py` | `api_busy` | | `base.html` guard modal |

## Partials and macros (not pages)

| Template | Included by |
|---|---|
| `base.html` | extended by every page: nav, theme and a11y pickers, guard and start-over modals |
| `diagrams.html` | imported as `dg` by `home.html`, `methods.html`, `model.html`, and `app/core/site_build.py` |
| `research_run.html` | `base.html`, only on `/model/pf2s` (`research_panel`) |
| `sandbox_views.html` | `sandbox.html`; loads `static/model-views.js` and `.css` |
| `sandbox_data.html` | `sandbox.html`, inside the editor's save form |
| `_datasets_card.html` | `data.html` (Your datasets: the upload box and the list) |
| `_dataset_upload.html` | the upload box: `_datasets_card.html`, `forecast.html`, `_dataset_replay.html`; loads `static/dataset_upload.js` |
| `_dataset_check.html` | the upload box's result (problems, column mapping, preview): `_dataset_upload.html`, and `datasets_ui.render_check` for `/data/datasets/check` |
| `_dataset_run.html` | `run.html`, for a run on a custom dataset (fans, export files) |
| `_dataset_replay.html` | `retro.html` (the Your data tab: the upload box, or a dataset's replay settings and its replays) |
| `_model_settings.html` | the Model settings panel: `forecast.html`, `retro.html`, and `_dataset_replay.html` (on the Your data tab: `datasets_ui.dataset_panel`, ids prefixed `dsr-`); loads `static/model_settings.js` |
| `_tips.html` | macros for the "?" tips, imported by most pages (`base.html` loads `static/tips.js`) |

Template names that differ from their tab: `runs.html` is Storage, `run.html` is one run's page, `model.html` is Models.

## Static (`static/`)

| File | Loaded by |
|---|---|
| `nau.css` | `base.html` (every page); its token blocks are embedded by `app/core/report_v2.py` and `report_season.py` |
| `player.js` | `retro_season.html`; inlined by `report_season.py`; its name and color maps are parsed by `templating.py` and the reports |
| `retro_progress.js` | `retro.html`, `retro_season.html` |
| `quips.js` | `forecast.html`, `retro.html`, `retro_season.html` |
| `plotly.min.js` | `data.html`, `forecast.html`, `model.html`, `retro_season.html`, `retro_dataset.html`, `run.html` (dataset runs), `sandbox.html` |
| `dataset-template.csv` | `_dataset_upload.html` download link (FluBNF's synthetic grouped-CSV template: three groups, Overall the sum, with populations) |
| `dataset_upload.js` | `_dataset_upload.html` (drop or choose one file, several or a folder of snapshots, check at once, recheck on kind/target/column changes) |
| `model_settings.js` | `_model_settings.html` (every panel on the page, each set up once: badge, engine and kind filters, reset, the override's reason) |
| `bngl-editor.js`, `bngl-editor.css`, `sandbox.js` | `sandbox.html` |
| `model-views.js`, `model-views.css` | `sandbox_views.html` |
| `brand/`, `fonts/` | `base.html`, `home.html`, `/favicon.ico` (icons); `base.html` (DM Sans) |
