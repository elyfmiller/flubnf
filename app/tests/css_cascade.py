"""A small CSS cascade for the tests: which declaration wins for one
element, at one window width, from the console's own stylesheets in the
order a page links them. A test that pins a rule's text passes when a later
rule undoes it; this asks the cascade instead.

What it reads, and no more: @media (min-width and max-width in px, rem or
em, always at the browser's 16 px, never the page's text size; print,
forced-colors and the preference queries count as off unless a test turns
one on), @container and @supports (counted as on), selector lists, the
descendant, child and sibling combinators, type, class, id and attribute
selectors, :not(), :is(), :where(), :has() and specificity.

An element is described by its own compound selector ("td.dsname",
'html[data-theme="dark"]'), from the root down. What the description
cannot settle counts as a match, so a rule that might undo another is
never missed: a sibling, a structural pseudo-class (:first-child,
:nth-child()), :has(). A state (:hover, :focus, :checked) matches only
when the element lists it ("button:hover"). A pseudo-element's rules
style only that box ("td[data-label]::before"), never the element.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
#: base.html links these on every console page, in this order; a page's
#: own sheet follows them
BASE_SHEETS = ("fonts/dm-sans.css", "nau.css", "ui-kit.css",
               "brand/logos.css")
#: rem and em in a media query: the browser's size, not the page's
MEDIA_EM_PX = 16.0

STATES = {"hover", "focus", "focus-visible", "focus-within", "active",
          "visited", "checked", "disabled", "enabled", "target", "empty",
          "placeholder-shown", "invalid", "valid", "required", "optional",
          "indeterminate", "default", "open", "read-only", "read-write",
          "autofill", "user-invalid", "user-valid", "popover-open",
          "fullscreen", "modal", "link", "any-link", "defined"}
PSEUDO_ELEMENTS = {"before", "after", "first-line", "first-letter",
                   "marker", "placeholder", "selection", "backdrop",
                   "file-selector-button", "cue"}


# ---------------------------------------------------------------- parsing

def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _scan(s: str, i: int, stops: str, depth_open="([", depth_close=")]"):
    """Index of the first character of `stops` at depth 0 from i, outside
    strings; -1 when none."""
    depth, q, n = 0, None, len(s)
    while i < n:
        c = s[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif depth == 0 and c in stops:
            return i
        elif c in depth_open:
            depth += 1
        elif c in depth_close:
            depth -= 1
        i += 1
    return -1


def _close(s: str, i: int, closer: str) -> int:
    """Index of the `closer` that ends the group opened just before i."""
    j = _scan(s, i, closer, "(", ")")
    if j < 0:
        raise ValueError(f"no {closer!r} closes {s!r} from {i}")
    return j


def _block_end(css: str, i: int) -> int:
    """Index of the brace closing the block that opens at i."""
    depth, q, n = 0, None, len(css)
    while i < n:
        c = css[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced block")


def split_top(s: str, sep: str) -> list[str]:
    """`s` split at `sep` outside strings, brackets and parentheses."""
    out, i = [], 0
    while True:
        j = _scan(s, i, sep)
        if j < 0:
            out.append(s[i:].strip())
            return [p for p in out if p]
        out.append(s[i:j].strip())
        i = j + 1


@dataclass
class Rule:
    selectors: list
    decls: list            # (property, value, important)
    conditions: tuple      # every enclosing @media / @container prelude
    sheet: str
    order: int = 0


def _decls(body: str) -> list:
    out = []
    for part in split_top(body, ";"):
        prop, colon, value = part.partition(":")
        if not colon:
            continue
        value = value.strip()
        important = bool(re.search(r"!\s*important\s*$", value))
        if important:
            value = re.sub(r"\s*!\s*important\s*$", "", value)
        out.append((prop.strip().lower() if not prop.strip().startswith("--")
                    else prop.strip(), value, important))
    return out


def parse(css: str, sheet: str = "", conditions: tuple = ()) -> list:
    """The style rules of one sheet, with their enclosing conditions."""
    css = _strip_comments(css)
    out, i, n = [], 0, len(css)
    while i < n:
        j = _scan(css, i, "{;")
        if j < 0:
            break
        prelude = " ".join(css[i:j].split())
        if css[j] == ";":                       # @import, @charset
            i = j + 1
            continue
        k = _block_end(css, j)
        body = css[j + 1:k]
        if prelude.startswith(("@media", "@container", "@supports")):
            out += parse(body, sheet, conditions + (prelude,))
        elif not prelude.startswith("@"):       # @keyframes, @font-face
            out.append(Rule(split_top(prelude, ","), _decls(body),
                            conditions, sheet))
        i = k + 1
    return out


# --------------------------------------------------------------- elements

@dataclass
class El:
    tag: str = ""
    id: str = ""
    classes: frozenset = frozenset()
    attrs: dict = field(default_factory=dict)
    states: frozenset = frozenset()
    pseudo: str = ""        # "before": the element's ::before box


def _compound_parts(comp: str) -> list:
    """A compound selector's simple selectors, in order."""
    parts, i, n = [], 0, len(comp)
    while i < n:
        c = comp[i]
        if c == "*":
            parts.append(("*", "")); i += 1
        elif c == "#" or c == ".":
            m = re.match(r"-?[\w-]+", comp[i + 1:])
            parts.append((c, m.group(0))); i += 1 + len(m.group(0))
        elif c == "[":
            j = _close(comp, i + 1, "]")
            parts.append(("[", comp[i + 1:j].strip())); i = j + 1
        elif c == ":":
            elem = comp.startswith("::", i)
            i += 2 if elem else 1
            m = re.match(r"-?[\w-]+", comp[i:])
            name = m.group(0).lower(); i += len(name)
            arg = None
            if i < n and comp[i] == "(":
                j = _close(comp, i + 1, ")")
                arg = comp[i + 1:j]; i = j + 1
            kind = "::" if elem or name in ("before", "after",
                                            "first-line",
                                            "first-letter") else ":"
            parts.append((kind, (name, arg)))
        else:
            m = re.match(r"[\w-]+", comp[i:])
            if not m:
                raise ValueError(f"cannot read {comp!r} at {i}")
            parts.append(("tag", m.group(0).lower())); i += len(m.group(0))
    return parts


