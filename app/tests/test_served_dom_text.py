"""served_dom's MiniDOM itself: textContent with nested elements, and a
form's elements.

textContent read `out` before its recursive call added a child
element's text, then wrote the stale value back, so every nested
element's text was dropped: a test reading a line built of spans saw only
its loose text. A form's elements (namedItem) is what
retro_progress.js reads its fields by.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import served_dom as SD                                    # noqa: E402

needs_js = pytest.mark.skipif(not SD.HAVE_JS,
                              reason="no JavaScript engine (jsc or node)")

PAGE = """<!doctype html><html><body>
<div id="line">one <b>two <i>three</i></b> four<span></span><em>five</em></div>
<p id="flat">plain</p>
<ul id="list"><li>a</li><li><a href="#">b</a> c</li></ul>
<select id="pick"><option value="x">The <b>first</b></option>
<option>  second   <i>one</i> </option></select>
<form id="fm"><input name="n" value="7"><select name="s"><option>p</option>
<option selected>q</option></select><textarea name="t">long text</textarea>
<fieldset><input id="by-id" value="i"></fieldset>
<input type="checkbox" name="box"><input type="checkbox" name="box"></form>
<div id="notform"><input name="n"></div>
</body></html>"""


@needs_js
def test_text_content_keeps_nested_text(tmp_path):
    got = SD.run(tmp_path, PAGE, [], """
      function t(id) { return document.getElementById(id).textContent; }
      var line = document.getElementById("line");
      var out = [t("line"), t("flat"), t("list"),
                 document.querySelector("#pick option").textContent];
      // the setter still replaces every child, nested ones included
      line.querySelector("b").textContent = "TWO";
      out.push(t("line"));
      line.textContent = "new";
      out.push(t("line"), line.querySelectorAll("b").length);
      // an option without a value reads its text, nested text included
      out.push(document.getElementById("pick").options[1].value);
      return out;""")
    assert got == ["one two three fourfive", "plain", "ab c",
                   "The first", "one TWO fourfive", "new", 0, "second one"]


@needs_js
def test_a_forms_elements_by_name_or_id(tmp_path):
    got = SD.run(tmp_path, PAGE, [], """
      var fm = document.getElementById("fm"), el = fm.elements;
      var out = [el.length, el.namedItem("n").value, el.namedItem("s").value,
                 el.namedItem("t").value, el.namedItem("by-id").value,
                 el.namedItem("nothing"),
                 document.getElementById("notform").elements === undefined];
      try { el.namedItem("box"); out.push("no throw"); }
      catch (e) { out.push(String(e.message)); }
      return out;""")
    assert got == [7, "7", "q", "long text", "i", None, True,
                   'MiniDOM: several controls named "box"']
