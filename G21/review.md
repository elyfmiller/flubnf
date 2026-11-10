# G21: review (B)
PR #79, head 9036c0b.

Approve.

- The diff is the decision: the four paths under APP_STATE (no checkout
  fallback); reclaim's roots with the reseal and `_storage_protected`
  asking `reclaim.is_protected`; a protected workroot's row with the lock
  badge in place of Delete, no new words; `workroot_failures` over the top
  level's and pf2s/ pf_status.json, an unreadable file keeping the trees;
  /output/download a .csv under submission/ or export/. The Status cell
  names #79 and WI-04's Sandbox part for Ely. Both commits authored and
  committed as Ely F. Miller <efm46@nau.edu>, no trailers; the PR body has
  no footer.
- Tests on the head: test_state_folder_protect, test_reclaim,
  test_storage, test_lean_storage, test_state_isolation, test_download_log,
  test_download_headers, test_submission_identity, test_output_by_date,
  test_busy_guard, test_ui_layout, test_engine_update: 177 passed. ruff
  clean (app/ui).
- Live, on servers from the head with their own state folders (the G20
  run state; a second server with FLUBNF_PROTECT_ROOTS naming one
  workroot):
  - WI-04: a Vermont Groundhog replay of 2025-26 wrote <state>/retro/
    2025-26 (weeks, run_meta, the season report); nothing under the
    tree's app/state; report_path names the state folder's file. A
    console on a fresh state folder lists no season and its reclaim
    reports 0/0/0.
  - ST-06: the protected workroot's row: no Delete control, the lock
    badge, no "running now"; a crafted POST /storage/delete answers "Not
    deleted: that tree is protected …" and the folder stays;
    reclaim.is_protected and storage._storage_protected both True on
    <state>/retro_reseal/2023-24.
  - ST-07: a workroot with results.json, Arizona_r0/pf.log and a failed
    cell in pf_status.json: /api/storage/reclaim 0/0/0; with the cell
    "ok": 0/1/0.
  - OU-15: <state>/ledger.sqlite, last_form.json and a run's results.json
    404 (the console's page); the run's submission CSV 200 text/csv.
