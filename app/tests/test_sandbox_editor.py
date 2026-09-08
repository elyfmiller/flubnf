"""The sandbox code editor (app/ui/static/bngl-editor.js and .css).

Hub-free and engine-free, like test_sandbox.py: the two static files are
served with their content types; the editor page marks the three
textareas for the script and keeps their names, rows and contents; the
script and stylesheet keep the console's rules (no dashes, no colour
literals, no external assets); and the pure text functions run for real
under JavaScriptCore where jsc ships (skipped cleanly where it does not).
"""
import html as H
import json
import re
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
JS = STATIC / "bngl-editor.js"
CSS = STATIC / "bngl-editor.css"
TEMPLATE = Path(__file__).resolve().parents[1] / "ui" / "templates" / "sandbox.html"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
needs_jsc = pytest.mark.skipif(not JSC.is_file(),
                               reason="JavaScriptCore jsc not available")


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A sandbox rooted in tmp_path, with BNG2.pl faked to write m.net."""
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "MODELS", tmp_path / "sandbox" / "models")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")

    def fake_netgen(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if "broken" not in (cwd / "m.bngl").read_text():
            (cwd / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="ABORT: bad rule\n", stderr="",
                                     returncode=0)
    monkeypatch.setattr(sb.subprocess, "run", fake_netgen)
    srv._status["running"] = None
    srv._sandbox_status["running"] = None
    return tmp_path / "sandbox"


def _js(tmp_path, expr):
    """Evaluate one expression against the editor's exported functions."""
    drv = tmp_path / "driver.js"
    drv.write_text("var E = BnglEditor;\n"
                   "print(JSON.stringify((function(){ return " + expr + "; })()));\n")
    out = subprocess.run([str(JSC), str(JS), str(drv)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------ the files

def test_the_editor_files_are_served_with_their_content_types():
    r = client.get("/static/bngl-editor.js")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0] in ("text/javascript",
                                                       "application/javascript")
    assert "BnglEditor" in r.text and "textarea.code-editor" in r.text
    r = client.get("/static/bngl-editor.css")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0] == "text/css"
    assert ".ce textarea.code-editor" in r.text


def test_the_editor_keeps_the_consoles_rules():
    js, css = JS.read_text(encoding="utf-8"), CSS.read_text(encoding="utf-8")
    for src in (js, css):
        assert "\u2013" not in src and "\u2014" not in src   # no dashes
        assert "http://" not in src and "https://" not in src  # self-hosted
    # colours only through the page's tokens: no literal colours anywhere
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.search(r"\brgba?\(|\bhsla?\(", css)
    assert not re.search(r"\.style\.(color|background)", js)
    for tok in ("--ink", "--mut", "--accent-ink", "--slate", "--ok", "--bad",
                "--bg", "--line"):
        assert "var(" + tok in css, tok
    # no build step: plain ES5 syntax, one file, initialised on load
    assert "=>" not in js and "`" not in js
    assert not re.search(r"^\s*(const|let|class|async)\s", js, flags=re.M)
    assert "DOMContentLoaded" in js and "themechange" in js
    assert "fontsizechange" in js
    assert len(js.splitlines()) <= 450


# ------------------------------------------------------------- the page

def test_the_editor_page_marks_the_three_textareas(box):
    sb.add_example("sihrs_example")
    page = client.get("/sandbox?model=sihrs_example").text
    assert '<link rel="stylesheet" href="/static/bngl-editor.css">' in page
    assert '<script defer src="/static/bngl-editor.js"></script>' in page
    assert '<script src="/static/plotly.min.js"></script>' in page    # still there
    tags = re.findall(r"<textarea([^>]*)>(.*?)</textarea>", page, flags=re.S)
    want = {"model_bngl": ("bngl", "18", "model.bngl"),
            "data_exp": ("exp", "8", "data.exp"),
            "priors_conf": ("conf", "8", "priors.conf")}
    files = sb.read_model("sihrs_example")
    seen = {}
    for attrs, body in tags:
        name = re.search(r'name="([^"]+)"', attrs).group(1)
        if name not in want:
            continue
        lang, rows, fname = want[name]
        assert 'class="code-editor"' in attrs, name
        assert f'data-lang="{lang}"' in attrs, name
        assert f'rows="{rows}"' in attrs, name
        assert 'spellcheck="false"' in attrs, name
        assert H.unescape(body) == files[fname], name        # content untouched
        seen[name] = True
    assert sorted(seen) == sorted(want)
    # the source keeps the Jinja expressions the form posts
    src = TEMPLATE.read_text(encoding="utf-8")
    for name, (_, _, fname) in want.items():
        assert f'name="{name}"' in src and f'{{{{ editing["{fname}"] }}}}' in src


# ------------------------------------------- the text functions, for real

