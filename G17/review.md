# G17: review (B)
PR #71, head 55f73c8.

Approve.

- The diff is the decision: my prototype (hub_missing with its reasons,
  the Data and Forecast lines, the check and the pull refusals, the /run
  refusal, the Setup card's data line, the engine as one component in the
  badge, the rows and the versions row, every row in plain words, the pin
  note, the in-place "checking…" badge, Perl through resolve_perl, the
  conftest fake with hub_check_real, the golden line) with A's DA-22
  (`fresh_after_pull`, the one-shot `_pulled`) and A's test in place of
  mine. The Status cell reads "fixed in #71".
- Both commits authored as Ely, no trailers; the PR body has no footer.
- Tests on the head: test_hub_setup, test_setup_badge, test_fewer_marks,
  test_data_view, test_pull_hub, test_data_tab_qol,
  test_forecast_us_choice, test_knobs_wiring, test_server_hardening,
  test_ui_layout, test_platform_setup_hint, test_pages: 205 passed. ruff
  gate clean.
- Live on servers from the head:
  - no hub, no BioNetGen: "3 not installed ? FluSight data, BioNetGen,
    Particle-filter engine", the data line then the engine's, the rows in
    plain words, "Particle-filter engine not installed · BioNetGen not
    installed · Perl 5.38.2"; Data "No FluSight data: there is no hub
    folder at /nonexistent. To fetch it, run ./setup.sh and relaunch the
    console.", "Hub clone missing", the check "missing" / "no hub clone:
    …", Update data refused with the step; Forecast's line; a Groundhog
    run for 2026-04-25 "Not run: no FluSight data (…)" with no workroot.
  - a private hub copy: right after Update data "Hub clone up to date",
    the next visit "not checked".
  - the slow probe on a copy of the head: "checking…" at first paint
    (every value resolving), then "1 not installed" with "?"
    "Particle-filter engine"; the versions row "Perl 5.38.2".
