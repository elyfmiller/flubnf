# G06: review (A)
PR #55, head 5d1e564 (ac82edd the change, 5d1e564 the Status cell).

The code: approve as it stands. The PR body: two changes requested (the body is the record; no code change, no new CI run needed for it).

1. "What changes" names the wrong bug on five bullets (the commit message lists them together and is fine). As the hunt numbers them:
   - the vintage rule (`realtime_of`, `choose`, `keep_reason`, the pipeline's flag) is **OU-02**, not OU-01;
   - the run page and report from the archive (`_run_folder`) is **OU-09**, not OU-02;
   - the picker keeping the card's week is **OU-01**, and its "Archived weeks" label **OU-11** (the bullet says OU-08);
   - the live badge's tip is **OU-08** (the bullet says OU-09);
   - the explainer's rules are **OU-08** too (the bullet says OU-11).
   The first bullet's "(also OU-11's page, HM-05's rule)" can go.
2. "Tests: app/tests/test_which_run_shows.py (10 tests, new)": the file holds 9 (A's 8 and B's HM-05 one).

What I checked
- The app diff is A's prototype (proto/G06-A) plus, as decided: `shared._wrote_forecasts` and its test, the `newer_run` link in `routes/models.py` and `model.html` with its assertions, and the `test_models_tab` fakes taking keywords; the rest are docstring rewraps. Author and committer Ely F. Miller <efm46@nau.edu>; no attribution lines or forbidden words in messages, diff or body; no footer; Status cell `fixed in #55`.
- On the head: test_which_run_shows, test_models_tab, test_output_by_date, test_archive_rule, test_output_freshness, test_output_run_pages, test_browse_safety, test_ui_layout, test_report_bundle, test_pages, test_storage, test_run_integrity: 189 passed. `ruff check --select F821,F823,F811,F401 app/ui` clean.
- Live, a server from the head: a real-time Arizona run, then a vintage quick run of 2026-10-10 from /model/analogue: the card reads "Latest real-time run 2026-10-17 · …" and, after the quick run, "Run details Newer run on the Forecast tab". The other bugs are the prototype's code, which I re-checked live before (OU-01 picker, OU-02 on a hub copy, OU-09 after a Storage delete, HM-05 on Home).
