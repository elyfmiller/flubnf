# G22: compare (B)
A's proposal read in full; A's patch applied on its base 8cb3f7d (on
today's dev, b4b176b, its output.py hunk conflicts with G21's docstring
and must be re-merged); its 5 tests with test_output_by_date,
test_ui_layout, test_browse_safety, test_download_headers,
test_run_labels_deleted, test_datasets_ui: 94 passed; ruff clean. The two
proposals take the same route on every bug; the differences are where the
404 handler lives and what it keys on, the replay notice's link, an
explicit empty-path return, and SB-16's quotes.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| UI-10 (MO-11, WI-14), the handler | `output._not_found_page`, registered in server.py: a 404 off /api/ and /static/ whose request accepts text/html is the notice; any other Accept keeps JSON. "Back to Home" | `shell.not_found_page`, registered with add_exception_handler: a 404 off /api/ and /static/ is the notice, whatever the Accept. "Open Home" | **A**, criterion 2: a script's fetch of a page path (a stub, a test, a poll) still reads the JSON it read before; only a window or a browser gets the page. Beside `_notice` in output.py is its natural home. |
| UI-10, the model and replay notices | "No model named nope", Open Models, heading "Models"; "No such replay", Open Retrospective (/retro) | the same words; heading "Model"; the replay notice's way on is the dataset's replays (/retro?dataset=<id>) when the dataset exists, else /retro | **B** for the replay link, criterion 1: RE-24 (G23) names the same page's missing way back to its dataset; the notice should lead there. Heading: either. |
| UI-10, the season report | the helper keeps its signature; the route turns a plain refusal into the notice (404 empty, 503 error), "Back to the season" | the same, "Open the season" | equal |
| OU-16 | `path` defaults to ""; an empty path returns `_not_found` explicitly (download) and reads as no file (reveal); `_bad_date` parses the day; the missing archive's view 404 | the same without the explicit return (the existing containment checks give the 404) | **A**, criterion 4: the explicit line says what an empty path means. |
| SB-16 | "no sandbox model named del_me" | "no sandbox model named 'del_me'" (the file's `{name!r}` idiom) | **A**: the bug's expected words. |
| Tests | 5 (the window-vs-script case among them) | 5 (the dataset-link case among them) | combine: B's file with A's window-vs-script assertions. |

Vote: combine: B's patch as the base, with A's handler (`_not_found_page`
in output.py keyed on Accept text/html, "Back to Home") in place of B's
shell.py one, A's explicit empty-path return in the download, A's SB-16
words, and A's window-vs-script test assertions; B's replay notice keeps
the dataset's replays as its way on.
