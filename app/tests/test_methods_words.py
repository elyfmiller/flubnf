"""Models and Methods (UX review F41 and F67; package P12).

  * a model tab opens on its own actions: the Quick run and Forecasts
    cards come right under the model's header card, before the drawings
    and the model source, which still work where they now sit; the
    research view (/model/pf2s) has neither card and keeps its order;
  * Methods' Purpose card ends with one closed fold, "Words used here":
    the working words other tabs use, one labelled line each. Each word is
    one a console page shows outside the fold, none is a label the page
    already defines, and the wording rules hold (a forecasting sample,
    never a posterior; the filter never adapts, tracks or follows). The
    public site gets the fold without the console's own words, and says
    nothing of a ledger, shard or workroot.

Every check reads the page the server renders. Run's place in the window
at 390x844 was checked by hand in a scratch console: no browser driver is
installed here.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import runs as runs_mod                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core import site_build                          # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402
from app.ui.server import app as srv                     # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_sandbox_guide import _finish, box              # noqa: E402,F401

client = TestClient(srv)
needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

#: the fold's rows that only the console shows (the site has no runs,
#: no Storage tab and no Model settings)
CONSOLE_ONLY = {"modified settings", "workroot", "run ledger"}


# ------------------------------------------------------------ the served DOM

def _text(node) -> str:
    if isinstance(node, str):
        return node
    if node["tag"] in ("script", "style"):
        return ""
    return "".join(_text(k) for k in node["kids"])


def _flat(node, out=None):
    """Every element in document order."""
    out = [] if out is None else out
    for k in node["kids"]:
        if not isinstance(k, str):
            out.append(k)
            _flat(k, out)
    return out


def _find(root, pred):
    return [i for i, el in enumerate(_flat(root)) if pred(el)]


def _by_id(root, ident):
    return _find(root, lambda el: el["attrs"].get("id") == ident)


def _h2(root, words):
    return _find(root, lambda el: el["tag"] == "h2"
                 and " ".join(_text(el).split()) == words)


def _classed(root, tag, cls):
    return _find(root, lambda el: el["tag"] == tag
                 and cls in el["attrs"].get("class", "").split())


def _words_fold(root):
    hits = [el for el in _flat(root) if el["attrs"].get("id") == "mt-words"]
    assert len(hits) == 1, len(hits)
    return hits[0]


def _terms(fold) -> list:
    return [" ".join(_text(el).split())
            for el in _flat(fold) if el["tag"] == "dt"]


def _shown(node, skip_id="mt-words") -> str:
    """What a reader meets on a page: its text and the names its
    aria-label and title attributes give, with scripts, styles and the
    `skip_id` subtree left out."""
    out = []

    def walk(n):
        for k in n["kids"]:
            if isinstance(k, str):
                out.append(k)
            elif k["tag"] in ("script", "style") \
                    or k["attrs"].get("id") == skip_id:
                continue
            else:
                out.extend(k["attrs"].get(a, "") for a in ("aria-label", "title"))
                walk(k)
    walk(node)
    return " ".join(" ".join(out).split())


def _page(url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.text[:300])
    return r.text


# ------------------------------------------------------- the model tabs (F41)

@pytest.mark.parametrize("url, mechs", [("/models", 2),
                                        ("/model/analogue", 1)])
def test_a_model_tab_opens_on_its_quick_run_and_forecasts(url, mechs):
    root = SD.tree(_page(url))
    hero = _by_id(root, "h-md-model")
    quick, fc = _by_id(root, "h-md-quick"), _by_id(root, "h-md-fc")
    drawn = _h2(root, "How the forecast is made")
    cards = _classed(root, "div", "md-mech")
    assert len(hero) == len(quick) == len(fc) == len(drawn) == 1
    # the drawings print once, under the model's own two cards
    assert len(cards) == mechs
    assert hero[0] < quick[0] < fc[0] < cards[0] < drawn[0]
    # the Run button is the Quick run card's, above every drawing
    run = _find(root, lambda el: el["tag"] == "button"
                and _text(el).startswith("Run ") and _text(el).endswith(" only"))
    assert len(run) == 1 and quick[0] < run[0] < cards[0]
    src = _classed(root, "details", "bngl")
    if url == "/models":
        assert len(src) == 1 and cards[-1] < src[0]
    else:
        assert src == []
    # the skip link still lands on the Quick run heading
    skip = _find(root, lambda el: el["tag"] == "a"
                 and el["attrs"].get("href") == "#h-md-quick")
    assert len(skip) == 1 and skip[0] < hero[0]


def test_the_research_view_keeps_its_order():
    root = SD.tree(_page("/model/pf2s"))
    for gone in ("h-md-quick", "h-md-fc", "mfan"):
        assert _by_id(root, gone) == [], gone
    hero = _by_id(root, "h-md-model")
    drawn = _h2(root, "The two circuits the filter fits")
    src = _classed(root, "details", "bngl")
    research = _by_id(root, "research-run")
    assert len(hero) == len(drawn) == len(src) == len(research) == 1
    assert hero[0] < drawn[0] < src[0] < research[0]


@needs_js
def test_the_model_source_buttons_work_where_they_now_sit(tmp_path):
    """The source block's own script, run on the served page: the
    download link is built from the text shown, and Copy copies it."""
    html = _page("/models")
    script = re.search(r'<details class="card bngl">.*?</details>\s*'
                       r"<script>(.*?)</script>", html, re.S)
    assert script, "the source block's script follows it"
    # served hidden, with no target until the script builds one
    dl = [el for el in _flat(SD.tree(html))
          if el["attrs"].get("id") == "md-src-dl"]
    assert len(dl) == 1 and "hidden" in dl[0]["attrs"]
    assert "href" not in dl[0]["attrs"]
    out = SD.run(tmp_path, html, [], """
      var dl = document.getElementById('md-src-dl'),
          pre = document.querySelector('details.bngl > pre'),
          said = document.getElementById('md-src-said');
      document.getElementById('md-src-copy').fire('click');
      return {hidden: dl.hidden,
              href: decodeURIComponent(dl.href.split(',').slice(1).join(',')) === pre.textContent,
              scheme: dl.href.split(',')[0],
              copied: COPIED === pre.textContent && pre.textContent.length > 100,
              said: said.textContent};
    """, prelude=(
        "var COPIED = null;\n"
        "var navigator = {clipboard: {writeText: function (t) {\n"
        "  COPIED = t; return {then: function (ok) { ok(); }}; }}};\n"
        + script.group(1)))
    assert out == {"hidden": False, "href": True,
                   "scheme": "data:text/plain;charset=utf-8",
                   "copied": True, "said": "Copied"}


# -------------------------------------------------- Methods' words (F67)

def test_the_words_are_one_closed_fold_at_the_end_of_purpose():
    root = SD.tree(_page("/methods"))
    purpose = [el for el in _flat(root) if el["attrs"].get("id") == "purpose"]
    assert len(purpose) == 1
    fold = _words_fold(purpose[0])
    assert fold["tag"] == "details" and "open" not in fold["attrs"]
    assert fold["attrs"]["class"].split() == ["uk-fold", "mt-fold"]
    summary = [el for el in fold["kids"] if not isinstance(el, str)][0]
    assert " ".join(_text(summary).split()) == "Words used here"
    # in the card's folds row, as the other Methods folds, and the card's
    # last element
    holder = [el for el in purpose[0]["kids"] if not isinstance(el, str)][-1]
    assert holder["attrs"].get("class") == "mt-folds"
    assert fold in holder["kids"]
    # one labelled line per word, with no mark and no id of its own
    lists = [el for el in _flat(fold) if el["tag"] == "dl"]
    assert len(lists) == 1
    assert lists[0]["attrs"]["class"].split() == ["uk-stats", "uk-stats--kv"]
    for el in _flat(fold):
        assert "id" not in el["attrs"], el["attrs"]
        assert el["tag"] != "button", el["attrs"]


def test_each_word_is_defined_once_in_the_set_wording():
    root = SD.tree(_page("/methods"))
    fold = _words_fold(root)
    terms = _terms(fold)
    assert len(terms) >= 10
    low = [t.lower() for t in terms]
    assert len(set(low)) == len(low), terms
    assert CONSOLE_ONLY <= set(low)
    # no word the page already gives as a labelled value (Scored cell and
    # relWIS are the Scoring card's)
    inside = {id(el) for el in _flat(fold)}
    page_labels = {" ".join(_text(el).split()).lower()
                   for el in _flat(root)
                   if el["tag"] == "dt" and id(el) not in inside}
    assert "scored cell" in page_labels and "relwis" in page_labels
    assert not set(low) & page_labels, set(low) & page_labels
    said = " ".join(_text(fold).split())
    assert "Liu-West filter" in said and "forecasting sample" in said.lower()
    for word in ("posterior", "adapt", "track", "follow", "–", "—"):
        assert word not in said.lower(), word


@pytest.fixture
def modified_run(monkeypatch):
    """The newest run made with a Model setting changed (as
    test_models_tab fakes it), so /models badges it."""
    res = {"forecast_date": "2098-11-14", "observed": {},
           "models": {"pf": {"Ohio": {"1": {"0.1": 1.0, "0.5": 2.0,
                                            "0.9": 3.0}}}},
           "spec": json.dumps({"extra": {"knobs": {"oracle.w": 0.25}}})}
    monkeypatch.setattr(ui_shared, "_latest_results",
                        lambda **kw: ("20981114T093100-abcdef", res))


def test_each_word_is_one_a_console_page_shows(box, modified_run, tmp_path,
                                               monkeypatch):
    """Every word in the fold is one a reader meets on a console page
    outside it, so the fold never defines a word the console does not
    use. Some show only in a state: a sandbox fit's results (the
    forecasting sample), a run with modified settings, and a run's folder
    on disk (Storage's Run workroots)."""
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example", particles=200, jitter=0.2, seed=3)
    _finish(w)
    urls = ["/data", "/forecast", "/output", "/retro", "/storage",
            "/sandbox", f"/sandbox?model=kinetics_example&run={w.name}",
            "/models", "/model/analogue", "/methods"]
    seen = {u: _shown(SD.tree(_page(u))).lower() for u in urls}
    # Storage lists the runs' folders under On disk once one is there: a
    # state of its own holding one run's, the listing recounted before
    # and after (the suite's state is never written)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    wr = tmp_path / "state" / "workroots" / "20981114T093100-abcdef"
    wr.mkdir(parents=True)
    (wr / "run.log").write_text("ok\n")
    ui_shared._invalidate_scans()
    try:
        page = _page("/storage")
    finally:
        ui_shared._invalidate_scans()
    assert 'id="h-st-wr"' in page
    seen["/storage, a run on disk"] = _shown(SD.tree(page)).lower()
    terms = _terms(_words_fold(SD.tree(_page("/methods"))))
    missing = [t for t in terms
               if not any(t.lower() in text for text in seen.values())]
    assert missing == [], missing


def test_the_public_methods_has_the_fold_without_the_console_words():
    site = site_build.harvest_methods({})
    root = SD.tree(site)
    fold = _words_fold(root)
    terms = [t.lower() for t in _terms(fold)]
    console = [t.lower() for t in _terms(_words_fold(SD.tree(_page("/methods"))))]
    assert len(set(terms)) == len(terms)
    assert terms == [t for t in console if t not in CONSOLE_ONLY]
    assert not CONSOLE_ONLY & set(terms)
    # nothing on the public page names the console's records or folders
    low = site.lower()
    for word in ("ledger", "shard", "workroot", "posterior"):
        assert word not in low, word
    # every run is reproducible from its record, in words the site can use
    assert "is seeded and reproducible from its run record" in " ".join(site.split())
