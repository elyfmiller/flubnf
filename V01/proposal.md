# V01 retro-runners: proposal (A)
Base: origin/dev 368e922

## FC-06, the /retro/run variant (found in the G01-G10 re-check)
- Reproduced: yes.
  - Browser: /retro, Shard width "2e0" (checkValidity true), Run
    retrospective, Resume in the start-over prompt: the page becomes
    /retro/run with
    `{"detail":[{"type":"int_parsing","loc":["body","width"],…,"input":"2e0"}]}`.
  - A cleared box posts "" and gets the same 422.
  - B re-checked with POST width=2e0: 422.
- Root cause: app/ui/routes/retro.py `retro_run`, `width: int = Form(4)`.
  G02 typed particles and replicates as text on this form and noted width
  for G23, but no G23 bug lists it.
- Fix:
  - `width: str = Form("4")`, read where it was clamped (after the knob
    validation, before anything is archived or claimed):
    `typed = _str_field(width).strip()`, then
    `max(1, min(int(typed or 4), 16))`.
  - Anything that is not a whole number:
    `_refused("Not started: shard width: '2e0' is not a whole number.")`,
    named by the field's label ("Shard width"), as the Forecast tab's knob
    refusals name theirs.
  - A blank reads as the form's own default, 4, as particles and
    replicates read a blank. The clamp to 1..16 is unchanged.
- Tests: `test_knobs_wiring.py::test_a_replay_refuses_a_shard_width_the_browser_allows_in_words`
  (parametrized). 2e0 is refused with nothing launched; then "3" launches
  with width 3 and "" with width 4. Both cases fail on 368e922 and pass
  here.
- Risk: the one field. One-click Resume posts the record's width (a whole
  number) and reads as before. Invariance: no (no run path or output).
- Status: no row exists for it. I'd add one after G10, "V01
  `retro-runners` | The Retrospective Run form's shard width typed as text
  | FC-06 (the /retro/run variant, found in the G01-G10 re-check) | S2 |
  … | fixed in #NN", so the record shows where it went.
- For Ely: none.

## Checks
- Targeted: test_knobs_wiring, test_retro_config, test_retro_live_progress
  and test_ui_layout: 96 passed. ruff (F gate) clean.
- Full suite (FLUBNF_HUB=/nonexistent): 3534 passed, 155 skipped, 0 failed.

## Patch
V01/proposal.patch (git diff origin/dev...proto/V-width-A)
