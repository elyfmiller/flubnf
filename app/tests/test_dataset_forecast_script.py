"""A dataset's Forecast page carries the same inline script values as the
hub's: forecast.html reads RASIDE (the weeks each member set aside), and
before this fix the dataset page left it empty, `const RASIDE = ;`, a
syntax error that stopped the fan and data-panel script on every dataset
page (G19)."""
import re
import shutil
import subprocess

import pytest

from test_datasets_ui import client, isolated, stored        # noqa: F401

# compiles a script body without running it: new Function throws the
# SyntaxError the browser would raise on loading it
PARSE = ("const src = require('fs').readFileSync(process.argv[2], 'utf8');\n"
         "new Function(src);\n")


def _inline_scripts(page: str) -> list[str]:
    bodies = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>",
                        page, flags=re.S)
    return [body for attrs, body in bodies
            if body.strip() and "json" not in attrs]


def test_the_dataset_forecast_page_sets_every_chart_value():
    ds = stored()
    page = client.get(f"/forecast?source={ds.id}").text
    assert "const RASIDE = ;" not in page
    assert re.search(r"const RASIDE = \{", page)


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_the_dataset_forecast_page_scripts_parse(tmp_path):
    ds = stored()
    page = client.get(f"/forecast?source={ds.id}").text
    parse = tmp_path / "parse.js"
    parse.write_text(PARSE, encoding="utf-8")
    scripts = _inline_scripts(page)
    assert scripts
    for i, body in enumerate(scripts):
        f = tmp_path / f"script{i}.js"
        f.write_text(body, encoding="utf-8")
        out = subprocess.run([shutil.which("node"), str(parse), str(f)],
                             capture_output=True, text=True)
        assert out.returncode == 0, (i, out.stderr[-400:], body[:200])
