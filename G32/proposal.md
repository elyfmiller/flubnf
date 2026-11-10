# G32 output-polish: proposal (B)
Base: origin/dev def45dbe (#61 merged)

How: a dev server over a state of 35 cloned Groundhog workroots (34 past dates and one open round, forecast 2026-11-07, due Wed 2026-11-11), timed with curl and profiled; the pages at 1280 px light and 390 px dark in Chromium, its clock set by Playwright for the countdown.

## OU-07
- Reproduced: yes. forecast_dates cold 7.7 s profiled (34 hubcheck.summary calls, 0.2 s each under the profiler; 0.1 s plain), warm 0.16 s; GET /output after a restart 3.9 s, then 0.16 s.
- Root cause: `routes/output._CHECKED` is a dict in the process; every launch checks every listed file again.
- Fix: the checks are kept on disk, `hub-checks.json` in the state folder (`CHECKS_FILE`): `_read_checks` loads it once per process into `_CHECKED` (the summary's `due` is rebuilt from its reference date), `_write_checks` rewrites it (whole file, atomic) when a file is checked; one entry per path, a rewritten file (new mtime or size) replaces its entry; a file that cannot be read or written leaves the checks in memory, as before. The write gate is untouched (no core change, no run-path change). After: the second launch's first GET /output 0.27 s; the first launch after the fix pays once.
- Not taken: skipping the lines' checks (the line's "fails hub checks" badge needs them); storing at write time (a core change in the run path, and the first page visit after a run is warm anyway).
- Tests: `test_hub_checks_are_kept_on_disk_between_launches`, `test_a_checks_file_that_cannot_be_read_starts_empty`.
- Risk: a new file in the state folder (beside component_versions.json and last_form.json); nothing lists the state root's files. Invariance check: no (the run path is untouched).
- For Ely: none

## OU-10
- Reproduced: yes. The title's "i" held 9 lines (about 250 words); the Your data "?" the hubverse sentence; a line's "fails hub checks" was a "?" tooltip where a card's "Fails N hub checks" is an "i" panel.
- Fix: the title's "i" is three lines (what the files are and that each is checked; cards and lines; the hub's window and that you upload) and a link "Which run's file shows, and the names" to a new Methods fold `mt-files` in Data and verification policies, which holds the moved text (the names and the quantile output, the checks, which run's file shows, modified and retired names, the copy buttons). A line's badge opens the same toggletip as a card's (`tt-out-lchk-<di>`, titled "Fails hub checks", one line per file). The Your data note is one line. test_fewer_marks' passing prefix moves from `tip-out-lchk-` to `tt-out-lchk-`.
- Tests: `test_the_title_help_is_three_lines_and_points_to_methods`, `test_a_lines_failing_checks_open_the_same_panel_as_a_cards`, `test_the_your_data_note_is_one_line`.
- Risk: Methods gains a fold (its links to folds do not open them, as /methods#mt-newest does not either). Invariance: no.
- For Ely: none

## OU-13
- Reproduced: yes (the focus order read Download, Show in folder, three times).
- Fix: `_filerow.html` gives Download `aria-label="Download <name>"` and Show in folder `aria-label="Show <name> in folder"`; the visible words stay.
- Tests: `test_download_and_show_in_folder_name_their_file`.
- Risk: none. Invariance: no.

## OU-14 (medium confidence: reproduced)
- Reproduced: yes. The badge "Due Wed 2026-11-11, 11 PM ET · 1 day 20 h left" and the gold Download stayed as rendered with the clock moved past the close; the stamp check returns before reloading when no run landed.
- Fix: the open round's `.out-bt` carries `data-out-due="<close ISO>"` (winbadge); a page script (output.html, beside the reader's-clock one) rewrites the badge through `FluBNFUI.setBadge` every 30 s and on pageshow, focus and visibility, in `_time_left`'s words ("2 days 1 h left", "5 h left", "7 min left"), turning it error under `URGENT_HOURS` (passed as `urgent_hours`), and reloads the page once the close has passed, waiting as the stamp check does over a focused form or the guard. tips.js is deferred, so the first tick is on DOMContentLoaded and waits for the kit.
- Tests: `test_the_due_badge_carries_its_close_for_the_page_script`; `test_the_badge_counts_down_and_the_page_reloads_once_closed` runs the script in node against a stand-in page, as test_output_freshness does.
- Risk: the badge's words after a tick are the script's, which mirror `_time_left`. A "soon" round still waits for a run or a reload to turn "due" (the open time is not in the markup; the bug is the countdown and due to closed). Invariance: no.
- For Ely: none

## OU-17
- Reproduced: yes: `aria-label="About no run 20261025t184517-9a04d9 is recorded here"` on /runs/<gone id>.
- Fix: `_tips.html`'s alert and empty lowercase only the first letter of the title for the "?"'s name (`lbl[:1] | lower ~ lbl[1:]`); "No runs yet" still reads "About no runs yet".
- Tests: `test_a_notices_question_mark_keeps_names_as_written`.
- Risk: every alert and empty title keeps its inner case now; no test pinned a lowercased name. Invariance: no.

## Checks
- New `app/tests/test_output_polish.py` (9 tests); test_fewer_marks' KEEP prefix. The Output, marks, pages, layout, kit, knobs and site-build tests: 355 passed, 23 skipped. ruff (the gate) clean. Full suite: see the line below once it has run.
- Live: cold Output 3.9 s then 0.27 s across two launches; badge "1 day 19 h left" to "1 day 16 h left" after 3 h, "3 h left" in error under 12 h, reload once past the close (desktop and phone); the marks on /output are the title's "i" and one "i" per failing line or card; no sideways scroll at 390 px; the notice reads "About no run 20261025T184517-9a04d9 is recorded here".
- Windows: the checks file is JSON with the file's own path string as key (backslashes escaped by json); written with os.replace; utf-8 both ways.

## Patch
G32/proposal.patch (git diff origin/dev...proto/G32-B)
