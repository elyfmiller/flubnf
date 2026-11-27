"""The glossary and the "?" that link to it (the 2026-11-27 user review,
B7: words a newcomer cannot know on the main path, and a glossary folded
away on Methods that no "?" linked to and that lacked relWIS, quantile,
replicates and the cap).

  * Methods' Glossary card holds one entry per key of
    app/core/glossary.py KEYS, each with its own id ("g-<key>"), and the
    public site the same less the console's own; the words the review
    named are there, in plain words and the set wording;
  * every "?" or "i" on Data, Forecast, Output and Retrospective whose
    subject is a glossary word links its entry (the kit's `gloss` key, or
    each word linked with tips.term), read from the pages the server
    renders, a dataset's own pages included; every key a template or
    Python names is an entry, and an unknown one fails the page;
  * the link is the console's alone: the weekly report's kit renders none,
    and the season page passes no key when exported.

test_methods_words.py holds the card's place and order; test_tips_popups.py
the popups' behavior.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import glossary as G                       # noqa: E402
from app.core import html_page, runs, site_build         # noqa: E402
from app.ui.templating import templates                  # noqa: E402

import served_dom as SD                                  # noqa: E402

from test_datasets_ui import client, isolated, stored    # noqa: E402,F401

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "app" / "ui" / "templates"


def _flat(node, out=None):
    out = [] if out is None else out
    for k in node["kids"]:
        if not isinstance(k, str):
            out.append(k)
            _flat(k, out)
    return out


def _text(node) -> str:
    if isinstance(node, str):
        return node
    return "".join(_text(k) for k in node["kids"])


def _words(node) -> str:
    return " ".join(_text(node).split())


def _page(url: str) -> str:
    r = client.get(url)
    assert r.status_code == 200, (url, r.text[:300])
    return r.text


def _entries(html: str) -> dict:
    """{key: (word, line)} of the Glossary card."""
    els = _flat(SD.tree(html))
    card = [el for el in els if el["attrs"].get("id") == "glossary"]
    assert len(card) == 1
    inner = _flat(card[0])
    out = {}
    for i, el in enumerate(inner):
        if el["tag"] == "dt":
            ident = el["attrs"].get("id", "")
            assert ident.startswith("g-"), el["attrs"]
            dd = next(e for e in inner[i + 1:] if e["tag"] == "dd")
            out[ident[2:]] = (_words(el), _words(dd))
    return out


# ------------------------------------------------------------- the card

def test_every_key_has_its_entry_and_every_entry_its_key():
    console = _entries(_page("/methods"))
    assert set(console) == G.KEYS
    site = _entries(site_build.harvest_methods({}))
    assert set(site) == G.KEYS - G.CONSOLE_ONLY
    assert G.CONSOLE_ONLY < G.KEYS
    for key in G.KEYS:
        assert G.href(key) == f"/methods#g-{key}"
    with pytest.raises(KeyError):
        G.href("posterior")


#: the words the review named as unknown (B7's evidence: "Vintages 106 8
#: shipped", "final data, not vintage-true", "FluSight window", "replicates
#: 3", "h3 97.5%", "Before cap", relWIS) and the task's list: their entry's
#: word and what its line must say
NAMED = {
    "relwis": ("relWIS", ["weighted interval score (WIS)", "below 1 beats the baseline",
                          "FluSight baseline", "on your own data"]),
    "quantile": ("Quantile", ["23 quantiles", "median", "97.5% quantile",
                              "central 95% interval"]),
    "replicates": ("Replicates", ["Independent runs of the Liu-West filter",
                                  "own random seed", "pooled into one forecasting sample"]),
    "cap": ("Upper-tail cap", ["above the median", "0 is no cap", "Before cap",
                               "the mean of the last three reported weeks",
                               "the larger", "clip", "shrink"]),
    "vintage": ("Vintage", ["archived on one day"]),
    "vintage-true": ("Vintage-true", ["snapshot that held it"]),
    "final-data": ("Final data", ["as they read today", "revisions"]),
    "snapshot": ("Snapshot", ["as_of date", "shipped snapshot", "your own data"]),
    "reference-date": ("Reference date", ["newest week plus 7 days", "FluSight round"]),
    "round": ("FluSight round", ["reference date", "FluSight window", "11 PM Eastern"]),
    "donor": ("Donor weeks", ["within two epiweeks"]),
    "horizon": ("Horizon", ["h3 is horizon 3"]),
}


def test_the_words_the_review_named_have_plain_entries():
    entries = _entries(_page("/methods"))
    for key, (word, says) in NAMED.items():
        got_word, line = entries[key]
        assert got_word == word, key
        for s in says:
            assert s in line, (key, s)
        # one or two plain sentences, for a reader new to forecasting
        sentences = re.findall(r"[.!?](?=\s+[A-Z]|$)", line)
        assert 1 <= len(sentences) <= 2, (key, line)
    said = " ".join(line for _, line in entries.values()).lower()
    for word in ("posterior", "adapt", " track", "follow", "–", "—"):
        assert word not in said, word
    assert "liu-west filter" in said and "forecasting sample" in said


# ---------------------------------------------------- the "?" that link it

def _links(html: str) -> dict:
    """{popup id: {glossary key}} for every glossary link inside a tip's
    box or a toggletip's panel; also checks each "More in the glossary"
    line ends its box."""
    out = {}
    for el in _flat(SD.tree(html)):
        cls = el["attrs"].get("class", "").split()
        if not ({"tipbox", "uk-tt-pop"} & set(cls)):
            continue
        keys = set()
        for a in _flat(el):
            href = a["attrs"].get("href", "")
            if a["tag"] == "a" and href.startswith("/methods#g-"):
                assert "uk-term" in a["attrs"].get("class", "").split(), href
                keys.add(href.split("#g-", 1)[1])
        ends = [k for k in el["kids"] if not isinstance(k, str) or k.strip()]
        lines = [k for k in el["kids"] if isinstance(k, dict)
                 and "uk-gloss" in k["attrs"].get("class", "").split()]
        if lines:
            assert len(lines) == 1 and ends[-1] is lines[0], el["attrs"]
            assert _words(lines[0]) == "More in the glossary"
        if keys:
            out[el["attrs"]["id"]] = keys
    return out


#: page -> {popup id: the glossary keys it links}: each "?" or "i" whose
#: subject is a glossary word (a toggletip that defines several links
#: each). The Data card's own "?" and the report's cards are other work
HUB_PAGES = {
    "/data": {"tip-archive": {"vintage"}, "tip-dsup-data-about": {"snapshot"}},
    "/forecast": {"tt-fc-settings": {"vintage", "reference-date", "round",
                                     "horizon"},
                  "tt-ms-about": {"modified"}},
    "/output": {"tt-out-files": {"reference-date", "modified"}},
    "/retro": {"tt-rt-page": {"relwis"}, "tt-ms-about": {"modified"}},
}


def test_each_tip_that_names_a_glossary_word_links_its_entry():
    entries = set(_entries(_page("/methods")))
    for url, want in HUB_PAGES.items():
        got = _links(_page(url))
        assert got == want, url
        assert set().union(*got.values()) <= entries, url


def test_a_dataset_s_own_pages_link_theirs():
    """A dataset with no as_of column (final data): its view on Data, its
    Forecast form's "i" and its Replay form's "?"."""
    ds = stored()
    assert not ds.vintage_true
    pages = {
        f"/data?source={ds.id}": {"tip-ds-browse": {"final-data"}},
        f"/forecast?source={ds.id}": {
            "tt-fc-settings": {"vintage", "vintage-true", "final-data"},
            "tt-ms-about": {"modified"}},
        f"/retro?dataset={ds.id}": {"tip-rt-ds-about": {"relwis"},
                                    "tt-dsr-ms-about": {"modified"}},
    }
    for url, want in pages.items():
        got = _links(_page(url))
        for popup, keys in want.items():
            assert got.get(popup) == keys, (url, popup, got)


def test_the_results_tip_links_relwis_as_the_macro_would():
    """The run page's and Forecast's Results "?" (runs.results_tip, the
    tip macro's Python twin): its subject is the relWIS convention."""
    py = runs.results_tip({})
    macro = templates.env.from_string(
        '{% import "_tips.html" as t %}'
        '{{ t.tip("res-note", "the results", text, gloss="relwis") }}'
    ).render(text=runs.HUB_RESULTS_NOTE)
    def norm(h):
        return re.sub(r"\s+>", ">", " ".join(h.split()))
    assert norm(py) == norm(macro)
    assert 'href="/methods#g-relwis">More in the glossary</a>' in py


# ---------------------------------------------------- the kit carries it

MACRO_CALLS = {
    "tip": 't.tip("x", "the x", "Words.", gloss=k)',
    "label": 't.label("X", "x", "Words.", for_="f", gloss=k)',
    "icon_tip": 't.icon_tip("x", "the x", "warning", "Words.", gloss=k)',
    "heading": 't.heading("X", "x", "Words.", gloss=k)',
    "heading, rich": 't.heading("X", "x", "Words.", rich=True, gloss=k)',
    "toggletip": 't.toggletip("x", "the x", "Words.", gloss=k)',
    "badge": 't.badge("warn", "w", "Words.", id="x", gloss=k)',
    "alert": 't.alert("warn", "Look.", tiptext="Words.", id="x", gloss=k)',
    "stat": 't.stat("X", "1", tiptext="Words.", id="x", gloss=k)',
    "namechip": 't.namechip("X", "x", "Words.", gloss=k)',
}


@pytest.mark.parametrize("call", list(MACRO_CALLS))
def test_every_kit_explainer_ends_with_the_link_its_key_names(call):
    def render(k):
        return templates.env.from_string(
            '{% import "_tips.html" as t %}{{ ' + MACRO_CALLS[call] + " }}"
        ).render(k=k)
    html = render("quantile")
    assert _links(html) and set().union(*_links(html).values()) == {"quantile"}
    assert "More in the glossary" not in render("")
    # an unknown key fails the page instead of linking nowhere
    with pytest.raises(KeyError):
        render("posterior")


def test_term_links_one_word_and_the_report_s_kit_links_nothing():
    con = templates.env.from_string(
        '{% import "_tips.html" as t %}{{ t.term("cap", "Upper-tail cap") }}').render()
    assert con == '<a class="uk-term" href="/methods#g-cap">Upper-tail cap</a>'
    # the weekly report renders the kit in an env of its own, without the
    # console's glossary_href: the words stay, the links do not
    kit = html_page.kit_macros()
    assert str(kit.term("cap", "Upper-tail cap")) == "Upper-tail cap"
    tip = str(kit.tip("x", "the x", "Words.", gloss="cap"))
    assert "uk-gloss" not in tip and "/methods" not in tip
    assert "uk-gloss" not in str(kit.toggletip("x", "the x", "Words.", gloss="cap"))


def _keys_named(text: str) -> set:
    """Every glossary key a template or a Python file names: gloss="k",
    either branch of gloss=("a" if ... else "b"), tips.term("k", ...)."""
    out = set()
    for m in re.finditer(r'gloss=\(?((?:"[\w-]*"|\s|if|else|not|[\w.]+)+)\)?', text):
        out |= set(re.findall(r'"([\w-]+)"', m.group(1)))
    out |= set(re.findall(r'tips\.term\("([\w-]+)"', text))
    return out


def test_every_key_named_anywhere_is_an_entry():
    named = set()
    for p in sorted(TEMPLATES.glob("*.html")):
        if p.name != "_tips.html":
            named |= _keys_named(p.read_text(encoding="utf-8"))
    for top in ("app", "flubnf"):
        for p in sorted((REPO / top).rglob("*.py")):
            if "tests" not in p.parts:
                named |= _keys_named(p.read_text(encoding="utf-8"))
    assert named and named <= G.KEYS, named - G.KEYS
    # and the pages above link every key a "?" names on them
    assert {"vintage", "snapshot", "relwis", "round", "modified"} <= named


def test_the_exported_season_page_names_no_key():
    """The season report is retro_season.html rendered with `export`: a
    saved file cannot reach Methods, so each key there is the console's
    branch only, and no word is linked with tips.term."""
    src = (TEMPLATES / "retro_season.html").read_text(encoding="utf-8")
    calls = re.findall(r"gloss=([^,)]+\)?)", src)
    assert calls, "the season page's \"i\" links relWIS"
    for c in calls:
        assert c.startswith('("" if export else "'), c
    assert "tips.term(" not in src
