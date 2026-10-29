# G13: review (B)
PR #67, head 4cbe0a3.

Approve.

- The code diff is byte-for-byte the decided patch (A's G13/proposal.patch); the second commit sets the Status cell to #67.
- Commits are authored as Ely with no trailers; the PR body carries no footer.
- Targeted on the head (worktree): test_phone_menus_rows, test_ui_kit, test_console_qol, test_ui_layout, test_fewer_marks, test_sandbox_guard: 135 passed; ruff gate clean.
- Live on a server from the head (Chromium, the stored `fontsize`):
  - ST-01 at 390: the title column 291 / 309 px at 160 / 130% (0 / 6 before), Delete's right edge 340 / 350 inside the screen; 768 and 1280 unchanged (three columns).
  - ST-02: no filter button narrower than its word at 390 and 130 / 160% (two and three rows); one row of 30 px at 1280.
  - SB-01: How it works and Manage inside the screen at 390 (x 14 to 372), 480, 640, and at 660 / 700 / 720 px with 160% text (the script's clamp: left edge 8); 700 and 1280 at 100% as before.
  - SB-13: the Runs table (two stand-in runs) shows the edge shadow while it scrolls at 390 (352 in 332 px; 564 in 298 at 160%) and none at 768 where it fits.
  - UI-07: the readout's right edge 340 inside the menu's 367 at 390 and 160%; two columns there, three at 130%, four at 768 and 1280 (the desktop names wrap exactly as on dev).
  - MO-08: #rr-particles 183 px with 100000 typed at 1280 (68 before), 296 at 390 and 160%, the count under the field.
- Windows: stylesheets and one script.