def el(desc: str) -> El:
    """An element from its compound selector: 'details.sbmanage[open]',
    'button:hover', 'html[data-theme="dark"]', or its box 'td::before'."""
    e = El()
    classes, attrs, states = set(), {}, set()
    for kind, v in _compound_parts(desc):
        if kind == "tag":
            e.tag = v
        elif kind == "#":
            e.id = v
        elif kind == ".":
            classes.add(v)
        elif kind == "[":
            name, eq, val = v.partition("=")
            attrs[name.strip()] = val.strip().strip("\"'") if eq else ""
        elif kind == ":":
            states.add(v[0])
        elif kind == "::":
            e.pseudo = v[0]
    e.classes, e.attrs, e.states = frozenset(classes), attrs, frozenset(states)
    return e


def path(*descs: str) -> list:
    """An element and its ancestors, root first."""
    return [el(d) for d in descs]


# --------------------------------------------------------------- matching
# three-valued: True, False, None (cannot tell, counted as a match)

def _and(vals):
    vals = list(vals)
    if False in vals:
        return False
    return None if None in vals else True


def _or(vals):
    vals = list(vals)
    if True in vals:
        return True
    return None if None in vals else False


def _not(v):
    return None if v is None else not v


def _attr_match(e: El, sel: str):
    m = re.match(r"\s*([\w-]+)\s*(?:([~^$*|]?=)\s*(.+?))?\s*(i)?\s*$", sel)
    name, op, val, ci = m.groups()
    if name not in e.attrs:
        return False
    if not op:
        return True
    have, want = e.attrs[name], val.strip("\"'")
    if ci:
        have, want = have.lower(), want.lower()
    return {"=": have == want, "~=": want in have.split(),
            "^=": have.startswith(want), "$=": have.endswith(want),
            "*=": want in have,
            "|=": have == want or have.startswith(want + "-")}[op]


