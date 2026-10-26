# G01: review (B)
PR #50, head 6c96e45 (c93fd60 the change, 6c96e45 the Status cell).

Approve.

What I checked
- The diff is A's proposal patch plus the two guard asserts the decision named (module copies are the pin; `data.live_newest_week()` is None); nothing else differs. Author Ely F. Miller, no attribution lines, no forbidden words in the diff, title and body in the repo's form with no footer.
- On the head, the five TS-01 tests (MO-21's two among them), `test_state_isolation`, `test_hubcheck`, `test_core`, `test_model_metadata`, `tests/test_sihrs_fit`, `tests/test_doctor_engine_hub`, `tests/test_first_run_sparse_hub`: 116 passed, 10 skipped with the clone at the default path and no env; the same with `FLUBNF_HUB` exported to the real clone; the same under CI's `FLUBNF_HUB=/nonexistent` (identical skip lists). With `FLUBNF_TEST_HUB` pointing at the sparse clone: 124 passed, 2 skipped (the clone's missing ensemble files and this machine's missing sealed runs).
- The guard fails without the pin: with dev's conftest and the PR's test, 1 failed both with the clone at the default path and under `FLUBNF_HUB=/nonexistent`.
- `ruff check --select F821,F823,F811,F401` clean on app/ui and the changed test files. Status cell reads `fixed in #50`.
