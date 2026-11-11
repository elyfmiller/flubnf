"""Two launcher wordings, known and left as they are, recorded in the App
lane's notes (docs/team/app.md, Now, 2026-11-10 evening), and the facts
that note states, read from the scripts as they are.

1. After a reinstall into ~/Documents/GitHub, setup.sh's run-again line
   names the folder, and FluBNF.command, which the reinstall opens at its
   end, then moves that folder to ~/GitHub.
2. On FluBNF.command's first run, setup.sh says "./setup.sh again" in a
   Terminal window that has no shell to type it into.

When a script changes so that either one no longer holds, a test here
fails: the note is then to be brought up to date (or dropped, once the
wording is fixed). Text only.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Prose is hard-wrapped, so a phrase may straddle a line break."""
    return " ".join(text.split())


def _note() -> str:
    """The App notes' entry on the two wordings."""
    notes = _read("docs/team/app.md")
    now = notes[notes.index("## Now"):notes.index("## Decided")]
    at = now.index("- 2026-11-10 (evening): two launcher wordings")
    return _flat(now[at:now.index("\n- ", at + 1)])


def test_the_app_notes_record_both_wordings():
    note = _note()
    assert "known and left as they are" in note
    assert "**After a reinstall into `~/Documents/GitHub`.**" in note
    assert ('`run cd "<home>/Documents/GitHub/flubnf" && ./setup.sh '
            'again`') in note
    assert "moves the copy to `~/GitHub/flubnf`" in note
    assert "**FluBNF.command's first run.**" in note
    assert ('"Setup hit a problem (see above). Press enter to close."'
            in note)
    assert "where `./setup.sh` is not found" in note


def test_the_reinstall_s_facts_hold():
    """reinstall.sh uses the Documents folder when an older setup is there
    and none is in ~/GitHub, tells setup.sh it came from there, and opens
    FluBNF.command at its end; FluBNF.command moves a Documents copy;
    setup.sh's reinstall line names its own folder."""
    rs = _read("reinstall.sh")
    assert ('[ -z "${FLUBNF_DIR:-}" ] && [ ! -e "$DEST" ] && '
            '[ -e "$HOME/Documents/GitHub/flubnf" ]') in rs
    assert 'DEST="$HOME/Documents/GitHub/flubnf"' in rs
    assert '( cd "$DEST" && FLUBNF_SETUP_FROM=reinstall ./setup.sh ) || {' \
        in rs
    assert 'open "$DEST/FluBNF.command"' in rs.split('say "done"')[1]
    sh = _read("setup.sh")
    assert 'again="run cd \\"$HERE\\" && ./setup.sh again"' in sh
    # a problem setup.sh carries on past: a warning, and no exit
    assert 'warn "data fetch failed (offline?) -- $again when connected"' \
        in sh
    cmd = _read("FluBNF.command")
    assert "scripts/macos/move_home.sh --check" in cmd
    assert 'exec /bin/bash ./FluBNF.command' in cmd


def test_the_first_run_s_facts_hold():
    """FluBNF.command runs setup.sh in its own folder without saying where
    it came from, so setup.sh's plain run-again words stand; then it
    closes, or starts the console in the same window. Its own stop for a
    missing launcher says to double-click it again."""
    cmd = _read("FluBNF.command")
    assert "FLUBNF_SETUP_FROM" not in cmd
    assert 'cd "$(dirname "$0")"' in cmd
    assert ('./setup.sh || { forget_reopen; echo; echo "Setup hit a problem '
            '(see above). Press enter to close."; read -r; exit 1; }') in cmd
    assert "Double-click me again" in cmd
    sh = _read("setup.sh")
    assert 'again="run ./setup.sh again"; Again="Run ./setup.sh again"' in sh
