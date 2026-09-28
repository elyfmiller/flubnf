"""The one-shot notices at the top of a page (shared._flash): one short
line, the essential fact first, styled by severity (a refusal warns, a
failure is an error), any extra in the notice's "?" tip (detail=)."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.ui import server as srv
from app.ui import shared as ui_shared
from app.ui import state as ui_state

#: the helpers whose first argument is a notice's line
_NOTICE_CALLS = {"_flash", "_refused", "_not_done"}
#: a line's literal text, interpolated values left out
_MAX_LITERAL = 120


def _calls():
    """(file:line, call node) for every notice call in app/ui."""
    for f in sorted((ROOT / "app" / "ui").rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name in _NOTICE_CALLS:
                yield f"{f.relative_to(ROOT)}:{n.lineno}", name, n


def _literal(node) -> str:
    """The literal text of a message expression (the longer branch of a
    conditional; an interpolated value counts as nothing)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_literal(v) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal(node.left) + _literal(node.right)
    if isinstance(node, ast.IfExp):
        return max(_literal(node.body), _literal(node.orelse), key=len)
    return ""


def _lead(node) -> str:
    """The message's opening literal ('' when it opens on a value)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        return _lead(node.values[0])
    if isinstance(node, ast.BinOp):
        return _lead(node.left)
    if isinstance(node, ast.IfExp):
        return _lead(node.body)
    return ""


def _kind(name, call):
    """The kind a call passes, or the helper's default."""
    for k in call.keywords:
        if k.arg == "kind" and isinstance(k.value, ast.Constant):
            return k.value.value
    if name == "_flash" and len(call.args) > 1 \
            and isinstance(call.args[1], ast.Constant):
        return call.args[1].value
    return {"_flash": "info", "_refused": "warn"}.get(name)


def test_every_notice_is_found():
    # a guard on the scan itself: the notices live in these modules
    files = {w.split(":")[0] for w, _, _ in _calls()}
    assert len(files) >= 6 and len(list(_calls())) > 100


def test_notice_lines_are_short_and_plain():
    long, dashes, redundant = [], [], []
    for where, _, call in _calls():
        text = _literal(call.args[0])
        if len(text) > _MAX_LITERAL:
            long.append((where, len(text)))
        if "\u2013" in text or "\u2014" in text:
            dashes.append(where)
        # a warn "Not run: ..." already says nothing ran
        if "othing was" in text:
            redundant.append(where)
    assert not long, long
    assert not dashes, dashes
    assert not redundant, redundant


def test_refusals_warn_and_failures_are_errors():
    wrong = []
    for where, name, call in _calls():
        lead, kind = _lead(call.args[0]), _kind(name, call)
        if kind is None:                      # _not_done picks it at runtime
            continue
        failed = lead.startswith("Could not") and kind != "error"
        refused = (lead.startswith(("Not ", "Nothing to"))
                   and kind not in ("warn", "error"))
        if failed or refused:
            wrong.append((where, lead, kind))
    assert not wrong, wrong


def test_detail_joins_and_the_most_severe_kind_wins():
    ui_state._status["flash"] = None
    ui_shared._flash("Saved a.", "ok", detail="First why.")
    ui_shared._flash("Not run: b.", "warn", detail="Second why.")
    ui_shared._flash("Saved a.", "ok", detail="First why.")   # no repeat
    assert ui_state._status["flash"] == "Saved a.  Not run: b."
    assert ui_state._status["flash_detail"] == "First why.  Second why."
    assert ui_state._status["flash_kind"] == "warn"
    # the log keeps the whole notice
    assert "Not run: b. Second why." in ui_state._status["log"]
    # a fresh notice after the page consumed the last carries no old detail
    for k in ("flash", "flash_kind", "flash_detail"):
        ui_state._status.pop(k, None)
    ui_shared._flash("Resuming 2098-99.", "ok")
    assert "flash_detail" not in ui_state._status


def test_the_page_shows_the_kind_and_the_detail_in_the_tip():
    ui_state._status["flash"] = None
    ui_shared._flash("Not run: x.", "warn", detail="Do <b>y</b> first.")
    html = TestClient(srv.app).get("/sandbox").text
    assert 'class="uk-alert uk-alert--warn" id="flash" role="status"' in html
    assert "Not run: x." in html
    assert 'aria-label="About this notice"' in html
    assert "Do &lt;b&gt;y&lt;/b&gt; first." in html        # escaped
    # consumed: the next page carries neither line nor tip
    again = TestClient(srv.app).get("/sandbox").text
    assert 'id="flash"' not in again and "Do &lt;b&gt;" not in again
