"""The newcomer docs, held to the repository and the code they describe.

docs/ADAPTING.md tells an outside group what works today for another
target, pathogen, geography or season calendar, what the console assumes,
and what needs code. Its numbers and rules are the upload check's and the
models' own, so each one is pinned here to the constant or the check that
holds it: a change to the code that makes the page wrong fails here. The
links of README.md and docs/*.md must reach a file in the repository.
Nothing is stored: the checks run validate_snapshots, as the console's
upload check does, which keeps nothing.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADAPTING = REPO / "docs" / "ADAPTING.md"
DOCS = [REPO / "README.md"] + sorted((REPO / "docs").glob("*.md"))

#: a markdown link's target: [text](target) or [text](<target>)
_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Prose is hard-wrapped, so a phrase may straddle a line break."""
    return " ".join(text.split())


def _prose(text: str) -> str:
    """The text outside fenced blocks and inline code, where links live."""
    kept, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            kept.append(line)
    return re.sub(r"`[^`\n]*`", "", "\n".join(kept))


def _heading_anchor(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation other than
    hyphens dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _anchors(text: str) -> set[str]:
    ids = set(re.findall(r'<a id="([^"]+)"></a>', text))
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        m = re.match(r"(#{1,6}) (.+)", line)
        if m and not fenced:
            ids.add(_heading_anchor(m.group(2)))
    return ids


def _relative_links(doc: Path) -> list[str]:
    out = []
    for target in _LINK.findall(_prose(_read(doc))):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            continue
        out.append(target)
    return out


def _table_row(name: str) -> list[str]:
    """ADAPTING.md's table row whose first cell holds `name`, as cells."""
    for line in _read(ADAPTING).splitlines():
        if line.startswith("| ") and name in line.split("|")[1]:
            return [c.strip() for c in line.split("|")[1:-1]]
    raise AssertionError(f"docs/ADAPTING.md has no row for {name}")


def _row_text(name: str) -> str:
    return " ".join(_table_row(name))


# ------------------------------------------------------------- links


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_every_relative_link_reaches_a_file_in_the_repository(doc):
    """A link to a moved or renamed file lands on GitHub's 404 page."""
    bad = []
    for target in _relative_links(doc):
        path = target.split("#", 1)[0]
        if path and not (doc.parent / path).exists():
            bad.append(target)
    assert not bad, f"{doc.relative_to(REPO)} links to what is not there: {bad}"


def test_every_anchor_the_adapting_page_links_to_exists():
    bad = []
    for target in _relative_links(ADAPTING):
        if "#" not in target:
            continue
        path, anchor = target.split("#", 1)
        page = (ADAPTING.parent / path) if path else ADAPTING
        if anchor not in _anchors(_read(page)):
            bad.append(target)
    assert not bad, bad


def test_the_index_and_the_readme_lead_to_the_adapting_page():
    index = _read(REPO / "docs" / "README.md")
    row = next(line for line in index.splitlines()
               if line.startswith("| Outside groups and other targets |"))
    assert "[ADAPTING.md](ADAPTING.md)" in row
    readme = _read(REPO / "README.md")
    quick = readme[readme.index("\n## Quick start\n"):
                   readme.index("\n## What it forecasts")]
    assert "[docs/ADAPTING.md](docs/ADAPTING.md)" in quick


# ------------------------------------------------------------- README


def test_the_quick_start_installs_the_engine_and_names_the_own_data_path():
    """The public engine is the default, and a clone by hand installs it
    with setup_engine.sh; the own-data lines name the tab, the template
    and what the Liu-West filter needs."""
    readme = _read(REPO / "README.md")
    quick = readme[readme.index("\n## Quick start\n"):
                   readme.index("\n## What it forecasts")]
    code = [line.strip() for line in quick.splitlines()
            if line.startswith("    ")]
    assert any(line.startswith("./setup_engine.sh ") for line in code), code
    assert code.index(next(c for c in code if c.startswith("./setup.sh"))) < \
        code.index(next(c for c in code if c.startswith("./setup_engine.sh")))
    assert (REPO / "setup_engine.sh").is_file()
    flat = _flat(quick)
    for needle in ("**Your data**", "**Template CSV**",
                   "the Liu-West filter needs counts and a population"):
        assert needle in flat, needle


# ------------------------------------------------------------- wording


def test_the_adapting_page_keeps_the_text_rules():
    """No en or em dash, the project's words, and three columns of facts
    beside the row's name."""
    text = _read(ADAPTING)
    assert "–" not in text and "—" not in text
    low = _flat(text).lower()
    assert "posterior" not in low
    assert "particle filter" not in low
    assert not re.search(r"(?:filter|engine)s? (?:adapts|tracks|follows)\b", low)
    assert "liu-west filter" in low
    header = next(line for line in text.splitlines() if line.startswith("| Change |"))
    assert [c.strip() for c in header.split("|")[1:-1]] == [
        "Change", "Works today without code", "What the console assumes",
        "Needs code"]
    # no link into the maintainers' own working folders
    assert ".claude" not in text


# ------------------------------------------------------------- the code it names


def _defined(path: Path, name: str) -> bool:
    src = _read(path)
    return bool(re.search(rf"^(?:def |class )?{re.escape(name)}\b\s*[(:=]",
                          src, re.M)
                or re.search(rf"^(?:def|class) {re.escape(name)}\b", src, re.M))


def test_every_module_and_name_in_needs_code_exists():
    """The Needs code column names modules and names, never line numbers,
    and each one is still where the page says."""
    cells = [_table_row(name)[3] for name in (
        "Your own weekly data", "Another target", "Another pathogen",
        "Another geography", "Another season calendar")]
    text = " ".join(cells)
    assert not re.search(r"\.py:\d", text), "a line number in Needs code"
    pairs = re.findall(r"`([\w/]+\.py)` `(\w+)`", text)
    pairs += [(f, n) for f, names in
              re.findall(r"`([\w/]+\.py)` \(((?:`\w+`(?:, )?)+)\)", text)
              for n in re.findall(r"`(\w+)`", names)]
    pairs += [(mod.replace(".", "/") + ".py", n)
              for mod, n in re.findall(r"`(app\.[\w.]+):(\w+)`", text)]
    assert len(pairs) >= 15, pairs
    missing = [f"{f} {n}" for f, n in pairs
               if not (REPO / f).is_file() or not _defined(REPO / f, n)]
    assert not missing, missing
    for path in re.findall(r"`((?:app|flubnf|data)/[\w./-]+)`", text):
        assert (REPO / path).exists(), path


def test_the_numbers_and_rules_are_the_codes():
    from app.core import custom_run as CR
    from app.core import datasets as D
    from app.core import horizons as HZ
    from app.core import knobs as K
    from app.core import submit as SB
    from app.ui import datasets_ui as DU
    from flubnf import analogue as AN

    own = _flat(_row_text("Your own weekly data"))
    lim = D.DEFAULT_LIMITS
    assert lim.max_groups == 200 and "At most 200 groups" in own
    assert lim.max_rows == 1_500_000 and "1,500,000 rows" in own
    assert lim.max_bytes == 100 * 1024 * 1024 and "100 MB" in own
    assert AN.MIN_DONORS == 30 and "The Groundhog needs 30 earlier weeks" in own
    assert AN.DEFAULT_BANDWIDTH == 2 and "MMWR week is within two of its own" in own
    assert set(CR.EXPORT_IDS.values()) == {"FluBNF-Groundhog", "FluBNF-SIHRS-PF"}
    assert "FluBNF-Groundhog and FluBNF-SIHRS-PF" in own
    assert CR.BASELINE == "in-house persistence baseline" and CR.BASELINE in own
    assert D.group_name_ok("x" * 40) and not D.group_name_ok("x" * 41)
    assert D.group_name_ok("Baden Württemberg")
    assert not D.group_name_ok("Baden-Württemberg")
    assert "at most 40 letters" in own

    target = _flat(_row_text("Another target"))
    assert HZ.HORIZONS == ("0", "1", "2", "3") and "Horizons 0 to 3 weeks" in target
    assert len(SB.QUANTILES) == 23 and "23 quantile levels" in target
    locked = {lk.key for lk in K.LOCKED}
    assert {"horizons", "quantile_levels", "season_boundary_month",
            "pf.template"} <= locked

    geo = _flat(_row_text("Another geography"))
    assert tuple(D.NATIONAL_NAMES) == ("US", "USA", "UNITED STATES",
                                       "US (NATIONAL)", "NATIONAL")
    assert "US, USA, United States, US (national) or National" in geo
    assert not D.is_national_name("England")

    cal = _flat(_row_text("Another season calendar"))
    assert AN.SEASON_BOUNDARY_MONTH == 8 and "from August to July" in cal
    assert DU.REPLAY_MONTHS == (10, 11, 12, 1, 2, 3, 4, 5, 6)
    assert "October to June of the newest season that holds 8 or more" in cal


def _csv(header, rows) -> bytes:
    return (",".join(header) + "\n"
            + "".join(",".join(map(str, r)) + "\n" for r in rows)).encode()


def _weeks(first: str, n: int, step: int = 7) -> list[str]:
    d0 = date.fromisoformat(first)
    return [(d0 + timedelta(days=step * i)).isoformat() for i in range(n)]


def _check(header, rows):
    from app.core import datasets as D
    return D.validate_snapshots([("s.csv", _csv(header, rows))])


def test_the_week_rules_the_page_states():
    """A plain date header moves a Sunday 6 days on; a week-ending header
    refuses it; daily rows are refused."""
    sundays = _weeks("2024-01-07", 4)
    r = _check(["date", "group", "value"], [(d, "A", 10) for d in sundays])
    assert r.ok and r.summary["first"] == "2024-01-13"
    assert any("+6 days" in w for w in r.warnings)
    for header in ("week_ending", "target_end_date"):
        r = _check([header, "location", "value"], [(d, "A", 10) for d in sundays])
        assert "weekday_end" in r.codes, (header, r.codes)
    r = _check(["date", "group", "value"],
               [(d, "A", 10) for d in _weeks("2024-01-01", 21, step=1)])
    assert not r.ok
    own = _flat(_row_text("Your own weekly data"))
    assert "a Sunday moves 6 days on" in own
    assert "a Sunday, Monday or Tuesday is refused" in own
    assert "Daily rows are refused." in own


def test_the_snapshot_and_group_limits_the_page_states():
    from app.core import datasets as D
    two = _csv(["date", "group", "value"],
               [(d, g, 5) for g in "AB" for d in _weeks("2024-01-06", 3)])
    three = _csv(["date", "group", "value"],
                 [(d, g, 5) for g in "ABC" for d in _weeks("2024-01-06", 4)])
    r = D.validate_snapshots([("2024-01-20.csv", two), ("2024-01-27.csv", three)])
    assert "snapshot_groups" in r.codes
    many = [(d, f"G{g:03d}", 5) for g in range(201) for d in _weeks("2024-01-06", 2)]
    assert "limit_groups" in _check(["date", "group", "value"], many).codes
    assert "Snapshot files must all hold the same groups." in _flat(
        _row_text("Your own weekly data"))


@pytest.mark.parametrize("seasons, groups, short", [
    (5, "A", True), (6, "A", False), (1, "ABC", True), (2, "ABC", False)])
def test_how_much_history_the_groundhog_needs(seasons, groups, short):
    """"One series needs about six earlier seasons, three groups about
    two": a steady series, one row a week, checked at its newest week."""
    from app.core.datasets import checks as DC
    rows = [(d, g, 50) for g in groups
            for d in _weeks("2010-08-07", 52 * seasons + 30)]
    r = _check(["date", "group", "value"], rows)
    assert r.ok
    assert any(w.startswith(DC.TOO_LITTLE_HISTORY) for w in r.warnings) is short
    assert ("One series needs about six earlier seasons, three groups about two"
            in _flat(_row_text("Your own weekly data")))


def test_the_template_the_page_offers_is_ready_and_forecastable():
    from app.core import datasets as D
    from app.core.datasets import checks as DC
    src = (REPO / "app/ui/static/dataset-template.csv").read_bytes()
    r = D.validate_snapshots([("dataset-template.csv", src)])
    assert r.ok, r.codes
    assert r.summary["has_population"]
    assert not any(w.startswith(DC.TOO_LITTLE_HISTORY) for w in r.warnings)
