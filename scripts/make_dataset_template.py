"""OPS: regenerate FluBNF's synthetic grouped-CSV template and its test slices.

The download template (app/ui/static/dataset-template.csv, "Template CSV")
and the two test slices (app/tests/fixtures/grouped-template-*.csv) are
made-up data, not anyone's surveillance counts. This script is how they were
made, so they can be re-made and audited:

- three groups: Pediatric, Adult and Overall = Pediatric + Adult;
- 143 Saturdays from 2022-01-01, dates written M/D/YY as a spreadsheet does;
- each of Pediatric and Adult is a low baseline with a mild winter swell plus
  four seasonal waves (Pediatric peaks a little earlier and lower), with
  Poisson-like noise (Gaussian, variance = mean) from a fixed seed;
- constant populations, Overall's the sum of the other two.

The slices are the first ten weeks (30 rows): one as a spreadsheet's
"CSV UTF-8" export writes it (UTF-8 BOM, CRLF, no population column), one
with populations (plain LF). app/tests/test_datasets.py checks that the
committed files are byte-for-byte what this script writes.

    python scripts/make_dataset_template.py           # rewrite the files
    python scripts/make_dataset_template.py --check   # exit 1 if they differ
"""
from __future__ import annotations

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = "app/ui/static/dataset-template.csv"
SLICE = "app/tests/fixtures/grouped-template-head.csv"
SLICE_POP = "app/tests/fixtures/grouped-template-population-head.csv"

SEED = 42
START = date(2022, 1, 1)          # a Saturday
WEEKS = 143
SLICE_ROWS = 30                   # ten weeks x three groups
GROUPS = ("Pediatric", "Adult", "Overall")
POP = {"Pediatric": 1752418, "Adult": 5236907}
POP["Overall"] = POP["Pediatric"] + POP["Adult"]

#: per group: (peak Saturday, height, rise sd in weeks, fall sd in weeks)
WAVES = {
    "Pediatric": [(date(2022, 1, 15), 58, 3.0, 4.5),
                  (date(2022, 11, 19), 131, 3.5, 4.0),
                  (date(2023, 12, 23), 92, 4.0, 5.5),
                  (date(2024, 3, 16), 17, 3.0, 3.0)],
    "Adult": [(date(2022, 1, 22), 176, 3.5, 5.0),
              (date(2022, 12, 3), 305, 4.0, 5.0),
              (date(2023, 12, 30), 248, 4.5, 6.0),
              (date(2024, 3, 23), 38, 3.0, 3.5)],
}
BASE = {"Pediatric": 9.0, "Adult": 27.0}


def mean(group: str, d: date) -> float:
    """The expected weekly count for a group on Saturday d."""
    m = BASE[group]
    # a gentle summer trough in the baseline (highest mid-January)
    doy = d.timetuple().tm_yday
    m *= 1.0 + 0.25 * math.cos(2 * math.pi * (doy - 15) / 365.25)
    for peak, height, rise, fall in WAVES[group]:
        w = (d - peak).days / 7.0
        sd = rise if w < 0 else fall
        m += height * math.exp(-0.5 * (w / sd) ** 2)
    return m


def rows() -> list[tuple[str, str, int, int]]:
    """(M/D/YY date, group, value, population), week by week."""
    rng = random.Random(SEED)
    out = []
    for i in range(WEEKS):
        d = START + timedelta(days=7 * i)
        vals = {}
        for g in ("Pediatric", "Adult"):
            mu = mean(g, d)
            vals[g] = max(0, int(round(rng.gauss(mu, math.sqrt(mu)))))
        vals["Overall"] = vals["Pediatric"] + vals["Adult"]
        ds = f"{d.month}/{d.day}/{d:%y}"
        out.extend((ds, g, vals[g], POP[g]) for g in GROUPS)
    return out


def build() -> dict[str, bytes]:
    """{repo-relative path: exact bytes} for the three files."""
    rs = rows()
    tpl = ["date,target_group,value,population"]
    tpl += [f"{a},{b},{c},{p}" for a, b, c, p in rs]
    head = rs[:SLICE_ROWS]
    # as a spreadsheet saves "CSV UTF-8": BOM, CRLF, M/D/YY
    crlf = ["date,target_group,value"] + [f"{a},{b},{c}" for a, b, c, _ in head]
    pop = (["date,target_group,value,population"]
           + [f"{a},{b},{c},{p}" for a, b, c, p in head])
    return {
        TEMPLATE: ("\n".join(tpl) + "\n").encode(),
        SLICE: b"\xef\xbb\xbf" + "".join(f"{r}\r\n" for r in crlf).encode(),
        SLICE_POP: "".join(f"{r}\n" for r in pop).encode(),
    }


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for rel, data in build().items():
        p = REPO / rel
        if check:
            if not p.is_file() or p.read_bytes() != data:
                stale.append(rel)
        else:
            p.write_bytes(data)
            print(f"wrote {rel}")
    for rel in stale:
        print(f"differs from the generator: {rel}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
