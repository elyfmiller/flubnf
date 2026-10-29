# G14: review (A)
PR #68, head eafcd8b.

Approve.

- The diff is my prototype (proto/G14-A at 79a7f7f's tree) plus exactly
  the decided changes: the SB-02 server words, the SB-11 refusal (366 days,
  naming production's start) with its test, and the 64-character trim in
  `free()`. Nothing else differs. The Status cell reads "fixed in #68;
  SB-12: the refusals' words only, the one-run lock stays".
- Commits as Ely, no trailers; the PR body has no footer.
- Tests on the head: every app/tests/test_sandbox*.py, test_datasets_ui,
  test_busy_guard: 278 passed, 4 skipped. ruff clean.
- Live on a fresh server from the head (Chromium, 1280):
  - SB-02: a 33 MB file with "# MY EDIT" typed: the page stays, the field
    says "This file is larger than the 20 MB limit; choose a smaller one.",
    the editor still starts "# MY EDIT".
  - SB-03: "19 weeks of New York, 2026-06-06 to 2026-10-10", holds "19
    weeks"; Arizona settled to 2026-12-31: "7 weeks ... 2026-09-05 to
    2026-10-17", holds "7 weeks".
  - SB-06: "cases (2025-01-04 to 2025-01-25)", "cases (2024-01-06 to
    2024-01-20)".
  - SB-08: 27 stand-in runs: "27 runs", "... and its 27 runs", 27 to
    compare with.
  - SB-09: suggested oracle_arizona_2026-10-17_2; a forced taken name
    comes back as Oracle SIHRS / Arizona / 2026-10-17 / 2026-08-08.
  - SB-11: "Not created: the season start 2025-08-01 is more than a year
    before the forecast date 2026-10-17; the Oracle SIHRS fits one season
    (production starts 2026-08-01)".
  - SB-17: "g14_pr6zfq_copy_1".
