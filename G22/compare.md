# G22: compare (A)

B's patch applied to origin/dev 8cb3f7d on a scratch worktree: its
test_error_pages, test_ui_layout, test_output_by_date and
test_browse_safety, 54 passed.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| UI-10 | a handler in routes/output.py beside `_notice`; a 404 outside /api/ and /static/ is the notice only when the request asks for HTML | a handler in routes/shell.py; every 404 outside /api/ and /static/ is the notice | Equal on every symptom. B's rule is the simpler one and safe: the console's script fetches outside /api/ are two (POST /output/reveal, /data/datasets/check), both to routes that exist, so no script reads a 404 there. A's Accept test keeps a non-browser client's JSON; nothing in the console needs that. B's home for an app-wide page (the shell's routes) fits better than Output's. B. |
| MO-11 | "No model named nope", Open Models | the same | Equal. |
| WI-14 | the replay: Open Retrospective (/retro); the season report: Back to the season | the replay: /retro?dataset=<id> when the dataset exists (retro_index reads it, as data.html's "Replay it" does); the season report: Open the season | B: the way back from a missing replay lands on that dataset's replays. |
| OU-16 | `path` defaults to ""; `date.fromisoformat`; the missing archive's view 404; the pin updated | the same, and the pin's test also checks the download agrees | Equal (A's new test checks the download too). |
| SB-16 | "no sandbox model named del_me" | "no sandbox model named 'del_me'" | Equal; B's quotes the name as the module's other refusals do ("model 'del_me' is missing ..."). |

Vote: B
