"""'Try the template' beside the Template CSV link (UX review F37,
package P4): a button that never submits (type=button), hidden until
static/dataset_upload.js finds the browser can hold a fetched file in the
input, naming the file it fetches; that file is served and checks as
ready, so one click shows a preview with no download and no dialog."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from test_dataset_upload_box import DOM_STUB, NODE    # noqa: E402
from test_datasets_ui import (TEMPLATE, client,        # noqa: E402,F401
                              isolated, stored)

STATIC = TEMPLATE.parent
BUTTON = ('<button type="button" class="quiet" data-try-template '
          'data-src="/static/dataset-template.csv" hidden>Try the template'
          '</button>')


def test_every_upload_box_offers_the_button_beside_the_link():
    pages = {"/data": "data", "/forecast?tab=own": "forecast",
             "/retro?tab=own": "replay"}
    for url, where in pages.items():
        html = client.get(url).text
        box = html[html.index(f'id="dsup-{where}"'):]
        box = box[:box.index("</form>")]
        assert BUTTON in box, url
        links = re.search(r'<div class="dt-zonelinks">(.*?)</div>', box,
                          re.S).group(1)
        assert 'href="/static/dataset-template.csv"' in links
        assert BUTTON in links
    # a stored dataset's Retrospective tab folds the box: still there
    ds = stored(TEMPLATE.read_bytes(), "Kids")
    assert BUTTON in client.get(f"/retro?dataset={ds.id}").text


def test_what_the_button_fetches_is_served_and_checks_ready():
    src = re.search(r'data-src="([^"]+)"', BUTTON).group(1)
    r = client.get(src)
    assert r.status_code == 200 and r.content == TEMPLATE.read_bytes()
    j = client.post("/data/datasets/check",
                    files={"file": ("dataset-template.csv", r.content,
                                    "text/csv")},
                    data={"kind": ""}).json()
    assert j["ok"] and j["status"] == "Ready to use: 3 groups, 143 weeks."
    assert j["name"] == "dataset-template"


# --------------------------------- the button's script, run under node

#: the upload box's DOM stub (test_dataset_upload_box), plus the button and
#: a File, a DataTransfer and the template's GET, each switchable
TRY_STUB = r"""
var tryBtn = new El({hidden: true, disabled: false});
tryBtn.attrs['data-src'] = '/static/dataset-template.csv';
tryBtn.getAttribute = function (k) {
  return k in this.attrs ? this.attrs[k] : null; };
form.q['[data-try-template]'] = tryBtn;
var gets = [];
function File(parts, n, o) { this.parts = parts; this.name = n;
                             this.type = (o || {}).type; }
var DataTransfer = HOLD ? function () {
  var fs = []; this.files = fs;
  this.items = {add: function (f) { fs.push(f); }};
} : undefined;
var checkPost = fetch;
fetch = function (url, opts) {
  if (opts) return checkPost(url, opts);
  gets.push(url);
  return Promise.resolve(SERVED ? {ok: true, status: 200, blob: function () {
    return Promise.resolve('date,target_group,value'); }}
    : {ok: false, status: 404});
};
"""


def _try(hold: bool = True, served: bool = True, click: bool = True) -> dict:
    """dataset_upload.js on the upload box's stub, with or without
    DataTransfer (`hold`) and the template served or not; the button
    clicked once. What it showed, fetched, put in the input and posted."""
    src = (STATIC / "dataset_upload.js").read_text(encoding="utf-8")
    prog = ("var HOLD = %s, SERVED = %s;\n" % (str(hold).lower(),
                                               str(served).lower())
            + DOM_STUB + TRY_STUB + src
            + "\n(async function () {\n"
            + ("tryBtn.fire('click'); await settle(); await settle();\n"
               if click else "")
            + "await settle();\nconsole.log(JSON.stringify({"
            "hidden: tryBtn.hidden, listens: !!(tryBtn.on.click || []).length,"
            " disabled: tryBtn.disabled, gets: gets, posted: posted,"
            " held: (input.files || []).map(function (f) { return f.name; }),"
            " shown: out.innerHTML, status: status.textContent || ''}));"
            "\n})();\n")
    out = subprocess.run([NODE, "-e", prog], capture_output=True, text=True,
                         timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not Path(NODE).exists(), reason="node not available")
def test_a_click_holds_the_template_and_checks_it():
    got = _try()
    assert got["hidden"] is False and got["listens"]
    assert got["gets"] == ["/static/dataset-template.csv"]
    # in the one-CSV input (a native submit posts it), then checked
    assert got["held"] == ["dataset-template.csv"]
    assert [p["file"] for p in got["posted"]] == ["dataset-template.csv"]
    assert got["disabled"] is False


@pytest.mark.skipif(not Path(NODE).exists(), reason="node not available")
def test_without_a_way_to_hold_a_file_the_button_stays_hidden():
    got = _try(hold=False)
    assert got["hidden"] is True and not got["listens"]
    assert got["gets"] == [] and got["posted"] == [] and got["held"] == []


@pytest.mark.skipif(not Path(NODE).exists(), reason="node not available")
def test_a_template_that_cannot_be_read_points_to_the_link():
    got = _try(served=False)
    assert got["gets"] == ["/static/dataset-template.csv"]
    assert got["posted"] == [] and got["held"] == []
    msg = ("The template could not be read; use the Template CSV link "
           "instead.")
    assert got["shown"] == msg and got["status"] == msg
    assert got["disabled"] is False
