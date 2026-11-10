# G26: review (A)
PR #85, head 4b1e241.

Approve.

- Commits bcfcd7a and 4b1e241: authored and committed as Ely F. Miller <efm46@nau.edu>, no trailers.
- The diff is the decision: A's FC-13 (`reported.covering_rules`, the box's script on load, on change and on `ms-reset`, the run's refusal in words, a covered state with no answer unrecorded), FC-18, FC-22 and FC-25; B's FC-21 mechanics (`_settings_refused`, the "Not run." / "Not started." lead, the dataset run's and the Retrospective's notices, the defaults under the remembered form) with A's `_PLAIN_REFUSALS`; B's "Pick a date.". Status cell "fixed in #85; FC-13 for Ely: ...".
- Tests on the head: test_forecast_panel_fixes, the Data issues, knobs, forecast modes, research run, retro forms, datasets, partial week, newest week, forecast aids, marks and layout tests: 222 passed; ruff (the gate) clean.
- Live on a server from the head (8812, the hub copy with Arizona at 0 and Ohio at 2):
  - FC-13: Level offered with the rule kept; with "Newest weeks reading 0" counted as unreported Arizona offers only "Both from 10-10 / Leave out" (Ohio too once "Collapsed newest week" is on); the run page "2 states, 2 recommended, 0 changed; 2 set aside" and "(set aside (Forecast tab)): Arizona 1, Ohio 1"; after the run the box still follows the setting; Reset brings every choice back; a stale post of Level is refused: "Not run: Data issues for Arizona: Level does not apply while Newest weeks reading 0 is set to counted as unreported; choose Both from 10-10 or Leave out."
  - FC-18: both selects whole (98 px of text in 206 px).
  - FC-21: no top notice; the panel "Not run. Replicates: 0 is outside 1 to 10.", "Not run. Prior range for Reff: 2.5, 0.6 is not a range: the low end must be 0 or more and below the high end.", "Not run. Kernel jitter: 'abc' is not a number."; a form posted from /model/analogue gets its one line there ("Not run: Own-state donor weight: 7 is outside 0 to 1."); the Retrospective's panel "Not started. Own-state donor weight: ..." with no top notice.
  - FC-22: the refusal hidden after Reset. FC-23: "Pick a date.". FC-25: the picker follows a typed archived week, and the same week can be picked again.
- Output: all-53 Groundhog on 2026-10-17, dev 349db4b and the head both 56da9201b416eb5c80317c849b55168e.