def _compound_match(comp: str, e: El, top: bool = True):
    parts = _compound_parts(comp)
    # a rule for the element never styles its ::before, and the reverse
    if top and next((v[0] for k, v in parts if k == "::"), "") != e.pseudo:
        return False
    res = []
    for kind, v in parts:
        if kind == "*":
            res.append(True)
        elif kind == "tag":
            res.append(e.tag == v)
        elif kind == "#":
            res.append(e.id == v)
        elif kind == ".":
            res.append(v in e.classes)
        elif kind == "[":
            res.append(_attr_match(e, v))
        elif kind == "::":
            res.append(True)
        else:
            name, arg = v
            if name in ("is", "where", "matches", "any"):
                res.append(_or(_compound_match(c, e, False)
                               for c in split_top(arg, ",")))
            elif name == "not":
                res.append(_and(_not(_compound_match(c, e, False))
                                for c in split_top(arg, ",")))
            elif name == "root":
                res.append(e.tag == "html")
            elif name in e.states:
                res.append(True)
            elif name in STATES:
                res.append(False)
            else:                       # structural, :has(), unknown
                res.append(None)
    return _and(res)


def _complex(sel: str) -> list:
    """[compound, combinator, compound, ...] left to right."""
    out, cur, i, n = [], "", 0, len(sel)
    while i < n:
        c = sel[i]
        if c in "([":
            j = _close(sel, i + 1, ")" if c == "(" else "]")
            cur += sel[i:j + 1]; i = j + 1
            continue
        if c in " >+~":
            comb = ""
            while i < n and sel[i] in " >+~":
                comb += sel[i]; i += 1
            comb = comb.strip() or " "
            if cur:
                out += [cur, comb]
                cur = ""
            elif out:
                out[-1] = comb
            continue
        cur += c; i += 1
    if cur:
        out.append(cur)
    return out


def matches(sel: str, chain: list):
    """Whether the last element of `chain` matches the complex selector."""
    parts = _complex(sel)

    def at(idx, pos, sibling=False):
        own = None if sibling else _compound_match(parts[idx], chain[pos])
        if own is False:
            return False
        if idx == 0:
            return own
        comb = parts[idx - 1]
        if comb == ">":
            rest = at(idx - 2, pos - 1) if pos > 0 else False
        elif comb == " ":
            rest = _or(at(idx - 2, p) for p in range(pos - 1, -1, -1))
        else:                           # + and ~: siblings are not known
            rest = at(idx - 2, pos, sibling=True)
        return _and([own, rest])

    return at(len(parts) - 1, len(chain) - 1)


def specificity(sel: str) -> tuple:
    a = b = c = 0
    for comp in _complex(sel)[::2]:
        for kind, v in _compound_parts(comp):
            if kind == "#":
                a += 1
            elif kind in (".", "["):
                b += 1
            elif kind == "tag":
                c += 1
            elif kind == "::":
                c += 1
            elif kind == ":":
                name, arg = v
                if name == "where":
                    continue
                if name in ("is", "not", "has", "matches", "any"):
                    best = max(specificity(s) for s in split_top(arg, ","))
                    a, b, c = a + best[0], b + best[1], c + best[2]
                else:
                    b += 1
    return (a, b, c)


# ------------------------------------------------------------ conditions

def _px(v: str) -> float:
    m = re.match(r"\s*([\d.]+)\s*(px|rem|em)\s*$", v)
    num, unit = float(m.group(1)), m.group(2)
    return num if unit == "px" else num * MEDIA_EM_PX


def condition_holds(prelude: str, width: float, on: frozenset) -> bool:
    if prelude.startswith(("@supports", "@container")):
        return True
    q = prelude[len("@media"):].strip().lower()
    for one in split_top(q, ","):
        neg = one.startswith("not ")
        one = re.sub(r"^(not|only)\s+", "", one)
        kind = re.match(r"([a-z]*)", one).group(1)
        ok = kind in ("", "all", "screen", "and") or kind in on
        for feat in re.findall(r"\(([^()]*)\)", one):
            name, _, val = (x.strip() for x in feat.partition(":"))
            if name == "min-width":
                ok = ok and width >= _px(val)
            elif name == "max-width":
                ok = ok and width <= _px(val)
            else:
                ok = ok and f"{name}:{val}" in on
        if ok != neg:
            return True
    return False


# --------------------------------------------------------------- cascade

@dataclass
class Win:
    prop: str
    value: str
    selector: str
    rule: Rule
    certain: bool


