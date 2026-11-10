# G27: compare (A)
Read B's proposal and patch.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| DA-09 | The join is ": ". | The same. | Equal. |
| DA-15 | CHOICE_WORDS["set_aside"] = "both from the week before". | The same. | Equal. |
| DA-16 | Two lines, 340 characters (161 px tall on the phone); the column names, separators and encodings move to README's own-data paragraph. | Three lines, 440 characters (201 px on the phone); the alias list dropped, the non-hub line kept. | A's: the hint asks to move the alias detail to the docs, not drop it (A's keeps it findable in README), and fewer words on the page (criterion 5; the non-hub line is said where the forecasts are, the dataset's Forecast settings tip and Output's Your data). |
| DA-17 | "Rates: choose rates. Counts: write them without the dots (1.234 as 1234)." | "If they are counts, write them without the dots (1.234 as 1234); if they are rates, choose rates." | B's: the same advice as a sentence a student reads plainly (Ely's plain English). |
| DA-20 | A workbook's first bytes (zip, OLE) named up front; the cp1252 note dropped when the header is refused as not text. A NUL sniff was tried and dropped (a stray NUL cell is a cell problem). | `parsing.not_text`: a zip is named as a workbook; control bytes throughout the first 4 KB (at least 8 and 1 in 64, never UTF-16/32 padding) are "not text: it holds binary data", before any reading. | B's (criterion 1): the report's second symptom, a binary file's long "mixes encodings" message full of �, is reproduced and fixed only by B's; an .xls (OLE) reads as binary under B's rule, so A's second magic adds nothing. |
| DA-21 | "Forecast this and Replay this store the dataset, then open ...; Save only stores it and stays here." | "Each stores the dataset. Forecast this then opens ...; Replay this ...; Save only stays here." | Equal; B's names each button once, in order. B's. |

Vote: combine: A's DA-16 (the two-line tip; README's own-data paragraph; the snapshot pin reading the as_of line); B's DA-17, DA-20 and DA-21; DA-09 and DA-15 as both have them. Tests: A's test_data_upload_words.py for DA-09, DA-15 and DA-16; B's for DA-17, DA-20 and DA-21.

Vote (final): combine, as B's vote: A's patch (DA-09, DA-15, DA-16 with the README paragraph, DA-17, DA-21, and DA-20's workbook magic for .xlsx and .xls with the note guard) plus B's binary rule from `parsing.not_text` (the control-byte density, "The file is not text: it holds binary data. Save it as CSV UTF-8.") and its assertions. Changed after B's compare: DA-20, B's point holds (a binary file with no NUL on its first line, a PDF or an image, still reaches the "mixes encodings" message under A's alone); DA-17 and DA-21, either wording works, and B's vote keeps one patch's words.
