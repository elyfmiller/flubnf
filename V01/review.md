# V01: review (A)
PR #64, head 42881a9.

Approve.

- The diff is the decision: width read as typed after the knob block and
  before anything is moved or claimed; commas stripped; "Not started:
  shard width: '…' is not a whole number."; a blank is
  DEFAULT_SHARD_WIDTH; the clamp to 1..16 is unchanged. The V01 row and
  "fixed in #64" are set.
- Commits are authored as Ely, with no trailers; the PR body has no footer.
- Targeted on the head: test_knobs_wiring, test_retro_config,
  test_retro_live_progress, test_ui_layout and test_busy_guard: 127
  passed. ruff (F gate) clean.
- Live, on a server from the head (Chromium):
  - 2e0 at 1280 light: back on /retro with the refusal; nothing started.
  - A cleared box at 1280 dark: the replay starts, recorded with width 2
    (this 4-core machine's default, the value the box showed).
  - 1.5 is held by the browser itself (step 1), so the server's refusal of
    it is the test's to show.
- Windows: nothing path- or encoding-related.
