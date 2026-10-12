"""Every download in the console goes one way: a link with the download
attribute.

In the macOS window pywebview turns such a click into a WebKit download
with a save panel (flubnf/window_downloads.py makes it replace the file
the user chose). A link without the attribute, or a script that sets
window.location, takes pywebview's other path instead: the file may open
inside the window, or be fetched again and moved into place, a move that
also keeps an existing file without a word. So every link to a route that
answers with an attachment carries the attribute, and no script navigates
to one.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

UI = Path(__file__).resolve().parents[1] / "ui"
TEMPLATES = sorted((UI / "templates").glob("*.html"))
#: the console's own scripts (plotly is vendored)
SCRIPTS = sorted(p for p in (UI / "static").glob("*.js")
                 if not p.name.endswith(".min.js"))

#: the routes that answer with an attachment, as their links spell them
DOWNLOAD_ROUTES = (
    r"/output/download\?",                    # a submission CSV, an export
    r"/report/download(\?|$)",                # the weekly report, any run
    r"^/retro/[^/]+/report(\{\{[^}]*\}\})?$",  # the season report
    r"^/retro/[^/]+/export(\{\{[^}]*\}\})?$",  # the replay bundle
    r"^/sandbox/(models|runs)/[^/]+/download$",  # the sandbox zips
)


def _is_download(href: str) -> bool:
    return any(re.search(p, href) for p in DOWNLOAD_ROUTES)


def _anchors(text: str):
    """(tag, href) of each <a ...> start tag (a Jinja expression inside an
    attribute holds no '>' in these templates)."""
    for m in re.finditer(r"<a\b[^>]*>", text, re.S):
        tag = m.group(0)
        h = re.search(r'\bhref="([^"]*)"', tag)
        if h:
            yield tag, h.group(1)


def test_the_route_patterns_know_the_download_routes():
    for href in ("/output/download?path={{ path | urlencode }}",
                 "/output/report/download",
                 "/output/report/download?date=2098-01-03",
                 "/runs/{{ run_id }}/report/download",
                 "/retro/{{ season }}/report{{ aq }}",
                 "/retro/{{ season }}/export{{ aq }}",
                 "/sandbox/models/{{ name }}/download",
                 "/sandbox/runs/{{ res.run_id }}/download"):
        assert _is_download(href), href
    for href in ("/output/report", "/output/report?date=2098-01-03",
                 "/runs/{{ run_id }}/report", "/runs/{{ run_id }}",
                 "/api/retro/{{ season }}/report_status", "/retro/{{ s }}",
                 "/output", "/static/dataset-template.csv"):
        assert not _is_download(href), href


def test_every_download_link_carries_the_download_attribute():
    found, bare = [], []
    for t in TEMPLATES:
        for tag, href in _anchors(t.read_text(encoding="utf-8")):
            if _is_download(href):
                found.append((t.name, href))
                if not re.search(r"\sdownload(=|[\s>])", tag):
                    bare.append((t.name, href))
    assert not bare, f"download links without the attribute: {bare}"
    # the places that offer a file: Output (each file, the latest report,
    # an earlier week's), a run (its report and files), a dataset run's
    # exports, the season report and the sandbox zips
    names = {n for n, _ in found}
    assert {"output.html", "run.html", "_dataset_run.html",
            "retro_season.html", "sandbox.html"} <= names
    hrefs = {h for _, h in found}
    assert "/output/report/download?date={{ archive_dates[0][0] }}" in hrefs
    # a file row (Output and the run page share _filerow.html)
    assert ("_filerow.html", "/output/download?path={{ path | urlencode }}") \
        in found


def test_no_script_navigates_to_a_download():
    """window.location, location.href or window.open on a download route
    would bypass the attribute; a script that starts a download builds a
    link with the attribute (retro_season.html's download())."""
    nav = re.compile(r"(?:window\.)?location(?:\.href)?\s*=(?!=)[^;\n]*"
                     r"|location\.(?:assign|replace)\([^)\n]*\)"
                     r"|window\.open\([^)\n]*\)")
    offenders = []
    for p in TEMPLATES + SCRIPTS:
        for m in nav.finditer(p.read_text(encoding="utf-8")):
            if re.search(r"/download|/export|/retro/[^']*'\s*\+[^)]*report\b",
                         m.group(0)):
                offenders.append((p.name, m.group(0)))
    assert not offenders, offenders
    season = (UI / "templates" / "retro_season.html").read_text(
        encoding="utf-8")
    helper = season.split("function download(href,name){", 1)[1][:200]
    assert "a.download=name" in helper and "a.click()" in helper
