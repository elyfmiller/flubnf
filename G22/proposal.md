# G22 error-pages: proposal (A)
Base: origin/dev 8cb3f7d

How: a dev server (8815) and a prototype server (8816), fresh state
folders; curl with a browser's Accept (text/html) and with a script's
(*/*); Chromium for the pages at 1280 and 390 px, light and dark.

## UI-10 (also: MO-11, WI-14)
- Reproduced: yes, on dev 8cb3f7d.
  - /model/nope: 404 text/html, body "unknown model" (13 bytes, no
    header, no way back).
  - /nope: 404 application/json {"detail":"Not Found"}.
  - WI-14: /retro/dataset/nope/20260101T000000Z: 404 "<p>No such
    replay.</p>"; /retro/2025-26/report with no completed weeks: 404
    text/plain "2025-26: no completed weeks yet, so there is no season
    report to build."
- Root cause: no 404 handler in server.py, so an unmatched path gets
  FastAPI's JSON; models.py:178, datasets_ui.py:1308 and retro.py's
  season report download return bare responses.
- Fix: one rule, Output's notice (`output._notice`, as /runs/nope uses):
  - an HTTPException handler, `output._not_found_page`, registered in
    server.py the way the middleware is: a 404 for a request that asks
    for HTML (the window, a browser) outside /api/ and /static/ is a
    notice, "No page at this address", heading "Not found", Back to
    Home. Anything else (a script's fetch, /api/, every other code) goes
    to FastAPI's own handler, so JSON callers see what they saw.
  - /model/nope: "No model named nope", Open Models, under Models.
  - an unknown replay: "No such replay", Open Retrospective.
  - the season report link: the reason it cannot be built, Back to the
    season (Open Retrospective for a malformed season), under
    Retrospective; a 503 (no truth file) is an error alert, a 404 empty.
    /api/retro/{season}/report_path keeps its plain text (a script reads
    it).
- After: each of the four answers a page of the console with the header
  and the way back; /nope and /api/nope with Accept */* still
  {"detail":"Not Found"}. Screenshots at 1280 light/dark and 390
  light/dark: no sideways scroll.
- Tests: test_error_pages.py
  `test_an_unknown_page_opened_in_the_window_is_a_console_page`,
  `test_an_unknown_model_or_replay_address_is_a_console_page`,
  `test_a_season_report_that_cannot_be_built_is_a_console_page`.
- Risk: the handler sees every HTTPException; it changes only a 404 a
  page navigation asked for. test_output_freshness's JS stub of a 404
  JSON body is a fetch, untouched. The handler lives in routes/output.py
  so server.py keeps only assembling (test_ui_layout's rule).
- For Ely: none

## OU-16 (also: none)
- Reproduced: yes.
  - GET /output/download with no path: 422 JSON {"detail":[{"type":
    "missing","loc":["query","path"]...}]}; POST /output/reveal with no
    path: the same 422.
  - /output/report?date=2026-13-45: 200 "No archived report for
    2026-13-45".
  - /output/report?date=2026-10-17 with no archive: 200; its
    /output/report/download: 404.
- Root cause: output.py's `path` parameters are required, so FastAPI's
  validation answers before the route; `_bad_date` checks the shape only;
  the missing-archive view returns `_notice(request, 200, ...)`.
- Fix: `path` defaults to "" in both; an empty path is the existing
  "File not found in app state" page (download) or the existing "Nothing
  opened: the file is not in app state any more." flash (reveal).
  `_bad_date` also needs `date.fromisoformat` to accept the day. The
  missing archive's view answers 404, as its download does.
- After: download 404 notice; reveal 303 back with the flash;
  2026-13-45 400 "Invalid date. Expected YYYY-MM-DD."; the view and the
  download of a missing archive both 404.
- Tests: `test_malformed_output_requests_get_the_console_notice`;
  test_output_by_date's pin of the missing archive's 200 now reads 404
  (the bug's symptom; its docstring says so). Its two callers are links
  (runs.html, output.html's window.open), never a fetch reading the code.
- Risk: none beyond these requests.
- For Ely: none

## SB-16 (also: none)
- Reproduced: yes. /sandbox?model=del_me (no such model) flashed "Not
  opened: model 'del_me' is missing model.bngl, data.exp, priors.conf".
- Root cause: sandbox.py `model_dir` lists the missing files without
  checking the folder exists.
- Fix: no folder -> SandboxError "no sandbox model named del_me"; the
  page reads "Not opened: no sandbox model named del_me".
- Tests: `test_opening_a_deleted_sandbox_model_says_it_is_not_there`.
- Risk: every model_dir caller (read, run, register) says the same for a
  missing model; no test pinned the old words.
- For Ely: none

## Checks
- New app/tests/test_error_pages.py (5): each fails on 8cb3f7d and passes
  here. test_ui_layout, test_models_tab, the output, download, sandbox,
  custom-retro and season tests: pass. ruff clean.
- Full suite (FLUBNF_HUB=/nonexistent): 4206 passed, 160 skipped, 0 failed.
- Output check: not needed (no run path; output.py's /run-free routes).
- Windows: no paths beyond Path(""); the notice is a template.

## Patch
G22/proposal.patch (git diff origin/dev...proto/G22-A)
