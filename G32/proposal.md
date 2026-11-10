# G32 output-polish: proposal (A)
Base: origin/dev 446542d (fb4fa7f plus other lanes' notes)

How: a dev server (8815) with four Groundhog vintage runs, all 53 locations, their workroots cloned to 32 (four dates), and a prototype server (8816) on a copy of that state. Relaunches timed with curl; the hub check timed alone. No round is open in this data, so OU-14 uses the tests' fake open round, with the page script run in Chromium on a controlled clock.

## OU-07 (the first Output after a launch re-checks every file)
- Reproduced: yes, in proportion. One hubcheck.summary takes 0.08 to 0.10 s here. Output after a relaunch: 0.50 s with 4 dated files (warm: 0.06 s). A season of about 30 dates is about 3 s on every launch, as the hunt measured.
- Root cause: `routes/output._CHECKED` is in memory only, so each launch checks every listed file again.
- Fix:
  - The results are also kept on disk, in the state folder's `hubcheck_results.json`. They are keyed as in memory, by path, mtime and size, and read once per state folder; the window ("due") is rebuilt from the reference date when read.
  - The file carries a rules digest: hubcheck.py and its vendored tasks.json. A result is used only while both are the ones that made it, so a changed rule checks every file again.
  - An "unreadable" result is not kept. The file is rewritten whole, via a temporary file.
  - Nothing else changes: the gate in submit.write_submission and the run pages' checks are as before.
- After: 0.13 s after a relaunch on the same state (dev 0.51 s).
- Tests: `test_output_polish.py::test_hub_checks_are_kept_on_disk_across_a_relaunch` (kept, read back without a check, and discarded under other rules).
- Risk: one small file in the state folder. Storage does not list it.

## OU-10 (walls of text; "?" on lines, "i" on cards)
- Reproduced: yes. The title's "i" holds 9 paragraphs (about 250 words). Your data's "?" reads "hubverse-format quantile CSVs (23 levels, horizons 0 to 3, reference date = forecast date + 7 days) ...". A line's "fails hub checks" is a tooltip "?", where a card's is a toggletip "i".
- Fix (output.html):
  - The title's "i" is three lines: what the files are and that each is checked before it is written; which file a date run twice shows, and what -modified files are; the hub's window and that FluBNF only writes the files.
  - Dropped from it: the reference date's definition (it heads each card), the file-name pattern (each file shows its name), the list of checks, retired names and the copy buttons (each button names what it copies). Methods is about the models, not the files, so nothing moves there.
  - Your data's note: "Forecasts on your own datasets, newest first, under non-hub names: for your own use, downloaded on this computer only."
  - A line's failing checks: the cards' badge and toggletip ("the hub check problems", one line per problem).
- Tests: `test_the_explainers_are_short_and_failing_lines_open_like_cards`.

## OU-13 (Download and Show in folder name no file)
- Reproduced: in the markup. The file row's link and button read only "Download" and "Show in folder".
- Fix: `aria-label="Download <name>"` and `aria-label="Show <name> in folder"` (_filerow.html), as the line links and the copy buttons already do.
- Tests: `test_each_files_controls_name_it`.

## OU-14 (medium confidence; reproduced: the countdown freezes)
- Reproduced: in code. The time left is rendered once, and the stamp check returns early when no run landed, so a page left open keeps "3 days 8 h left" and a closed round's gold Download.
- Fix:
  - `_date_status` adds `flips`: the instants, ISO UTC, at which the badge next changes. For a coming round that is the window's opening (midnight Eastern on its first day). For a due round it is the start of its last 12 hours (URGENT_HOURS, when the badge turns error) and the close.
  - The badge's time left is a span the page script keeps to the minute, from the deadline the page already carries.
  - The script reloads the page once when a flip passes, and waits while a form has focus or the guard modal is open. Each flip reloads at most once (sessionStorage), so a browser clock ahead of the server's cannot loop.
- After (Chromium, the clock run forward): "2 days 8 h left", then "2 days 6 h left" after 61 minutes. One reload at the 12-hour mark, and none a minute later.
- Tests: `test_an_open_rounds_badge_changes_on_a_page_left_open` (the flips for a due and a coming round, none for a whole-day answer, and the markup).

## OU-17 (a notice's "?" lowercases ids)
- Reproduced: in the kit. `empty()` names its tip `title | lower` and `alert()` `(title or text) | lower`, so "No run 20261025T184517-9a04d9 ..." reads "about no run 20261025t184517-9a04d9 ...".
- Fix (_tips.html, alert and empty only): only the first word is lowered, and not when it is a name or an acronym (a capital after its first letter: FluSight, US). Ids and names keep their case.
  - This is written inline in the two macros, not as a helper macro: test_ui_kit requires every macro in _tips.html to be a documented one.
  - The other kit labels (stats, labels, legends) are not touched: they carry no ids.
- Tests: `test_a_notices_tip_keeps_ids_and_names_as_written`.

## Checks
- New `app/tests/test_output_polish.py` (5), each failing on dev. Output, marks, kit, pages and layout tests: 240 passed, 6 skipped. ruff (the gate) clean.
- Output check: not needed. No run path is touched, and the hub checks themselves are unchanged (only where their result is kept).
- Windows: the kept file's paths are strings, written as UTF-8 JSON and replaced with Path.replace; the clock code is the browser's.

## Patch
G32/proposal.patch (git diff origin/dev...proto/G32-A)
