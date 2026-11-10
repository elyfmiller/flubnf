# G31: pr (A)
PR: https://github.com/elyfmiller/flubnf/pull/91
Head: 697f7415424c487d027183a6cb2ed1667abb0ba1
Base: dev c2ad352e (#90 merged); dev has since gained other lanes' notes (cd21afa5), no conflict.
The decision as written: A's patch with B's `_weeks` helper (SB-25) and the 64 KB cap (SB-26), on today's dev. Two conflicts with the engine switch (#61) resolved: machine_problems keeps dev's public-engine branch, with the plain headline before the missing engine's message; What changed keeps dev's engine row and `_run_setting`, labelled "engine". test_engine_cutover_fixes' comparison pin gains the label.
Full suite on the branch: 4666 passed, 216 skipped, 0 failed (run in the foreground of a background task: a shell's `&` starts the suite with SIGINT ignored, and test_sandbox_cli's handler test then fails on dev too). ruff (the gate) clean. Live: the captions, the unchanged Save, Save and run's pointer under the plain notice, and the label sizes, as in the PR.
Output check: not needed (no run path).

Windows: test-windows (3.11) failed on 62f5b0ff in test_sandbox_polish's run-zip test: it wrote the .err file in text mode, so Windows turned \n into \r\n and the zip's bytes (copied as written) no longer ended in \n. 697f7415 writes the bytes, as the engine does; the product code is unchanged. Re-review asked for this head.
