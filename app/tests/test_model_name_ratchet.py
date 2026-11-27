"""The two shipped models are named directly in too many places; that number
may only go down.

The Oracle SIHRS and the Groundhog are written into the code by their storage
keys ('pf', 'analogue') and by their display names, file after file: member
tuples, labels, colours, file names, page text. Adding a third model, or
letting a user bring their own, means finding every one of those places. The
planned fix is one model registry that every page, form, file name and record
reads from. Until it exists, this test keeps the count from growing: a new
member list or a name typed again fails here, and the change should read the
name from a constant that already holds it (submit.MODEL_ABBR,
custom_run.MEMBER_LABELS, runs.ENGINE_LABELS, report_v2.MODEL_SHORT,
knobs.MEMBERS) instead.

The ceilings are the counts on `dev` at 320df9bc. When a change removes names,
lower them to the new counts in the same commit, so the room cannot be spent
again. Raise them only for a change that cannot be made otherwise, and say
why in its commit message.

What counts: a non-test .py, .html, .js or .css file under app/ or flubnf/,
and each of its lines that holds a quoted 'pf' or 'analogue' (either quote)
or the words "Oracle SIHRS" or "Groundhog".
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("app", "flubnf")
SUFFIXES = {".py", ".html", ".js", ".css"}
NAMES = re.compile(r"""(['"])(?:pf|analogue)\1|Oracle SIHRS|Groundhog""")

MAX_FILES = 91
MAX_LINES = 845


def _is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_") or path.name == "conftest.py"


def name_counts(root: Path = ROOT) -> dict[str, int]:
    """Lines naming either model, per file (relative path), for files with any."""
    out: dict[str, int] = {}
    for top in SCANNED:
        for path in sorted((root / top).rglob("*")):
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            rel = path.relative_to(root)
            if _is_test(rel):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            n = sum(1 for line in text.splitlines() if NAMES.search(line))
            if n:
                out[rel.as_posix()] = n
    return out


def test_pattern_finds_what_it_should_and_nothing_else():
    hits = [
        "MEMBERS = ('pf', 'analogue')",
        'key = "pf"',
        "Oracle SIHRS forecasts",
        "the Groundhog's donors",
    ]
    misses = [
        "pf_filter = 1",          # another key, counted by the registry work later
        "'pf2s'",
        "pdf",
        "analogues of the week",  # the word, unquoted
        "groundhog_cache",        # lower case: a module or folder name
    ]
    assert all(NAMES.search(s) for s in hits)
    assert not any(NAMES.search(s) for s in misses)


def test_the_two_models_are_not_named_in_more_places():
    counts = name_counts()
    files, lines = len(counts), sum(counts.values())
    if files <= MAX_FILES and lines <= MAX_LINES:
        return
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:12]
    listing = "\n".join(f"  {n:4d}  {f}" for f, n in top)
    raise AssertionError(
        f"{files} files and {lines} lines now name 'pf'/'analogue', \"Oracle SIHRS\" "
        f"or \"Groundhog\"; the ceiling is {MAX_FILES} files and {MAX_LINES} lines.\n"
        "Read the model's id, name or colour from an existing constant "
        "(submit.MODEL_ABBR, custom_run.MEMBER_LABELS, runs.ENGINE_LABELS, "
        "report_v2.MODEL_SHORT, knobs.MEMBERS) instead of writing it again.\n"
        f"Files with the most:\n{listing}"
    )
