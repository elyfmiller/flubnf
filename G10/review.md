# G10: review (B)
PR #59, head 9cb3fbf (fix/G10-season-player from dev 04d2ebb).

Approve.

- The code is the chosen patch (A's proposal), cherry-picked onto 04d2ebb;
  the diff against origin/dev differs from the proposal patch only in two
  hunk offsets in routes/retro.py (G09 moved the lines). The Status cell
  reads `fixed in #59`. Commits are Ely's, no attribution; the PR body has
  no footer.
- Targeted on 9cb3fbf (14 files incl. test_season_page_player,
  test_playback, test_shipped_vintages, test_server_hardening,
  test_retro_live_progress): 284 passed, 2 skipped; ruff gate clean. Full
  suite on 9cb3fbf: 3523 passed, 154 skipped, 2 failed (tests/test_doctor.py,
  environmental: Python 3.13 here).
- Live on the head (8826: hub copy with the baseline, scored 2024-25 and
  2025-26; 8827: no baseline, unscored 2026-27):
  - RE-04: from ?week=2025-01-18&view=map, three ArrowLefts, Forecast
    detail: Models row "Groundhog, FluSight baseline, FluSight ensemble",
    Groundhog in the live scores; with ?loc=Texas the menu has 53 entries
    and opens on Texas, a California click switches to California.
  - RE-11: 2025-08-30 reads "no FluSight round" for the Groundhog and the
    official; the payload's no_round is true there, false on 2025-11-22;
    _v stays 7.
  - RE-15: 1280 "Aug Dec Jan Feb Mar Apr Jun", 390 "Aug Dec Jan Feb Mar
    Apr May Jun", nothing overlapping or outside the track.
  - UI-01: reduce 983 -> 465, card top 0; no-preference 1026 -> 465.
  - UI-18: "0 jurisdictions scored", the clock and "Arrives with the first
    scored week"; no filter, no bare headers (phone, dark).
  - UI-20: "Scoring failed. The FluSight baseline forecasts are not on
    this computer yet. Update data from the Data tab, then open this page
    again.", "Details" fold, Data tab on its own line (phone, 136 px).
- Windows: no paths, encodings or line endings in the diff.
