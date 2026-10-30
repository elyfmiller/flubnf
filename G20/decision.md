# G20: decision (by B)
Decision: combined: B's patch, with MO-23's scroller named as the other
figscroll regions are (the drawing's own label plus "(scrolls)":
"Seasonal harmonic (scrolls)", "Two-strain seasonal harmonic
(scrolls)") and test_theme_and_harmonic's needles tightened to the
figure's own label ("Seasonal harmonic:", "Two-strain seasonal
harmonic:"), so it still counts each figure once and never its
scroller (A's second option; B's revised patch had taken the first);
and ME-07's phone grid as A's flow: two columns, the symbol spanning
three rows, the meaning, units and source flowing down the second
(B's placed the units beside the source with `grid-column`, which
test_reading_column forbids in nau.css), the symbol column capped at
6rem as B's was.
Implementer: B (the author of the chosen patch, and the decider)
Why: both votes take B's patch (A: combine = B plus the harmonic test
and A's ME-07 flow; B: B, then the same after A's full-suite finding). Criterion 2 for ME-10 (A's rule moves every fold's badge to the
right edge); criterion 1 for DA-10 (the name column collapses at 768 px
and 160% without a floor) and MO-19 (the shorter rows); criterion 4 for
MO-23 (the drawn width) and ME-08 (the template's entities, Home's
padding rule). The scroller's name follows the convention (criterion 4)
and the test change is the smaller one, as A reasoned.
Left for Ely: none
Not reproduced: none
