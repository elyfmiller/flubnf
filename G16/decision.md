# G16: decision (by B)
Decision: combined: A's patch as the base (OU-03 `_report_suffix` with
the per-run name for Ely; OU-04 `_drawn`; OU-05 the header link's inline
referrer rule; RE-26 `download_name`; FC-20), with B's OU-06 (the hidden
sections' figures as JSON, drawn by `rpDraw` when a section opens, the
retint pass taking one chart) in place of A's early script and section
move. Tests: A's test_weekly_report_files.py with B's
`test_a_hidden_sections_figures_wait_for_it_to_open` in place of A's
OU-06 test; test_report_weekly's split string; test_report_design_pass
unchanged.
Implementer: B
Why: both votes combine. Criterion 2 for OU-03 (the Decided name of
2026-10-01 stands; the override case is named like its files) and
criterion 4 for RE-26 (the download name only). Criterion 1 for OU-06:
only the lazy figures fix UI-09's load time as well as the dead buttons,
and an opened state draws as on dev. OU-04, OU-05 and FC-20 are equal;
A's are taken with the base (OU-05's inline rule also reaches the stored
reports legacy_theme_carry dresses).
Left for Ely: OU-03: two shipped runs of one week still save their
reports under one name (the decided name is the reference date's;
telling them apart would change it).
Not reproduced: none
