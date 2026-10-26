AMENDMENT 1 TO PREREG.md (sha256 fd8f57d6): THE PAST-SEASON BOXES' VALUES
Written by build_boxes.py from the season-end fits (arms/FITS), by the
rule of section 3, before HP or HS runs and before any arm is scored.

Season-end fits (per-jurisdiction posterior medians over three replicates):
- 2022-23 at 2023-06-10: 52 jurisdictions; median eps1 0.188 (5-95%: 0.065-0.367), median phi1 30.3 (5-95%: 18.4-34.0)
- 2023-24 at 2024-04-27: 52 jurisdictions; median eps1 0.148 (5-95%: 0.065-0.399), median phi1 28.5 (5-95%: 20.9-36.4)
- 2024-25 at 2025-06-14: 52 jurisdictions; median eps1 0.145 (5-95%: 0.060-0.388), median phi1 25.4 (5-95%: 10.3-35.7)

Boxes:
- 2023-24 (from 2022-23): HP eps1 [0.0, 0.5175], phi1 [10.5493, 41.8682]; HS widths over 52 jurisdictions, eps1 median 0.617 (range 0.200-1.000), phi1 median 46.7 (range 10.7-52.0) weeks
- 2024-25 (from 2022-23, 2023-24): HP eps1 [0.0, 0.5418], phi1 [11.1557, 44.6482]; HS widths over 52 jurisdictions, eps1 median 0.739 (range 0.310-1.000), phi1 median 52.0 (range 39.8-52.0) weeks
- 2025-26 (from 2022-23, 2023-24, 2024-25): HP eps1 [0.0, 0.5604], phi1 [0.0, 52.0]; HS widths over 52 jurisdictions, eps1 median 0.859 (range 0.329-1.000), phi1 median 52.0 (range 44.3-52.0) weeks; notes: phi1: 2 fits straddle the wrap [('2024-25', 'Massachusetts'), ('2024-25', 'Texas')]; HP falls back; Massachusetts phi1: a fit straddles the wrap; shipped range; Texas phi1: a fit straddles the wrap; shipped range

Full tables: boxes.json.