class Cascade:
    """The rules of `sheets` (paths under app/ui/static), in link order."""

    def __init__(self, *sheets: str):
        self.rules = []
        for name in sheets:
            text = (STATIC / name).read_text(encoding="utf-8")
            self.rules += parse(text, name)
        for i, r in enumerate(self.rules):
            r.order = i

    @classmethod
    def page(cls, *own: str) -> "Cascade":
        """A console page: base.html's sheets, then the page's own."""
        return cls(*BASE_SHEETS, *own)

    def candidates(self, chain: list, props, width: float = 1280,
                   on=()) -> list:
        """Every declaration of `props` that applies to the last element
        of `chain`, weakest first (cascade order)."""
        props = (props,) if isinstance(props, str) else tuple(props)
        on = frozenset(on)
        found = []
        for r in self.rules:
            if not any(d[0] in props for d in r.decls):
                continue
            if not all(condition_holds(c, width, on) for c in r.conditions):
                continue
            hits = [(s, matches(s, chain)) for s in r.selectors]
            hits = [(s, m) for s, m in hits if m is not False]
            if not hits:
                continue
            sel, m = max(hits, key=lambda h: specificity(h[0]))
            for k, (p, v, imp) in enumerate(r.decls):
                if p in props:
                    found.append(((imp, specificity(sel), r.order, k),
                                  Win(p, v, sel, r, m is True)))
        return [w for _, w in sorted(found, key=lambda f: f[0])]

    def winner(self, chain: list, props, width: float = 1280,
               on=()) -> Win | None:
        """The declaration of `props` the cascade gives the last element
        of `chain`; None when no rule sets it."""
        c = self.candidates(chain, props, width, on)
        return c[-1] if c else None

    def value(self, chain: list, prop: str, width: float = 1280,
              on=()) -> str | None:
        w = self.winner(chain, prop, width, on)
        return None if w is None else w.value

    def token(self, chain: list, name: str, width: float = 1280,
              on=()) -> str | None:
        """A custom property as the last element of `chain` inherits it,
        its var() references resolved."""
        for i in range(len(chain), 0, -1):
            w = self.winner(chain[:i], name, width, on)
            if w is not None:
                return self.resolve(w.value, chain[:i], width, on)
        return None

    def resolve(self, value: str, chain: list, width: float = 1280,
                on=()) -> str:
        """`value` with each var(--x[, fallback]) replaced."""
        for _ in range(20):
            m = re.search(r"var\(\s*(--[\w-]+)\s*(?:,([^()]*))?\)", value)
            if not m:
                return value
            got = self.token(chain, m.group(1), width, on)
            if got is None:
                got = (m.group(2) or "").strip()
            value = value[:m.start()] + got + value[m.end():]
        raise ValueError(f"var() loop in {value!r}")


# ---------------------------------------------------------------- lengths

def px(value: str, root_px: float = 16.0, vw_px: float = 1280.0,
       pct_of: float | None = None) -> float:
    """A length in px: px, rem and em (at the root's size: the Display
    menu's text size sets it), vw, % (of `pct_of`), calc(), min(), max()
    and clamp(); "none" is no limit."""
    units = {"px": 1.0, "rem": root_px, "em": root_px, "vw": vw_px / 100}

    def num(m):
        n, unit = float(m.group(1)), m.group(2)
        if unit == "%":
            if pct_of is None:
                raise ValueError(f"% with nothing to take it of: {value!r}")
            return repr(n * pct_of / 100)
        return repr(n * units[unit])

    expr = re.sub(r"(-?\d*\.?\d+)(px|rem|em|vw|%)", num, value.strip())
    expr = expr.replace("calc(", "(")
    if expr == "none":
        return float("inf")
    if re.search(r"[^\d.eE\s+\-*/(),]",
                 re.sub(r"\b(min|max|clamp)\(", "(", expr)):
        raise ValueError(f"cannot size {value!r}")
    return float(eval(expr, {"__builtins__": {}},           # noqa: S307
                      {"min": min, "max": max,
                       "clamp": lambda lo, v, hi: max(lo, min(v, hi))}))


# ------------------------------------------------------------------ color

def _rgb(hex_: str) -> tuple:
    h = hex_.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"not a hex color: {hex_!r}")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two hex colors."""
    def lum(c):
        lin = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4
               for x in _rgb(c)]
        return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


def themes() -> list:
    """The theme ids nau.css carries a token block for, in file order."""
    text = (STATIC / "nau.css").read_text(encoding="utf-8")
    seen = []
    for t in re.findall(r'^\[data-theme="([\w-]+)"\]', text, flags=re.M):
        if t not in seen:
            seen.append(t)
    return seen
