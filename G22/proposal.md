# G22 error-pages: proposal (B)
Base: origin/dev 8cb3f7d

Reproduced on a server from dev (FLUBNF_STATE_DIR, the G20/G21 run state),
with curl for the codes and bodies and Chromium at 1280 and 390 px for the
pages. No run path; no invariance check.

## UI-10 (also: MO-11, WI-14)
- Reproduced: yes. /model/nope: 404, the 13-byte text "unknown model".
  /nope: 404 application/json {"detail":"Not Found"}. WI-14's others:
  /retro/dataset/nope/<stamp>: 404 "<p>No such replay.</p>";
  /retro/2097-98/report: 404 text/plain "2097-98: no completed weeks yet,
  so there is no season report to build."
- Root cause: routes/models.py answers an unknown name with a bare
  HTMLResponse; the app has no handler for Starlette's 404, so an unmatched
  path gets FastAPI's JSON; datasets_ui.replay_page and
  retro.retro_season_report answer with bare text.
- Fix: one handler, `routes/shell.not_found_page`, registered in server.py
  with `app.add_exception_handler` (server.py keeps only its assembly
  names, as test_ui_layout pins): a 404 off `/api/` and `/static/` is the
  console's notice page (routes/output._notice, as /runs/nope is): heading
  "Not found", "No page at this address", Open Home, no tab current; API
  paths and static files keep the plain answer their callers read, and
  every other status keeps FastAPI's. /model/<unknown>: the same notice
  under Models ("No model named nope", Open Models). The replay page: "No
  such replay" under Retrospective, the way to the dataset's replays (or
  /retro when the dataset is unknown). /retro/<season>/report: the
  helper's refusal text (unchanged words, its status) as a notice under
  Retrospective with "Open the season"; `_season_report` itself keeps its
  signature and plain answers (tests repoint it; /api/retro/<season>/
  report_path, the results page's Reveal, stays plain). No tips: the title
  and the button are the page.
- Tests: test_error_pages.py
  `test_an_unknown_address_is_a_console_page_with_the_way_home`,
  `test_an_unknown_model_is_a_console_page_under_models`,
  `test_an_unknown_replay_or_season_report_is_a_console_page`.
- Risk: any client that read the JSON 404 for a non-API page (none in the
  console: every fetch is under /api/); the test_browse_safety walk and
  the no-store middleware cover the new pages (the notice is a normal
  response).
- For Ely: none

## OU-16
- Reproduced: yes. GET /output/download with no path and POST
  /output/reveal with no path: 422 application/json. /output/report?date=
  2026-13-45: 200 "No archived report for 2026-13-45". A missing archive:
  the view 200, its download 404.
- Root cause: `path` is required on both routes (FastAPI's 422);
  `_bad_date` checks the shape only; the view's missing-archive notice is
  a 200.
- Fix: `path` defaults to "" on both: the download's existing checks give
  the 404 notice; reveal treats no path as nothing to open (never the
  working folder "" would resolve to) and flashes as for a missing file.
  `_bad_date` parses with date.fromisoformat after the shape check, so
  2026-13-45 is "Invalid date" (400) on the view and the download. The
  missing-archive view answers 404 as its download does;
  test_output_by_date's pin of the 200 is updated (the bug names it) and
  now also checks the download agrees.
- Tests: `test_malformed_output_requests_get_the_console_notice`.
- Risk: the view's status for a missing archive (200 -> 404) is the one
  behavior change; Home's and Output's links never point at a missing
  archive.
- For Ely: none

## SB-16
- Reproduced: yes. New model del_me, Delete, then /sandbox?model=del_me:
  "Not opened: model 'del_me' is missing model.bngl, data.exp,
  priors.conf".
- Root cause: sandbox.model_dir lists the required files of a folder that
  is not there.
- Fix: model_dir raises SandboxError("no sandbox model named 'del_me'")
  when the folder is absent, before the file check; the page's `_not_done`
  flashes "Not opened: no sandbox model named 'del_me'". A folder that
  lost a file still names the file. Every caller of model_dir (open, save,
  run, register, download) gives the same sentence for a gone model.
- Tests: `test_a_deleted_sandbox_model_is_said_to_be_gone`.
- Risk: the Sandbox's own wording only.
- For Ely: none

## Patch
G22/proposal.patch (git diff origin/dev...proto/G22-B): server.py (one
add_exception_handler line), routes/shell.py (not_found_page),
routes/models.py, datasets_ui.py, routes/retro.py (the report route),
routes/output.py, core/sandbox.py, test_output_by_date.py (the pin),
app/tests/test_error_pages.py (5 tests). Targeted suites (test_output_*,
test_run_labels_deleted, test_datasets_ui, test_browse_safety,
test_download_headers, test_server_hardening, test_sandbox,
test_ui_layout): 125 passed. Full suite (FLUBNF_HUB=/nonexistent): 4205 passed, 159 skipped, the two test_doctor failures of this container's Python. ruff clean. Windows:
no path or encoding change.
