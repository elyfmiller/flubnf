"""The console's outward shape, pinned while app/ui/server.py is split into
per-tab modules (a refactor that must not change behaviour):

  1. the route table, flattened (FastAPI >= 0.141 keeps an included router
     as one entry in app.router.routes): the same (methods, path, name)
     routes; the routes one concrete path can reach in the same relative
     order, which decides the 405 Allow header (no two routes sharing a
     method overlap, so dispatch never depends on order); a name's first
     route is still the one url_path_for finds; datasets_ui's routes last;
  2. what a wrong method, a trailing slash and the favicon get back;
  3. the middleware, outermost first;
  4. the Jinja globals and filters the app adds, the templates and static
     directories;
  5. importing app.ui.server, in a fresh interpreter with only the startup
     warm thread held back: the warm pass is requested once, after the app
     is fully assembled; the startup trace opens before fastapi, app.core
     and flubnf load and closes the import; the same first-party modules
     load and pandas/plotly stay off the import path;
  6. `ruff check --select F821,F823,F811,F401 app/ui` is clean (skipped
     where ruff is not installed);

and the rules that keep app/ui's modules (server plus the support and tab
modules split out of it) honest with each other and with the tests:

  7. every name a test patches on an app.ui module (and data_mod, which
     rebinds itself) is DEFINED by exactly that module and bound by no
     other app.ui module at import, so no patch can miss a copy;
  8. a name one app.ui module imports from another is the owner's own
     object (one _status, one lock, one VERSIONS, one templates);
  9. no module-level alias of an app.ui module is rebound anywhere in its
     file (a local `state` would shadow the module `state`);
 10. the tests reach a moved private name through its owner, never through
     app.ui.server, and patch app.ui modules with raising left on; no
     app.ui module imports server or datasets_ui at import (datasets_ui
     is included by server, last).

golden/ui_routes.json was captured at 029c028. Regenerate it only for a
deliberate change, and review its diff:

    python app/tests/test_ui_layout.py --write-golden
"""
import ast
import importlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "ui_routes.json"

client = TestClient(srv.app)


# ------------------------------------------------------------- the snapshot

