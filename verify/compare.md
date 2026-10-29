# Re-check of G01-G10: compare (B)

Verdicts: the two tables agree on all 53 bugs (51 fixed, DA-02 and RE-17 for
Ely as recorded). A's full suite with the hub clone present (0 failed) adds
to my five-test TS-01 run.

Findings:
- A's 1 (the Retro form's "runners" field, `width: int = Form(4)` in
  app/ui/routes/retro.py, 422 JSON on 2e0): re-checked by B on 368e922 with
  POST /retro/run width=2e0: HTTP 422, `{"detail":[{"type":"int_parsing",
  "loc":["body","width"],…"input":"2e0"}]}`. Accepted. It is the FC-06
  shape on the one visible number field G02 left typed int; the three other
  int Form fields (forecast.py weeks_to_nowcast, members, drop_same_day;
  datasets_ui.py drop_same_day) are hidden or selects and cannot be typed.
- A's 2: withdrawn by A; agreed (RE-14 stays fixed).
- B found none.

Agreed: one fix group, V01 `retro-runners` (from G02, so B decides),
runs the usual loop before G11.
