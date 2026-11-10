# G23: review (B)
PR #81, head 21aeefc.

Approve.

- The diff is A's patch with B's RE-12 as decision.md says: `output_reveal` answers a JSON caller `{ok, message, detail}` through one `answer()` (the form posts keep the flash and the redirect; `path` keeps G22's "" default), and `fail(msg, title)` in retro_season.html shows the reveal's own sentence as the alert's title. RE-13 (the in-memory form, the panel's values, `ms_refused` once), RE-24 and RE-25 as proposed; the Status cell reads "fixed in #81".
- Tests on the head: test_retro_forms, test_retro_archive, test_datasets_ui, test_season_page_player, test_download_headers, test_ui_layout, test_dataset_replay_knobs, test_output_by_date, test_error_pages, test_fewer_marks: 157 passed; ruff clean.
- Live on a server from the head (8823): /retro/2025-26, Show in folder (no xdg-open here): under the buttons "Nothing opened: no file manager could be started." with the FileNotFoundError and the file's path as the text, at 1280 px. /retro after the custom-scope refusal: season 2025-26, custom (the list shown), states only, Groundhog only, blend, all kept. The replay page's badge and back link were checked on A's patch earlier (8824): "stopped after 76 of 142 weeks", "Back to the replays", "No forecasts stored", no sideways scroll at 1280 light and 390 dark.
