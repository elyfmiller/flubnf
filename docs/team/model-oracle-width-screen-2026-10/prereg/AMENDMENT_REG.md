AMENDMENT R TO PREREG.md (sha256 fd8f57d6): THE REGISTERED MEMBER AS A
REFERENCE ARM (2026-10-22, at Ely's request: "how the relWIS scores change
between old registration and this new one being tested now"; added before
any arm is scored)

REG  the registered Oracle SIHRS as main runs it with no override (its
     pre-registration 67c9fa49): pf.seed_denominator = to_date, oracle.w =
     0.5, oracle.narrow = 1, no upper-tail rule. Same weeks, machine,
     engine, worktree and scorer as every arm; queued right after C0,
     before the season-end fits.

Reading, descriptive (no decision rule; a record for the team's review),
pooled relWIS on both scales, coverage, the gate, by season, each step
against REG on the common cells with the week-cluster bootstrap:
  1. REG as registered (exact);
  2. REG's logged secondary, w 0.25, the submitted seed before the floor
     (the weight alone; oracle.json, so pre-floor, within check C);
  3. C0 at k = 1 (the stage rule and w 0.25; re-exponentiated, approximate
     within check C);
  4. C0 at k = 0.7 (the live configuration of the 2026-10-24 round, exact);
  5. C0 at k = 0.7 with the upper-tail rule at 15x, 10x and 8x, shrink and
     clip (the 2026-10-28 candidates, exact).