@needs_jsc
def test_highlighting_colours_each_language(tmp_path):
    bngl = ("# a comment (with a bracket)\\nbegin model\\nbegin reaction rules\\n"
            "S() + I() -> I() + I()   beta()/N\\nR() <-> S() omega\\n"
            "end reaction rules\\nend model\\nbegin parameters\\n"
            "Reff__FREE 1.20\\ni0 2.70386837e-04\\nbeta0 H2O\\nend parameters\\n"
            "begin actions\\ngenerate_network({overwrite=>1})\\n"
            "simulate({suffix=>\\\"flu\\\"})\\nend actions\\n")
    h = _js(tmp_path, f"E.highlight('{bngl}', 'bngl', null)")
    assert '<span class="ce-c"># a comment (with a bracket)</span>' in h
    assert '<span class="ce-k">begin reaction rules</span>' in h
    assert '<span class="ce-k">end model</span>' in h
    assert '<span class="ce-r">-&gt;</span>' in h and '<span class="ce-r">&lt;-&gt;</span>' in h
    assert '<span class="ce-f">Reff__FREE</span> <span class="ce-n">1.20</span>' in h
    assert '<span class="ce-n">2.70386837e-04</span>' in h
    assert "beta0 H2O" in h                                  # digits in names stay plain
    assert '<span class="ce-fn">beta</span>()' in h
    assert '<span class="ce-a">generate_network</span>(' in h
    assert '<span class="ce-a">simulate</span>(' in h
    assert h.endswith("</span>\n ")                          # the trailing line keeps its height
    exp = _js(tmp_path, "E.highlight('# time H_weekly\\n0 8.000000\\n1 10.5', 'exp', null)")
    assert exp == ('<span class="ce-c"># time H_weekly</span>\n'
                   '<span class="ce-n">0</span> <span class="ce-n">8.000000</span>\n'
                   '<span class="ce-n">1</span> <span class="ce-n">10.5</span>')
    conf = _js(tmp_path, "E.highlight('# p\\nuniform_var = k__FREE 0.05 2.0\\n"
                         "pf_cumulative_observable = Hobs', 'conf', null)")
    assert '<span class="ce-v">uniform_var</span> = <span class="ce-f">k__FREE</span>' in conf
    assert '<span class="ce-key">pf_cumulative_observable</span> = Hobs' in conf
    assert '<span class="ce-n">0.05</span>' in conf
    # text is escaped, never interpreted
    assert _js(tmp_path, "E.highlight('<b>&', 'exp', null)") == "&lt;b&gt;&amp;"


@needs_jsc
def test_brackets_match_outside_comments(tmp_path):
    assert _js(tmp_path, "E.bracketMatch('f(a(b)) # (x', 7)") == {"pos": [1, 6], "ok": True}
    assert _js(tmp_path, "E.bracketMatch('f(a(b)) # (x', 1)") == {"pos": [1, 6], "ok": True}
    assert _js(tmp_path, "E.bracketMatch('f(a(b) # (x', 1)") == {"pos": [1], "ok": False}
    assert _js(tmp_path, "E.bracketMatch('abc', 1)") is None
    assert _js(tmp_path, "E.bracketMatch('# (a)', 3)") is None
    h = _js(tmp_path, "E.highlight('f(a)', 'bngl', E.bracketMatch('f(a)', 2))")
    assert h == ('<span class="ce-fn">f</span><span class="ce-brk">(</span>a'
                 '<span class="ce-brk">)</span>')
    h = _js(tmp_path, "E.highlight('f(a', 'bngl', E.bracketMatch('f(a', 2))")
    assert '<span class="ce-brk-bad">(</span>' in h


@needs_jsc
def test_line_edits_indent_outdent_comment_and_keep_indentation(tmp_path):
    r = _js(tmp_path, "E.indentLines('a\\n  b\\nc', 0, 5, false)")
    assert r["text"] == "  a\n    b\nc" and (r["start"], r["end"]) == (2, 9)
    assert (r["from"], r["to"], r["block"]) == (0, 5, "  a\n    b")
    r = _js(tmp_path, "E.indentLines('a\\n  b\\nc', 3, 3, true)")
    assert r["text"] == "a\nb\nc" and (r["start"], r["end"]) == (2, 2)
    r = _js(tmp_path, "E.indentLines('\\tx', 1, 1, true)")
    assert r["text"] == "x" and (r["start"], r["end"]) == (0, 0)
    # a selection ending just after a newline leaves the next line alone
    r = _js(tmp_path, "E.indentLines('a\\nb\\nc', 0, 4, false)")
    assert r["text"] == "  a\n  b\nc"
    r = _js(tmp_path, "E.commentLines('a\\n\\n  b\\n', 0, 7)")
    assert r["text"] == "# a\n\n  # b\n" and (r["start"], r["end"]) == (2, 11)
    r = _js(tmp_path, "E.commentLines('# a\\n\\n  # b\\n', 0, 10)")
    assert r["text"] == "a\n\n  b\n" and (r["start"], r["end"]) == (0, 6)
    r = _js(tmp_path, "E.commentLines('#a\\n# b', 0, 5)")           # both forms come off
    assert r["text"] == "a\nb"
    r = _js(tmp_path, "E.commentLines('a\\n# b', 0, 5)")            # mixed: all get one
    assert r["text"] == "# a\n# # b"
    assert _js(tmp_path, "E.commentLines('', 0, 0)")["text"] == "# "
    assert _js(tmp_path, "E.newlineIndent('  ab\\n\\tcd', 4)") == "\n  "
    assert _js(tmp_path, "E.newlineIndent('  ab', 1)") == "\n "
    assert _js(tmp_path, "E.newlineIndent('\\n  x', 0)") == "\n"
    assert _js(tmp_path, "E.lineCol('ab\\ncd', 4)") == {"line": 2, "col": 2}
    assert _js(tmp_path, "E.lineCol('ab', 0)") == {"line": 1, "col": 1}
    assert _js(tmp_path, "E.tokenize('H2O beta0 2*pi .5', 'bngl')") == [[10, 11, "n"], [15, 17, "n"]]
