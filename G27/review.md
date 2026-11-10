# G27: review (B)
PR #86, head f6162c3.

Approve.

- Commits c729f5e, 5dff3ed (dev merged in) and f6162c3: authored and committed as Ely F. Miller <efm46@nau.edu>, no trailers; the PR body carries no footer. Status cell "fixed in #86".
- The diff is the decision: A's patch (DA-09 ": "; DA-15 "both from the week before"; DA-16 the two-line tip with README's own-data paragraph; DA-17 "Rates: choose rates. Counts: write them without the dots (1.234 as 1234)."; DA-21 the Save only clause where that button is) with B's binary rule in `parsing.not_text` (the workbook magic and the control-byte density, said before any reading; the Windows-1252 note only when the second read did not refuse the file) and B's assertions in test_dataset_lenient.
- Tests on the head: test_data_upload_words, test_dataset_lenient, test_dataset_snapshots, test_dataset_upload_box, test_newest_reported, test_datasets_ui, test_data_issues, test_fewer_marks, test_pages: 345 passed; ruff (the gate) clean.
- Live on a server from the head (8824, the private hub copy with Arizona at 0 and Ohio at 2, the stored Kids dataset):
  - DA-09: "Groundhog (own data) only: the particle-filter engine is not installed".
  - DA-15: "0 after 63, 69, 60: Arizona. Recommended: both from the week before (looks like a missed report)."
  - DA-16: two lines, 338 characters; 320 x 170 px at 1280 light, 320 x 161 px at 390 dark; no sideways scroll.
  - DA-17: "... 1.234 is 1.234 as a rate or 1234 as a count. Rates: choose rates. Counts: write them without the dots (1.234 as 1234)."
  - DA-20: a zip named book.xlsx "This looks like an Excel workbook, not a CSV file: save it as CSV UTF-8."; bytes 0 to 255 and a PDF-like file with no NUL "The file is not text: it holds binary data. Save it as CSV UTF-8."; each the one problem, no encoding note.
  - DA-21: "Forecast this and Replay this store the dataset, then open ...; Save only stores it and stays here. Nothing runs until you start it there." beside the three buttons; the template reads Ready to use.
- No run path touched.
