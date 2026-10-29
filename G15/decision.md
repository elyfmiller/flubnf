# G15: decision (by A)
Decision: A
Implementer: A
Why: both votes A. Criterion 1: ST-09 is fixed whole: the ledger and
workroot rows read the same time, and the archive row names its round.
FC-16's ledger facts drop the claimed "1 submission" and "report ✓".
Criterion 2: one test, `output._files_deleted`, decides on the run page,
the ledger, the Forecast card and the fans' badge, and it knows an
archived run's files are not deleted. Criterion 5: FC-19's words replace
the empty card's line instead of adding an alert; A's guard also catches
a results.json that is not a JSON object.
Left for Ely: none
Not reproduced: none
The fix branch is cut from dev once G14 (#68) is merged.
