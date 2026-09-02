"""Thin wrapper around scripts/validate_submission.R.

Runs a FluSight submission CSV through the hub's own acceptance code
(the hubValidations R package) in a throwaway git worktree of a hub clone,
so the clone is never dirtied. Prints one GREEN or RED line plus any
failing checks, and exits nonzero on RED. Needs only R with hubValidations
and a public clone of cdcepi/FluSight-forecast-hub; the private engine is
not involved.

Usage:
    python scripts/validate_submission.py <submission.csv> <hub_clone_path> [--window]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    rscript = shutil.which("Rscript") or "/usr/local/bin/Rscript"
    if not Path(rscript).exists():
        print("RED: Rscript was not found on this machine. Install R first.")
        return 2
    r_file = Path(__file__).resolve().parent / "validate_submission.R"
    proc = subprocess.run([rscript, str(r_file), *argv])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
