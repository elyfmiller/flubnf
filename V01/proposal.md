# V01 retro-runners: proposal (B)
Base: origin/dev 368e922

## V01 (A's finding 1 of the G01-G10 re-check; FC-06's shape on the Retro form)
- Reproduced: yes. POST /retro/run width=2e0 on 368e922: HTTP 422 with the
  raw JSON `{"detail":[{"type":"int_parsing","loc":["body","width"],…
  "input":"2e0"}]}`. The browser's number box lets 2e0 (and 1.5) through.
- Root cause: app/ui/routes/retro.py retro_run declares `width: int =
  Form(4)`, the one visible number field G02 left typed int (particles and
  replicates became str fields read by the knob parser there).
- Fix: `width: str = Form("")`, read as typed where the other numbers are
  validated (after the knob block, before anything is moved or claimed):
  commas stripped, a non-integer refused with the flash "Not started:
  runners: '2e0' is not a valid int." (the G02 wording), a blank is this
  machine's DEFAULT_SHARD_WIDTH, then the existing clamp to 1..16. The
  refusal goes back to /retro like every other one of this handler.
- Tests: app/tests/test_knobs_wiring.py
  test_a_replay_refuses_a_runner_count_the_browser_allows_in_words
  (parametrized: 2e0, 1.5 and "two" refused with that flash and nothing
  launched; "2" and blank launch), beside G02's
  test_a_replay_refuses_a_number_the_browser_allows_in_words.
  Targeted: test_knobs_wiring, test_retro_config, test_busy_guard,
  test_retro_archive, test_oracle_step: 146 passed; ruff gate clean.
- Live: served from the prototype, width=2e0, 1.5 and two each give 303 to
  /retro with the flash; a blank width starts the replay with the default.
- Risk: the Retro run handler only; no run-path file, so no invariance
  check. Windows: nothing path- or encoding-specific.
- For Ely: none

## Patch
V01/proposal.patch (git diff origin/dev...proto/V01-B)
