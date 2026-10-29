# G14: compare (B)
A's patch applied on 78f0331 (scratch worktree): every sandbox test file, test_datasets_ui and test_busy_guard pass.
| Bug | A's | B's | Better, and why |
|---|---|---|---|
| SB-02 | the page refuses a file over the cap before the post, through the file field's own validity message (data-max-bytes); the server's words add "the editor's text included" | the same refusal with a kit alert in the pane (data-cap); the server's words add "unsaved edits in the editor were not saved" | Equal in effect; A's uses the field's own message and adds no element (criterion 4). |
| SB-03 | missing weeks counted up to the source's newest week (the vintage's date, settled truth's newest over all locations, a dataset's newest group week); the flash and the holds row show the weeks loaded | missing weeks counted up to the location's own last loaded week; the sidecar and flash carry the loaded range | A, criterion 1: a location short of the source's newest week still counts that week missing (B's would not), and the weeks loaded are read from the sidecar's dates. |
| SB-06 | a label from dataset_choices with the weeks when a name repeats | the same, computed in the template | Equal. |
| SB-08 | the cap goes | the same | Equal. |
| SB-09 | a free suggestion (data-taken, _2, _3 …) and a refused form that comes back as posted (a one-shot kept like the upload report) | the free suggestion only (the Copy of choices as the taken names) | A, criterion 1: both of the bug's symptoms, the taken name and the reset form. |
| SB-11 | refused over 364 days back: "… is more than a year before the forecast date …; the model fits one season" | over 366 days, the refusal naming production's start | Equal; A's shorter (5). |
| SB-12 | the words only: "a sandbox fit is running (<id>); one run at a time." and "a console run is in progress"; the one-run lock stays (recorded design) | the words only, the same way; the overlap listed for Ely | Equal on the fix. A's reading stands: the lock is unchanged, so nothing is left for Ely; the Status cell should say the lock stays. |
| SB-17 | copy names `<model>_copy_1` | `<model>_1` | Equal; A's names the copy. |
Vote: A