def route_contexts(app) -> list:
    """Every route of `app`, flattened. FastAPI >= 0.141 keeps each included
    router as a single _IncludedRouter entry in app.router.routes; older
    versions copy the router's routes in flat."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:
        return list(app.router.routes)
    return list(iter_route_contexts(app.router.routes))


def route_rows(app) -> list:
    """[methods, path, name, kind, group] per route, in registration order;
    group: console (an app.ui handler), datasets_ui, mount or framework
    (FastAPI's own /openapi.json and docs)."""
    from starlette.routing import Mount
    rows = []
    for rc in route_contexts(app):
        route = getattr(rc, "original_route", rc)
        mod = getattr(getattr(rc, "endpoint", None), "__module__", "") or ""
        if mod == "app.ui.datasets_ui":
            group = "datasets_ui"
        elif mod.startswith("app.ui"):
            group = "console"
        elif isinstance(route, Mount):
            group = "mount"
        else:
            group = "framework"
        rows.append([",".join(sorted(getattr(rc, "methods", None) or ())),
                     rc.path, rc.name, type(route).__name__, group])
    return rows


def middleware_names(app) -> list:
    """The http middleware dispatch functions, outermost first."""
    out = []
    for m in app.user_middleware:
        kw = getattr(m, "kwargs", None) or getattr(m, "options", {}) or {}
        d = kw.get("dispatch")
        out.append(d.__name__ if d is not None else m.cls.__name__)
    return out


def _describe(v) -> str:
    if isinstance(v, types.ModuleType):
        return "module " + v.__name__
    if callable(v):
        return "callable " + getattr(v, "__name__", type(v).__name__)
    return "value " + type(v).__name__


def jinja_added() -> tuple:
    """(globals, filters) the app adds to a stock Jinja2Templates
    environment, name -> description (callables by __name__)."""
    from fastapi.templating import Jinja2Templates
    stock = Jinja2Templates(directory=str(REPO / "app" / "ui" / "templates"))
    env = srv.templates.env
    out = []
    for have, base in ((env.globals, stock.env.globals),
                       (env.filters, stock.env.filters)):
        out.append({k: _describe(v) for k, v in sorted(have.items())
                    if k not in base or _describe(base[k]) != _describe(v)})
    return tuple(out)


def _rel(p) -> str:
    return Path(p).resolve().relative_to(REPO).as_posix()


def directories() -> dict:
    from starlette.routing import Mount
    static = [r for r in srv.app.router.routes
              if isinstance(r, Mount) and r.name == "static"]
    return {"templates": [_rel(p) for p in
                          srv.templates.env.loader.searchpath],
            "static": _rel(static[0].app.directory) if static else None}


#: run in a fresh interpreter from the repository root; prints one JSON line
_IMPORT_PROBE = r'''
import json, os, sys, threading
TRACE = os.environ["FLUBNF_STARTUP_TRACE"]
WATCH = ("fastapi", "app.core", "flubnf")
seen = set()

class _FirstImports:
    """Marks, in the startup trace itself, where fastapi, app.core and
    flubnf first load."""
    def find_spec(self, name, path=None, target=None):
        if name in WATCH and name not in seen:
            seen.add(name)
            with open(TRACE, "a") as fh:
                fh.write("IMPORT " + name + "\n")
        return None

sys.meta_path.insert(0, _FirstImports())

def shape(mod):
    from fastapi.routing import iter_route_contexts
    return {"routes": len(list(iter_route_contexts(mod.app.router.routes))),
            "middleware": len(mod.app.user_middleware),
            "globals": sorted(mod.templates.env.globals)}

_start = threading.Thread.start
warm = []

def start(self, *a, **k):
    # hold back ONLY the startup warm pass (its imports would race the
    # sys.modules snapshot); anyio and every other thread start as usual
    if self.name == "flubnf-startup-warm":
        warm.append(shape(sys.modules["app.ui.server"]))
        return None
    return _start(self, *a, **k)

threading.Thread.start = start
import app.ui.server as srv
print(json.dumps({
    "warm": warm,
    "final": shape(srv),
    "first_party": sorted(m for m in sys.modules
                          if m.split(".")[0] in ("app", "flubnf")
                          and not m.startswith("app.ui")),
    "third_party": {m: m in sys.modules
                    for m in ("pandas", "plotly", "scipy", "numpy")},
}))
'''


def import_probe(tmp: Path) -> dict:
    trace = tmp / "startup-trace.txt"
    env = dict(os.environ, FLUBNF_STARTUP_TRACE=str(trace))
    r = subprocess.run([sys.executable, "-c", _IMPORT_PROBE], cwd=str(REPO),
                       env=env, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    events = []
    for line in trace.read_text().splitlines():
        if line.startswith("IMPORT "):
            events.append(line)
        elif " srv] " in line:
            events.append("srv: " + line.split(" srv] ", 1)[1])
    out["trace"] = events
    return out


def snapshot(tmp: Path) -> dict:
    g, f = jinja_added()
    probe = import_probe(tmp)
    return {
        "_about": ("app/ui's outward shape for test_ui_layout.py; "
                   "regenerate only for a deliberate change: python "
                   "app/tests/test_ui_layout.py --write-golden"),
        "routes": route_rows(srv.app),
        "middleware": middleware_names(srv.app),
        "jinja_globals": g,
        "jinja_filters": f,
        "directories": directories(),
        "import": {"first_party": probe["first_party"],
                   "third_party": probe["third_party"],
                   "trace": [e for e in probe["trace"]
                             if e.startswith("srv: ")]},
    }


def _fmt(v, ind: int = 0) -> str:
    """JSON, one route (any flat list) per line."""
    pad = " " * ind
    if isinstance(v, dict) and v:
        rows = [f'{pad} {json.dumps(k)}: {_fmt(x, ind + 1)}'
                for k, x in v.items()]
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
    if isinstance(v, list) and v and (
            any(isinstance(x, (list, dict)) for x in v)
            or len(json.dumps(v)) > 100):
        rows = [pad + " " + _fmt(x, ind + 1) for x in v]
        return "[\n" + ",\n".join(rows) + "\n" + pad + "]"
    return json.dumps(v)


def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------ 1. the routes

def _pattern(path: str):
    return re.compile("^" + re.sub(
        r"\\\{(\w+)(?::(\w+))?\\\}",
        lambda m: ".+" if m.group(2) == "path" else "[^/]+",
        re.escape(path)) + "$")


def _overlaps(rows: list) -> set:
    """Pairs of routes (by methods, path) that one concrete path reaches,
    found by filling every path parameter with every literal segment of
    the table. Raises if two of them share a method (order-dependent
    dispatch)."""
    rows = [r for r in rows if r[0]]                 # routes with methods
    literals = sorted({s for r in rows for s in r[1].split("/")
                       if s and "{" not in s} | {"x"})
    pats = [(r, _pattern(r[1])) for r in rows]
    urls = set()
    for r in rows:
        params = re.findall(r"\{(\w+)(?::\w+)?\}", r[1])
        for combo in itertools.product(literals, repeat=len(params)):
            url = r[1]
            for p, v in zip(params, combo):
                url = re.sub(r"\{" + p + r"(?::\w+)?\}", v, url, count=1)
            urls.add(url)
    pairs = set()
    for url in sorted(urls):
        hits = [r for r, pat in pats if pat.match(url)]
        methods = [m for r in hits for m in r[0].split(",")]
        assert len(methods) == len(set(methods)), (
            f"{url} reaches two routes with the same method: {hits}")
        for a, b in itertools.combinations(hits, 2):
            pairs.add(((a[0], a[1]), (b[0], b[1])))
    return pairs


def test_the_route_table_is_the_golden_one():
    live, gold = route_rows(srv.app), golden()["routes"]
    lc, gc = Counter(map(tuple, live)), Counter(map(tuple, gold))
    assert lc == gc, {"new": sorted((lc - gc).elements()),
                      "gone": sorted((gc - lc).elements())}


def test_routes_one_path_reaches_keep_their_order():
    """The first route whose path matches (in registration order) names
    the Allow header of a 405, so order matters exactly for these pairs."""
    live, gold = route_rows(srv.app), golden()["routes"]
    pairs = _overlaps(gold)
    assert pairs == {
        (("POST", "/runs/clear"), ("GET", "/runs/{run_id}")),
        (("POST", "/retro/stop"), ("GET", "/retro/{season}")),
        (("POST", "/retro/run"), ("GET", "/retro/{season}")),
    }
    assert {frozenset(p) for p in _overlaps(live)} == \
        {frozenset(p) for p in pairs}

    def pos(rows, key):
        return [i for i, r in enumerate(rows) if (r[0], r[1]) == key][0]
    for a, b in pairs:
        assert pos(live, a) < pos(live, b), (a, b)


def test_a_route_name_still_finds_its_first_route():
    """url_path_for takes the first route of a name: /runs (not /storage)
    for runs_page, the console's /storage/delete for storage_delete."""
    seen = set()
    for methods, path, name, kind, group in golden()["routes"]:
        if kind != "APIRoute" or name in seen:
            continue
        seen.add(name)
        params = re.findall(r"\{(\w+)\}", path)
        assert srv.app.url_path_for(name, **{p: "p" for p in params}) == \
            re.sub(r"\{\w+\}", "p", path), name
    assert srv.app.url_path_for("runs_page") == "/runs"
    assert srv.app.url_path_for("storage_delete") == "/storage/delete"


def test_the_dataset_routes_come_last():
    live = route_rows(srv.app)
    groups = [r[4] for r in live]
    n = sum(1 for r in golden()["routes"] if r[4] == "datasets_ui")
    assert n == 8
    assert groups[-n:] == ["datasets_ui"] * n
    assert "datasets_ui" not in groups[:-n]


# ------------------------------------------------------------ 2. the probes

@pytest.mark.parametrize("method,path,allow", [
    ("PUT", "/runs/clear", "POST"),
    ("PUT", "/retro/stop", "POST"),
    ("PUT", "/retro/run", "POST"),
    ("DELETE", "/runs/x", "GET"),
])
def test_a_wrong_method_names_the_first_matching_route(method, path, allow):
    r = client.request(method, path, follow_redirects=False)
    assert r.status_code == 405
    assert r.headers["allow"] == allow


@pytest.mark.parametrize("path", ["/forecast/", "/retro/", "/storage/"])
def test_a_trailing_slash_redirects(path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "http://testserver" + path.rstrip("/")


def test_the_favicon_is_served():
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"
    assert r.content == (REPO / "app" / "ui" / "static" / "brand"
                         / "favicon.ico").read_bytes()


# -------------------------------------------------------- 3. the middleware

def test_the_middleware_order():
    """The sandbox engine guard wraps the same-host (CSRF) guard."""
    assert middleware_names(srv.app) == golden()["middleware"] == [
        "_sandbox_engine_guard", "_same_host_guard"]


# ------------------------------------------------ 4. the Jinja environment

def test_the_jinja_globals_and_filters():
    g, f = jinja_added()
    gold = golden()
    assert g == gold["jinja_globals"]
    assert f == gold["jinja_filters"]


def test_the_templates_and_static_directories():
    assert directories() == golden()["directories"] == {
        "templates": ["app/ui/templates"], "static": "app/ui/static"}


# ------------------------------------------------- 5. importing the server

def test_importing_the_server(tmp_path):
    probe, gold = import_probe(tmp_path), golden()["import"]
    # the warm pass is requested once, and only once the app is assembled
    assert probe["warm"] == [probe["final"]]
    # the trace opens before fastapi, app.core and flubnf load, and the
    # import's last act is to announce the warm pass
    trace = probe["trace"]
    assert [e for e in trace if e.startswith("srv: ")] == gold["trace"] == [
        "srv: import begin (fastapi + app.core next)",
        "srv: import complete, starting background warm"]
    assert trace[0] == gold["trace"][0] and trace[-1] == gold["trace"][-1]
    assert {e for e in trace if e.startswith("IMPORT ")} == {
        "IMPORT fastapi", "IMPORT app.core", "IMPORT flubnf"}
    # no new eager imports: the same first-party modules outside app.ui,
    # and the heavy science stays behind the first use
    assert probe["first_party"] == gold["first_party"]
    assert probe["third_party"] == gold["third_party"] == {
        "pandas": False, "plotly": False, "scipy": False, "numpy": True}
    for lazy in ("app.core.data", "app.core.knobs", "app.core.retro",
                 "app.core.report_v2", "app.core.report_season"):
        assert lazy not in probe["first_party"], lazy


# ------------------------------------------------------------- 6. the lint

def _ruff() -> list | None:
    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff"]
    exe = shutil.which("ruff")
    return [exe] if exe else None


def test_app_ui_has_no_undefined_shadowed_or_unused_names():
    """F821 undefined name (a string annotation included: FastAPI resolves
    those from the defining module), F823 local read before assignment,
    F811 redefinition, F401 unused import."""
    cmd = _ruff()
    if cmd is None:
        pytest.skip("ruff is not installed")
    r = subprocess.run(cmd + ["check", "--isolated", "--no-cache",
                              "--select", "F821,F823,F811,F401", "app/ui"],
                       cwd=str(REPO), capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------ 7. every patched name, one home

UI_DIR = REPO / "app" / "ui"
TEST_DIRS = (REPO / "app" / "tests", REPO / "tests")


def _dotted(path: Path) -> str:
    parts = list(path.relative_to(REPO).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def ui_modules() -> dict:
    """Dotted name -> path of every module under app/ui."""
    return {_dotted(p): p for p in sorted(UI_DIR.rglob("*.py"))
            if "__pycache__" not in p.parts}


def _parse(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _test_files() -> list:
    return [p for d in TEST_DIRS for p in sorted(d.rglob("*.py"))
            if "__pycache__" not in p.parts]


def _names(target):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for e in target.elts:
            yield from _names(e)
    elif isinstance(target, ast.Starred):
        yield from _names(target.value)


def _top_level(body):
    """A module's statements, through if/try/with/for blocks, never into a
    def or a class."""
    for node in body:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            continue
        for field in ("body", "orelse", "finalbody", "handlers"):
            sub = getattr(node, field, None)
            if isinstance(sub, list):
                yield from _top_level(sub)


def module_bindings(tree) -> tuple:
    """(defined, imported): the names a module binds at import by def,
    class or assignment, and by import."""
    defined, imported = set(), set()
    for node in _top_level(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                defined.update(_names(t))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For,
                               ast.AsyncFor)):
            defined.update(_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    defined.update(_names(item.optional_vars))
        elif isinstance(node, ast.Import):
            imported.update(a.asname or a.name.split(".")[0]
                            for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(a.asname or a.name for a in node.names)
    return defined, imported


def _module_aliases(tree, modules: dict, anywhere: bool = True) -> dict:
    """Name -> dotted app.ui module, for each import that binds a module
    under app/ui: `from app.ui import x [as y]`, `from app.ui.routes import
    x as y`, `import app.ui.x as y` (in any scope, or at top level only)."""
    out = {}
    nodes = ast.walk(tree) if anywhere else _top_level(tree.body)
    for node in nodes:
        if isinstance(node, ast.ImportFrom) and node.level == 0 \
                and node.module:
            for a in node.names:
                if f"{node.module}.{a.name}" in modules:
                    out[a.asname or a.name] = f"{node.module}.{a.name}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in modules and a.asname:
                    out[a.asname] = a.name
    return out


#: how the tests spell a name bound to the app.ui.server module
SERVER_SPELLINGS = {"srv", "srv_", "server", "srv_mod"}


def _test_aliases(tree, modules: dict) -> dict:
    """_module_aliases for a test file, plus the server module arriving
    through a fixture (`srv_, raw = console`) in a file that imports it:
    its usual spellings, unless an import binds them to something else in
    the file (`from app.ui.server import app as srv` is the FastAPI app)."""
    alias = _module_aliases(tree, modules)
    if "app.ui.server" not in alias.values():
        return alias
    other = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            other.update(a.asname or a.name.split(".")[0]
                         for a in node.names if a.name != "app.ui.server")
        elif isinstance(node, ast.ImportFrom):
            other.update(a.asname or a.name for a in node.names
                         if f"{node.module}.{a.name}" != "app.ui.server")
    for name in SERVER_SPELLINGS - other:
        alias.setdefault(name, "app.ui.server")
    return alias


def _str_arg(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def patches_in_tests(modules: dict):
    """(file, line, module, name, call) for every patch the tests make on
    an app.ui module: setattr/delattr (monkeypatch's or the builtin) or
    patch.object on an alias of the module, or an "app.ui.<module>.<name>"
    target string."""
    for path in _test_files():
        tree = _parse(path)
        alias = _test_aliases(tree, modules)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else getattr(
                f, "id", "")
            a0 = node.args[0]
            if fname in ("setattr", "delattr", "object") \
                    and len(node.args) >= 2 and isinstance(a0, ast.Name) \
                    and a0.id in alias and _str_arg(node.args[1]):
                yield (path, node.lineno, alias[a0.id],
                       _str_arg(node.args[1]), node)
            elif fname in ("setattr", "delattr", "patch") \
                    and (_str_arg(a0) or "").startswith("app.ui."):
                mod, _, name = _str_arg(a0).rpartition(".")
                if mod in modules:
                    yield path, node.lineno, mod, name, node


def test_every_patched_name_has_one_home():
    """A test patches a name on the module that DEFINES it, and no other
    app.ui module holds a binding of that name made at import: a
    from-import copy would never see the patch (a silent no-op). data_mod
    counts too, since its lazy proxy rebinds it on first use."""
    modules = ui_modules()
    binds = {m: module_bindings(_parse(p)) for m, p in modules.items()}
    targets = {(mod, name) for _p, _l, mod, name, _n in
               patches_in_tests(modules)} | {("app.ui.state", "data_mod")}
    assert len(targets) > 20, targets            # the scan sees the tests
    problems = []
    for mod, name in sorted(targets):
        homes = [m for m, (d, _i) in binds.items() if name in d]
        others = sorted(m for m, (d, i) in binds.items()
                        if m != mod and (name in d or name in i))
        if homes != [mod] or others:
            problems.append(f"{mod}.{name}: defined in {homes}, also "
                            f"bound in {others}")
    assert not problems, "\n".join(problems)


# ---------------------------------------- 8. one object behind every name

def test_an_imported_name_is_its_owners_object():
    """Every name an app.ui module takes from another (from app.ui.x import
    name) is x's own object; server's public names are their owners'."""
    from app.ui import state, templating, versions
    modules = ui_modules()
    loaded = {m: importlib.import_module(m) for m in modules}
    checked = 0
    for mod, path in modules.items():
        for node in _top_level(_parse(path).body):
            if not (isinstance(node, ast.ImportFrom) and node.level == 0
                    and node.module in modules):
                continue
            for a in node.names:
                if f"{node.module}.{a.name}" in modules:
                    continue                             # a module, not a name
                assert getattr(loaded[mod], a.asname or a.name) is getattr(
                    loaded[node.module], a.name), (mod, a.name)
                checked += 1
    assert checked > 20
    assert srv.templates is templating.templates
    assert srv.VERSIONS is versions.VERSIONS
    assert srv.RUNNING_SHA is versions.RUNNING_SHA
    # the console-wide state: one object each, wherever a module holds it
    for name in ("_status", "_last_form", "_engine_lock", "_sandbox_status",
                 "_WARM_DONE", "ENGINES"):
        held = {id(getattr(m, name)) for m in loaded.values()
                if hasattr(m, name)}
        assert held == {id(getattr(state, name))}, name


# ---------------------------------------- 9. no module alias is shadowed

def test_no_module_alias_is_rebound_in_its_file():
    """A module-level alias of an app.ui module (`state`, `shared`, ...)
    must not also name a local, a parameter or a def anywhere in the file:
    `state._status` under a local `state` reads the wrong object."""
    modules = ui_modules()
    problems = []
    for mod, path in modules.items():
        tree = _parse(path)
        aliases = _module_aliases(tree, modules, anywhere=False)
        for node in ast.walk(tree):
            bound = []
            if isinstance(node, ast.Name) and isinstance(
                    node.ctx, (ast.Store, ast.Del)):
                bound = [(node.id, None)]
            elif isinstance(node, ast.arg):
                bound = [(node.arg, None)]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                bound = [(node.name, None)]
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound = [(node.name, None)]
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound = [(n, None) for n in node.names]
            elif isinstance(node, ast.Import):
                bound = [(a.asname or a.name.split(".")[0],
                          a.name if a.asname else None) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                bound = [(a.asname or a.name, f"{node.module}.{a.name}")
                         for a in node.names]
            for name, target in bound:
                if name in aliases and target != aliases[name]:
                    problems.append(f"{path.relative_to(REPO)}:"
                                    f"{node.lineno}: {name} rebinds the "
                                    f"module alias {aliases[name]}")
    assert not problems, "\n".join(problems)


# ------------------------------------------------- 10. the import hygiene

def test_tests_reach_moved_names_through_their_owners():
    """No test reads, patches or imports a private name through
    app.ui.server that server does not itself define (it moved: use its
    owner), and no patch on an app.ui module passes raising=False (a patch
    of a missing name must fail, not pass silently)."""
    modules = ui_modules()
    server_defined, _ = module_bindings(_parse(modules["app.ui.server"]))

    def stale(name) -> bool:
        return (name.startswith("_") and not name.startswith("__")
                and name not in server_defined)
    problems = []
    for path in _test_files():
        tree = _parse(path)
        srv_names = {k for k, v in _test_aliases(tree, modules).items()
                     if v == "app.ui.server"}
        where = path.relative_to(REPO)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(
                    node.value, ast.Name) and node.value.id in srv_names \
                    and stale(node.attr):
                problems.append(f"{where}:{node.lineno}: server.{node.attr}")
            elif isinstance(node, ast.ImportFrom) \
                    and node.module == "app.ui.server":
                problems += [f"{where}:{node.lineno}: from server import "
                             f"{a.name}" for a in node.names if stale(a.name)]
            elif isinstance(node, ast.Constant) and isinstance(
                    node.value, str) and node.value.startswith(
                        "app.ui.server.") and stale(node.value.split(".")[3]):
                problems.append(f"{where}:{node.lineno}: {node.value!r}")
    for path, line, mod, name, call in patches_in_tests(modules):
        where = path.relative_to(REPO)
        if mod == "app.ui.server" and stale(name):
            problems.append(f"{where}:{line}: patches server.{name}")
        if any(k.arg == "raising" and not (
                isinstance(k.value, ast.Constant) and k.value.value is True)
               for k in call.keywords):
            problems.append(f"{where}:{line}: raising= on {mod}.{name}")
    assert not problems, "\n".join(problems)


def test_no_app_ui_module_imports_the_assembly_at_import():
    """server assembles the app and includes datasets_ui last; a module
    that imported either at import would put a cycle on the import path
    (the existing in-function `from app.ui import datasets_ui` stay)."""
    modules = ui_modules()
    problems = []
    for mod, path in modules.items():
        for node in _top_level(_parse(path).body):
            if isinstance(node, ast.Import):
                got = {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                got = {node.module} | {f"{node.module}.{a.name}"
                                       for a in node.names}
            else:
                continue
            banned = {"app.ui.server"} | (
                set() if mod == "app.ui.server" else {"app.ui.datasets_ui"})
            if got & banned:
                problems.append(f"{mod}:{node.lineno}: {sorted(got & banned)}")
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-golden"]:
        sys.exit(__doc__)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        GOLDEN_PATH.write_text(_fmt(snapshot(Path(d))) + "\n",
                               encoding="utf-8")
    print(f"wrote {GOLDEN_PATH.relative_to(REPO)}")
