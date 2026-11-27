"""Where the console's words are defined: the Glossary card at the end of
the Methods page (templates/methods.html), one entry per word, each with
its own id, "g-<key>", for a link to land on.

A "?" or "i" whose subject is one of these words ends with a link to its
entry (the kit's `gloss` key, templates/_tips.html), and a rich explainer
that defines several links each word (tips.term). This module is that
link's address: `href` is the console Jinja env's `glossary_href` global
(app/ui/templating.py), and Python that builds a tip's markup itself
(app/core/runs.py _tip) calls it too. An unknown key raises, so a page
that names one fails to render rather than linking nowhere;
app/tests/test_glossary.py holds KEYS to the entries the served Methods
page carries.

Only the console links here. The weekly report renders the kit's macros
without the global and the season report without the keys, so a saved
copy carries no link it could not follow; the public site rewrites
/methods#g-<key> to its own same-page anchor (site_build.harvest_methods).
"""
from __future__ import annotations

#: the page that holds the glossary
PAGE = "/methods"

#: every entry's key, as Methods' Glossary card writes it (the card's
#: order: alphabetical by the word). CONSOLE_ONLY are the console's own
#: words, which the public site leaves out
KEYS = frozenset({
    "abstain", "donor", "final-data", "forecasting-sample", "round",
    "groundhog", "horizon", "jurisdiction", "liu-west", "modified",
    "oracle-step", "quantile", "reference-date", "relwis", "replicates",
    "ledger", "snapshot", "cap", "vintage", "vintage-true", "workroot",
})
CONSOLE_ONLY = frozenset({"modified", "ledger", "workroot"})


def href(key: str) -> str:
    """The address of `key`'s entry: "/methods#g-<key>"."""
    if key not in KEYS:
        raise KeyError(f"no glossary entry {key!r} (app/core/glossary.py KEYS)")
    return f"{PAGE}#g-{key}"
