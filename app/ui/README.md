# app/ui/: the console (FastAPI server, Jinja pages, static assets)

Every route lives in `server.py`, grouped under `# === <Tab> ===` banners, except the custom-dataset routes, which live in `datasets_ui.py` (an APIRouter `server.py` includes); this page maps each route to its handler, template and caller.

## Routes by console tab

"Caller" is the template or script that fetches, posts or links to the route. `base.html` is the shell every page extends.

| Method | Path | Handler | Template | Caller |
|---|---|---|---|---|
| **Home** | | | | |
| GET | `/` | `home` | `home.html` | nav |
| GET | `/api/outlook-ready` | `api_outlook_ready` | | `home.html` poll |
| GET | `/api/versions` | `api_versions` | | `base.html` versions poller |
| GET | `/favicon.ico` | `favicon` | | `base.html` |
| **Data** | | | | |
| GET | `/data` | `data_page` (`?source=<dataset>`: `datasets_ui.data_context`) | `data.html` | nav; `data.html` vintage form |
| POST | `/data/datasets/check` | `datasets_ui.check` | JSON: the result box's HTML (`_dataset_check.html`), the inferred kind, the targets | `static/dataset_upload.js` |
| POST | `/data/datasets` | `datasets_ui.upload` | `data.html` (problems) or redirect to Data, Forecast or Retrospective (`next`) | `_dataset_upload.html` form (Data, Forecast, Retrospective) |
| POST | `/data/datasets/{id}/delete` | `datasets_ui.delete` | redirect | `_datasets_card.html` form |
| POST | `/data/pull` | `data_pull` | redirect | `data.html` form |
| POST | `/freshness` | `freshness` | `data.html` | `data.html` form |
| **Forecast** | | | | |
| GET | `/forecast` | `forecast_page` (`?source=<dataset>`: `datasets_ui.forecast_page`) | `forecast.html` | nav |
| POST | `/run/dataset` | `datasets_ui.run_dataset` | redirect | `forecast.html` `#fcform` with a dataset |
| POST | `/run` | `run_models` | redirect | `forecast.html` `#fcform`, `model.html` form, `research_run.html` |
| POST | `/run/stop` | `run_stop` | redirect | `forecast.html` form, `base.html` guard modal |
| GET | `/api/progress` | `api_progress` | | `forecast.html` progress poll |
| GET | `/api/series` | `api_series` (`source=<dataset>`: `datasets_ui.api_series`) | | `forecast.html`, `model.html` charts |
| GET | `/runs/{run_id}` | `run_page` | `run.html` | links in `forecast.html`, `runs.html` |
| GET | `/runs/{run_id}/report` | `run_report` | the run's `report.html` | `forecast.html`, `run.html` |
| GET | `/runs/{run_id}/report/download` | `run_report_download` | | `run.html` |
| POST | `/runs/{run_id}/rerun` | `run_rerun` | | `forecast.html`, `run.html` forms |
| **Output** | | | | |
| GET | `/output` | `output_page` | `output.html` | nav |
| GET | `/output/download` | `output_download` | file | `output.html`, `run.html` |
| POST | `/output/reveal` | `output_reveal` | redirect | `output.html` form, `retro_season.html` fetch |
| GET | `/output/report` | `output_report` | weekly report | `output.html` link and date picker |
| GET | `/output/report/download` | `output_report_download` | | `output.html` |
| **Retrospective** | | | | |
| GET | `/retro` | `retro_index` (`?dataset=<id>`: the replay card opens on it) | `retro.html` | nav; the upload box's "Replay this" |
| POST | `/retro/run` | `retro_run` | redirect | `retro.html` start and resume forms |
| POST | `/retro/stop` | `retro_stop` | redirect | `base.html` guard modal |
| POST | `/retro/{season}/stop`, `/pause`, `/resume` | `retro_season_stop`, `_pause`, `_resume` | | `retro.html`, `retro_season.html` forms |
| POST | `/retro/{season}/archive/{stamp}/delete` | `retro_archive_delete` | | `retro.html` form |
| GET | `/api/retro/progress` | `api_retro_progress` | | `static/retro_progress.js` |
| GET | `/api/retro/startover` | `api_retro_startover` | | `base.html` start-over modal |
| GET | `/retro/{season}` | `retro_results` | `retro_season.html` | `retro.html` links |
| GET | `/api/retro/{season}/results_status` | `api_retro_results_status` | | `retro_season.html` preparing poll |
| GET | `/api/retro/{season}/playback/{asof}` | `api_retro_playback` | | `retro_season.html` player host (`static/player.js`) |
| GET | `/api/retro/{season}/mapswap/{asof}` | `api_retro_mapswap` | | `retro_season.html` map swap |
| GET | `/retro/{season}/report` | `retro_season_report` | file (`app/core/report_season.py`) | `retro_season.html` download link |
| GET | `/api/retro/{season}/report_path` | `api_retro_report_path` | | `retro_season.html` reveal button |
| POST | `/retro/dataset/run` | `datasets_ui.replay_start` | redirect | `_dataset_replay.html` form |
| GET | `/retro/dataset/{id}/{stamp}` | `datasets_ui.replay_page` | `retro_dataset.html` | `_dataset_replay.html` links |
| POST | `/retro/dataset/{id}/{stamp}/stop` | `datasets_ui.replay_stop` | redirect | `retro_dataset.html` form |
| **Storage** | | | | |
| GET | `/storage`, `/runs` | `runs_page` | `runs.html` | nav |
| GET | `/api/storage/reclaim` | `api_storage_reclaim` | | `runs.html` fetch |
| POST | `/storage/reclaim` | `storage_reclaim` | | `runs.html` `#reclaim-form` |
| POST | `/storage/delete` | `storage_delete` | | `runs.html` forms |
| POST | `/storage/clear-workroots` | `storage_clear_workroots` | | `runs.html` `#clear-workroots` |
| POST | `/storage/datasets/{id}/delete` | `datasets_ui.storage_delete` (the dataset, its replays and its runs' workroots; the name confirms) | redirect | `runs.html` Your datasets forms |
| POST | `/runs/clear` | `runs_clear` | | `runs.html` `#clear-ledger` |
| **Models** | | | | |
| GET | `/models` | `models_page` (calls `model_page`) | `model.html` | nav |
| GET | `/model/{name}` | `model_page` | `model.html` | `methods.html` links; `pf2s` is research only |
| **Methods** | | | | |
| GET | `/methods` | `methods_page` | `methods.html` | nav |
| **Sandbox** | | | | |
| GET | `/sandbox` (`?model=`, `?run=`, `?dataset=`, `?compare=`) | `sandbox_page` | `sandbox.html` (gallery, or one model's workbench) | nav |
| POST | `/sandbox/new` (`start=skeleton\|example:<n>\|copy:<m>\|shipped:sihrs\|shipped:dataset:<id>`), `/sandbox/add-example` (alias) | `sandbox_new`, `sandbox_add_example` | redirect | `sandbox.html` forms |
| POST | `/sandbox/models/{name}/save`, `/run` (save, then run), `/delete` | `sandbox_save`, `sandbox_model_run`, `sandbox_delete_model` | redirect | `sandbox.html` workbench form |
| POST | `/sandbox/models/{name}/fill-data`, `/upload-data` (multipart, size-capped) | `sandbox_fill_data`, `sandbox_upload_data` | redirect | `sandbox_data.html` (`formaction`) |
| POST | `/sandbox/run` (alias) | `sandbox_run` | redirect | scripts |
| POST | `/sandbox/runs/{run_id}/stop`, `/delete`; `/sandbox/stop` | `sandbox_run_stop`, `sandbox_delete_run`, `sandbox_stop` | redirect | results card; the guard modal |
| POST | `/sandbox/runs/{run_id}/oracle` (the Oracle step on an unedited Oracle SIHRS start; sandbox only) | `sandbox_run_oracle` | redirect | results card |
| GET | `/sandbox/models/{name}/download`, `/sandbox/runs/{run_id}/download` (localhost Host only) | `sandbox_model_download`, `sandbox_run_download` | zip | workbench |
| POST | `/api/sandbox/models/{name}/check` | `api_sandbox_check` | JSON | `static/sandbox.js` |
| GET | `/api/sandbox/models/{name}/contactmap`, `/network` | `api_sandbox_contactmap`, `api_sandbox_network` | | `sandbox_views.html` (drawn by `static/model-views.js`; cached by the model text) |
| GET | `/api/sandbox/runs/{run_id}` | `api_sandbox_run` | | `static/sandbox.js` poll |
| **Shared** | | | | |
| GET | `/api/busy` | `api_busy` | | `base.html` guard modal |

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
| `_dataset_replay.html` | `retro.html` (Replay your own data) |
| `_model_settings.html` | the Model settings panel: `forecast.html`, `retro.html`, and `_dataset_replay.html` (a second panel on that page: `datasets_ui.dataset_panel`, ids prefixed `dsr-`); loads `static/model_settings.js` |
| `_tips.html` | macros for the "?" tips, imported by most pages (`base.html` loads `static/tips.js`) |

Template names that differ from their tab: `runs.html` is Storage, `run.html` is one run's page, `model.html` is Models.

## Static (`static/`)

| File | Loaded by |
|---|---|
| `nau.css` | `base.html` (every page); its token blocks are embedded by `app/core/report_v2.py` and `report_season.py` |
| `player.js` | `retro_season.html`; inlined by `report_season.py`; its name and color maps are parsed by server and reports |
| `retro_progress.js` | `retro.html`, `retro_season.html` |
| `quips.js` | `forecast.html`, `retro.html`, `retro_season.html` |
| `plotly.min.js` | `data.html`, `forecast.html`, `model.html`, `retro_season.html`, `retro_dataset.html`, `run.html` (dataset runs), `sandbox.html` |
| `dataset-template.csv` | `_dataset_upload.html` download link (FluBNF's synthetic grouped-CSV template: three groups, Overall the sum, with populations) |
| `dataset_upload.js` | `_dataset_upload.html` (drop or choose, check at once, recheck on kind/target/column changes) |
| `model_settings.js` | `_model_settings.html` (every panel on the page, each set up once: badge, engine and kind filters, reset, the override's reason) |
| `bngl-editor.js`, `bngl-editor.css`, `sandbox.js` | `sandbox.html` |
| `model-views.js`, `model-views.css` | `sandbox_views.html` |
| `brand/`, `fonts/` | `base.html`, `home.html`, `/favicon.ico` (icons); `base.html` (DM Sans) |
