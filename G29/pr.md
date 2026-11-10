# G29: pr (A)
PR: https://github.com/elyfmiller/flubnf/pull/88
Head: 92104c390d2a2949322c1156c772426264b1cdb8 (was 4dfe348)
Base: dev fb4fa7f (G28 merged)
The decision applied as decided (proto/G29-A); the Status cell reads "fixed in #88".
Full suite on the branch: 4255 passed, 160 skipped, 0 failed; ruff (the gate) clean.

Update 92104c3: CI on 4dfe348 failed on both test-windows jobs in my own test, test_storage_words::test_archived_runs_read_in_this_computers_time. Windows has no time.tzset, so the block that set and removed TZ never ran, and the test's last assertion (TZ gone) failed there. The test now checks the form "YYYY-MM-DD HH:MM" everywhere, and the Phoenix reading only where a zone can be set. It passes here, and with time.tzset deleted (as on Windows). Full suite: 4255 passed, 160 skipped, 0 failed. No product code changed.
