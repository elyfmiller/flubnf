"""SANDBOX: the model library, Sandbox models registered for replays
(app/core/experiments.py) and the engine's reading of a registered model
(engines/pf.py prepare, through resolve and replay_conf; the Register
button comes in a later step).

A model ready for replays is the Sandbox's own three-file folder with its
placeholders kept ({{POP}}, {{I0FRAC}}, ...: what sihrs_fit.
materialize_model fills per location and week). validate() says whether
it is ready; nothing is stored in the Sandbox folder for it. register()
freezes one as a version:

  sandbox/library/<name>/<n>/   n = 1, 2, ... (the highest plus 1)
    model.bngl, priors.conf     their replay normal form (replay_text):
                                newlines pinned to LF, outer whitespace
                                dropped, one final newline, and in
                                model.bngl FluBNF's own actions after end
                                model
    model.json                  {"format_version": 1, "fingerprint",
                                "files": {file: sha256 of its stored
                                bytes}, "registered_utc", and "origin"
                                when the Sandbox model.json has one},
                                written once and never rewritten

A reference is name@version (beta2@3), or a bare shipped name (sihrs):
the shipped models (SHIPPED_NAMES) are composed from the repository as
the engine composes them (shipped_files) and stored nowhere.

The fingerprint is sha256 over the canonical JSON of the two files'
hashes, each taken over the exact bytes stored, so `shasum -a 256` on a
stored file reproduces its entry in model.json. Comments are inside it
(a comment edit is a new version); the model's own actions, data.exp,
model.json, the name, the version and the time are not. A field added
later enters the hashed object only when it differs from its default, so
a fingerprint stays valid. resolve() hashes the bytes again every time:
a version that no longer matches is MODEL_CHANGED, and so is one register
would not have stored (a folder written by hand, whose hashes agree with
themselves): text not in its normal form, or breaking validate's own
rules.

The rules (_rules) are validate's, resolve's and the engine's: what a
replay would refuse is refused at Register and at every resolve too, and
the engine writes priors.conf's values again rather than copying them
(replay_conf).

Findings and refusals carry the codes of app/core/problem_codes.py.
"""
from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Mapping

from app.core import sandbox as sb
from app.core.engines import pf as pf_engine
from app.core.problem_codes import Refusal, finding
from app.core.sandbox_bngl import (RANGE_PRIORS, SPREAD_PRIORS, bngl_outputs,
                                   bngl_parameters)
from flubnf.sihrs_fit import (GAMMAH_PER_WEEK, OMEGA_PER_WEEK, RHO_IHR,
                              _TOKEN_RE)
from flubnf.sihrs_priors import S0_DEFAULT, gamma_per_week

REPLAY_FILES = ("model.bngl", "priors.conf")
MANIFEST = "model.json"
FORMAT_VERSION = 1
SHIPPED_NAMES = ("sihrs", "sihrs-2strain", "sihrs-natg")
#: the placeholders materialize_model fills in any model
TOKENS = ("{{POP}}", "{{I0FRAC}}", "{{S0FRAC}}", "{{GAMMA}}", "{{RHO}}",
          "{{GAMMAH}}", "{{OMEGA}}")
#: the shipped models' own placeholders: they switch on hub-only data
#: feeds (the two-strain NREVSS channel, natg's growth gap)
SHIPPED_TOKENS = ("{{A0SHARE}}", "{{IOTA}}", "{{GAPEXPR}}", "{{GAPNOTE}}")
#: a model needs one of these, or every location runs one location's values
STATE_TOKENS = ("{{POP}}", "{{I0FRAC}}")
#: what Check's run of a model ready for replays puts in each placeholder:
#: a sample location, then the constants from where materialize_model
#: reads them, written as it writes them
SAMPLE_TOKENS = {
    "{{POP}}": "1000000",
    "{{I0FRAC}}": "1e-05",
    "{{S0FRAC}}": f"{float(S0_DEFAULT):g}",
    "{{GAMMA}}": f"{gamma_per_week():.6f}",
    "{{RHO}}": f"{RHO_IHR:g}",
    "{{GAMMAH}}": f"{GAMMAH_PER_WEEK:g}",
    "{{OMEGA}}": f"{OMEGA_PER_WEEK:g}",
    "{{A0SHARE}}": "0.8500",
    "{{IOTA}}": "0.302",
    "{{GAPEXPR}}": "0",
    "{{GAPNOTE}}": "sample",
}
#: the data.exp Check reads beside it: a replay writes its own per cell
SAMPLE_EXP = "# time H_weekly\n1 1\n2 1\n"
#: the one priors.conf key besides the priors: the runner writes the rest
REPLAY_KEYS = ("pf_cumulative_observable",)
#: the blocks a model may hold between begin model and end model
MODEL_BLOCKS = ("parameters", "compartments", "molecule types", "species",
                "seed species", "observables", "functions", "reaction rules",
                "energy patterns", "population types", "population maps")
#: the end model line: contactmap._with_actions' pattern held to one line
#: (its \s* would run on over blank lines into a comment after end model,
#: and keep that comment in the stored text)
END_MODEL_RE = re.compile(r"^[ \t]*end[ \t]+model[ \t]*(?:#.*)?$", re.M)
#: model.bngl as BNG2.pl reads it (BNGModel.pm readFile and get_line): the
#: file as bytes, so its whitespace is ASCII only; a line ending in a
#: backslash goes on to the next; begin model, and a block's end at any
#: end line (BNG2.pl stops on one whose name does not match)
_WS = " \t\n\r\f\v"
_CONTINUED = re.compile(r"\\\s*$", re.ASCII)
_BEGIN_MODEL = re.compile(r"begin\s+model\s*$", re.ASCII)
_BLOCK_END = re.compile(r"\s*end\s+", re.ASCII)
#: the line breaks of Python's str.splitlines besides \n and \r, which
#: BNG2.pl reads as none: PyBNF reads the model again through splitlines
#: (pybnf/pset.py BNGLModel) and writes what it read back out for BNG2.pl,
#: so a comment could end at one for PyBNF and hide a statement
#: (LINE_BREAK_NOT_ALLOWED)
_BREAKS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")
#: the actions every replay runs (the suffix is rewritten per cell)
REPLAY_ACTIONS = ('begin actions\n'
                  'generate_network({overwrite=>1})\n'
                  'simulate({suffix=>"SIHRS_flu",method=>"ode",t_start=>0,'
                  't_end=>48,n_steps=>48,print_functions=>1})\n'
                  'end actions')
#: the actions a replay keeps the gist of; any other is said to be dropped
_KEPT_ACTION = re.compile(r"^(?:generate_network|simulate)\s*\(")
REF_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]{0,63})(?:@([1-9][0-9]{0,5}))?$")
#: a version folder's name; .reg-* building folders are not one
_VERSION_RE = re.compile(r"[1-9][0-9]{0,5}")
#: check() codes a model ready for replays never keeps: data.exp is the
#: sample's, the cumulative line is CUMULATIVE_REQUIRED here, and the
#: actions are FluBNF's
_CHECK_DROPPED = ("EXP_UNREADABLE", "EXP_TIME_ORDER", "ROW_BEFORE_START",
                  "ONE_ROW", "SCALE_OFF", "NO_CUMULATIVE", "NO_SUFFIX",
                  "NO_GENERATE_NETWORK")
#: the most dropped action lines ACTIONS_DROPPED names
_DROPPED_SHOWN = 5
#: a suffix named before end model: materialize_model rewrites every
#: suffix=>"..." in the file, comments included (SUFFIX_IN_MODEL)
_SUFFIX = re.compile(r"suffix\s*=>")
#: a prior's number: a subset of PyBNF's number grammar (pybnf/parse.py),
#: ASCII digits, a digit before any point, no bounds letter after it
_NUMBER = re.compile(r"[+-]?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?")
#: a fitted parameter's name: PyBNF's bng_parameter, ending in __FREE
_FREE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*__FREE")
#: the output pf_cumulative_observable names
_OUTPUT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def root() -> Path:
    """The library folder, read at call time (the tests move the sandbox)."""
    return sb.SANDBOX / "library"


# ------------------------------------------------- normal form, fingerprint


def _lf(text: str) -> str:
    """The text without a byte order mark, its newlines pinned to LF."""
    return (text.removeprefix("\ufeff").replace("\r\n", "\n")
            .replace("\r", "\n"))


def replay_text(name: str, text: str) -> str:
    """The text Register stores for one replay file, and what its hash is
    taken over: newlines pinned to LF, outer whitespace dropped, one final
    newline, and in model.bngl FluBNF's own actions after end model."""
    text = _lf(text)
    if name == "model.bngl":
        m = END_MODEL_RE.search(text)
        if m is None:
            raise Refusal(finding("NO_MODEL_BLOCK", _NO_MODEL_BLOCK,
                                  file="model.bngl"))
        text = text[:m.end()].rstrip() + "\n\n" + REPLAY_ACTIONS
    return text.strip() + "\n"


def _canonical(obj) -> bytes:
    """knobs._canonical's JSON: sorted keys, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_hashes(files: Mapping[str, str]) -> dict[str, str]:
    """sha256 of each replay file's stored bytes (replay_text)."""
    return {f: hashlib.sha256(replay_text(f, files[f]).encode("utf-8")).hexdigest()
            for f in REPLAY_FILES}


def fingerprint(hashes: Mapping[str, str]) -> str:
    """A model's identity: sha256 over the canonical JSON of file_hashes
    (or a model.json's "files")."""
    return hashlib.sha256(_canonical(dict(hashes))).hexdigest()


def short(fp: str) -> str:
    """A fingerprint as shown: its first 8 hex characters (as
    knobs.digest); files store and compare all 64."""
    return str(fp)[:8]


def tokens(bngl: str) -> set[str]:
    """The placeholders model.bngl uses, comments included (materialize_
    model fills and refuses over the whole text)."""
    return set(_TOKEN_RE.findall(bngl))


# ----------------------------------------------------------------- validate

_NO_MODEL_BLOCK = ("model.bngl has no begin model ... end model: a replay "
                   "keeps the model's blocks and runs FluBNF's own actions "
                   "after end model")


def _text(value) -> str | None:
    """A file's text: a str as given, bytes decoded as strict UTF-8; None
    when it is missing or not UTF-8 text."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _code(line: str) -> str:
    """A line without its comment, stripped."""
    return line.split("#", 1)[0].strip()


def _bngl_lines(lines: list) -> list:
    """(number, line) of each line BNG2.pl reads (get_line in
    BNGModel.pm): its comment cut, a blank one skipped, and one ending in
    a backslash joined to the next."""
    out, i = [], 0
    while i < len(lines):
        n, line = i + 1, lines[i].split("#", 1)[0]
        i += 1
        if not line.strip(_WS):
            continue
        while True:
            line, joined = _CONTINUED.subn("", line)
            if not joined or i == len(lines):
                break
            line += lines[i].split("#", 1)[0]
            i += 1
        out.append((n, line))
    return out


def _structure(bngl: str) -> list:
    """The structure rules on model.bngl as written (LF only, _lf), read
    as BNG2.pl reads it up to the end model line replay_text cuts at:
    NO_MODEL_BLOCK, OUTSIDE_MODEL, BLOCK_NOT_ALLOWED and ACTIONS_DROPPED;
    and LINE_BREAK_NOT_ALLOWED up to that line and on it, where PyBNF
    would read other lines than BNG2.pl. A statement outside every block
    is what BNG2.pl runs through Perl."""
    out = []
    m = END_MODEL_RE.search(bngl)
    lines = bngl.split("\n")
    end = bngl.count("\n", 0, m.start()) if m else 0
    for i, line in enumerate(lines[:end + 1], 1):
        b = _BREAKS.search(line)
        if b:
            out.append(finding(
                "LINE_BREAK_NOT_ALLOWED", f"model.bngl line {i}: "
                f"{b.group()!r} is a line break to PyBNF, which reads the "
                "model too, and not to BNG2.pl, so the two would read "
                "different lines; write a newline or a space instead",
                file="model.bngl", line=i))
    in_model, block = False, None
    for i, line in _bngl_lines(lines[:end]):
        if block is not None:
            if _BLOCK_END.match(line):
                block = None
            continue
        s = line.strip(_WS)
        if not in_model and _BEGIN_MODEL.match(s):
            in_model = True
        elif in_model and s.startswith("begin"):
            # BNG2.pl's block name: after begin, spaces collapsed
            block = name = re.sub(r"\s+", " ", s[5:].strip(_WS),
                                  flags=re.ASCII)
            if name not in MODEL_BLOCKS:
                out.append(finding(
                    "BLOCK_NOT_ALLOWED", f"model.bngl line {i}: begin {name} "
                    "is not a model block (the model may hold "
                    f"{', '.join(MODEL_BLOCKS)})", file="model.bngl", line=i))
        elif s:
            where = "inside begin model" if in_model else "before begin model"
            out.append(finding(
                "OUTSIDE_MODEL", f"model.bngl line {i}: {s!r} stands outside "
                f"every block, {where}: BNG2.pl would run it as a statement, "
                "so it belongs in a block or after end model",
                file="model.bngl", line=i))
    if not in_model:
        # a bare model, or none: one problem, not one per line of it
        return [finding("NO_MODEL_BLOCK", _NO_MODEL_BLOCK, file="model.bngl")]
    dropped, continued = [], False
    for line in lines[end + 1:]:
        s = _code(line)
        if continued:
            continued = s.endswith("\\")
            continue
        if not s or " ".join(s.split()) in ("begin actions", "end actions"):
            continue
        if _KEPT_ACTION.match(s):
            continued = s.endswith("\\")
            continue
        dropped.append(s)
        continued = s.endswith("\\")
    if dropped:
        more = len(dropped) - _DROPPED_SHOWN
        named = "; ".join(dropped[:_DROPPED_SHOWN]) + (
            f" (and {more} more)" if more > 0 else "")
        out.append(finding(
            "ACTIONS_DROPPED", "a replay runs FluBNF's own actions (generate "
            "the network, simulate), so these lines after end model are "
            f"dropped: {named}", file="model.bngl"))
    return out


def _tokens_rules(files: Mapping[str, str], shipped: bool) -> list:
    """The placeholder rules: TOKEN_MALFORMED, SUFFIX_IN_MODEL (the
    suffix is a placeholder FluBNF fills too), TOKEN_UNKNOWN,
    NO_STATE_TOKENS and the GAMMA_ASSUMED warning."""
    out = []
    bngl = files["model.bngl"]
    for i, line in enumerate(bngl.splitlines(), 1):
        left = _TOKEN_RE.sub("", line)
        if "{{" in left or "}}" in left:
            out.append(finding(
                "TOKEN_MALFORMED", f"model.bngl line {i}: double braces that "
                "are not a placeholder; one is written {{NAME}}, capitals, "
                "digits and _ only, no spaces", file="model.bngl", line=i))
        if _SUFFIX.search(line):
            out.append(finding(
                "SUFFIX_IN_MODEL", f"model.bngl line {i}: a suffix "
                "(suffix=>) before end model: FluBNF writes each location's "
                "suffix into its own actions, over the whole file, comments "
                "included, so the model may not name one", file="model.bngl",
                line=i))
    for i, line in enumerate(files["priors.conf"].splitlines(), 1):
        if "{{" in line or "}}" in line:
            out.append(finding(
                "TOKEN_MALFORMED", f"priors.conf line {i}: double braces; "
                "FluBNF fills placeholders in model.bngl only",
                file="priors.conf", line=i))
    used = tokens(bngl)
    allowed = set(TOKENS) | (set(SHIPPED_TOKENS) if shipped else set())
    for t in sorted(used - allowed):
        why = ("it switches on a hub-only data feed, so FluBNF fills it for "
               "the shipped models only" if t in SHIPPED_TOKENS else
               f"FluBNF fills {', '.join(TOKENS)}")
        out.append(finding("TOKEN_UNKNOWN", f"model.bngl uses {t}, which "
                           f"FluBNF does not fill for this model: {why}",
                           file="model.bngl"))
    if not used & set(STATE_TOKENS):
        out.append(finding(
            "NO_STATE_TOKENS", "model.bngl uses neither {{POP}} nor "
            "{{I0FRAC}}: every location would run with this one location's "
            "values; write {{POP}} for the population (and {{I0FRAC}} for "
            "the data's starting infected fraction)", file="model.bngl"))
    if "{{I0FRAC}}" in used and "{{GAMMA}}" not in used:
        out.append(finding(
            "GAMMA_ASSUMED", "model.bngl uses {{I0FRAC}} without {{GAMMA}}: "
            "the starting infected fraction FluBNF derives from the data "
            "assumes a removal rate of 7/3.2 per week, whatever this model "
            "writes", file="model.bngl"))
    return out


def _conf(files: Mapping[str, str]) -> tuple[list, str, str]:
    """(findings, the cumulative output, the prior lines) of priors.conf,
    read against model.bngl as given (_rules gives it up to end model).
    Each line is read without its comment, stripped, and gives the first
    finding of these it meets: PRIORS_LINE (no '='); CUMULATIVE_NOT_OUTPUT
    (pf_cumulative_observable naming no observable or function);
    KEY_NOT_ALLOWED (any other key but a prior kind); PRIOR_MALFORMED
    (not 'kind = name low high', each number in PyBNF's form and finite);
    PRIOR_NOT_FREE; PRIOR_UNDEFINED; PRIOR_BOUNDS. Then
    CUMULATIVE_REQUIRED without a cumulative line, and FREE_NO_PRIOR for
    each __FREE parameter of model.bngl no prior line names. The
    cumulative output is the first line's; each prior is written again as
    'kind = name low high', each number its float's repr, in file order."""
    out, cums, priors, named = [], [], [], set()
    kinds = RANGE_PRIORS + SPREAD_PRIORS
    bngl = files["model.bngl"]
    params, outputs = bngl_parameters(bngl), bngl_outputs(bngl)

    def problem(code: str, text: str) -> None:
        out.append(finding(code, f"priors.conf line {i}: {text}",
                           file="priors.conf", line=i))
    for i, line in enumerate(files["priors.conf"].splitlines(), 1):
        s = _code(line)
        if not s:
            continue
        if "=" not in s:
            problem("PRIORS_LINE", f"{s!r} has no '=': every line is 'key "
                    "= value', a prior 'uniform_var = name low high'")
            continue
        k, v = (x.strip() for x in s.split("=", 1))
        if k in REPLAY_KEYS:
            cums.append(v)
            if not (_OUTPUT_NAME.fullmatch(v) and v in outputs):
                problem("CUMULATIVE_NOT_OUTPUT", "pf_cumulative_observable "
                        f"names {v!r}, which is neither an observable nor a "
                        "function of the model")
            continue
        if k not in kinds:
            problem("KEY_NOT_ALLOWED", f"{k} is not a key a model for "
                    "replays may set (the priors and pf_cumulative_observable "
                    "only: every replay runs the shipped filter settings)")
            continue
        toks = v.split()
        if toks:
            named.add(toks[0])           # one problem for it, not two
        if len(toks) != 3:
            problem("PRIOR_MALFORMED", f"{s!r}: a prior is '{k} = name low "
                    "high', a name and two numbers, nothing after them")
            continue
        name, lo, hi = toks
        nums = [float(x) if _NUMBER.fullmatch(x) else None for x in (lo, hi)]
        if not all(x is not None and math.isfinite(x) for x in nums):
            problem("PRIOR_MALFORMED", f"{s!r}: {lo} and {hi} must be finite "
                    "numbers, written with digits and a point (2.5, 0.1, "
                    "1e-3)")
            continue
        if not _FREE_NAME.fullmatch(name):
            if not name.endswith("__FREE"):
                problem("PRIOR_NOT_FREE", f"{name} has a prior line but its "
                        "name does not end in __FREE: only a __FREE "
                        "parameter is fitted")
            else:
                problem("PRIOR_MALFORMED", f"{name} is not a parameter name: "
                        "a letter first, then letters, digits and _")
            continue
        if name not in params:
            problem("PRIOR_UNDEFINED", f"{k} names {name}, which the "
                    "parameters block does not define")
            continue
        a, b = nums
        if k in RANGE_PRIORS and a >= b:
            problem("PRIOR_BOUNDS", f"{k} {name}: the low end {lo} is not "
                    f"below the high end {hi}")
        elif k == "loguniform_var" and a <= 0:
            problem("PRIOR_BOUNDS", f"loguniform_var {name}: the low end must "
                    "be above 0")
        elif k in SPREAD_PRIORS and b <= 0:
            problem("PRIOR_BOUNDS", f"{k} {name}: the spread {hi} must be "
                    "above 0")
        else:
            priors.append(f"{k} = {name} {a!r} {b!r}\n")
    if not cums:
        out.append(finding(
            "CUMULATIVE_REQUIRED", "priors.conf has no "
            "pf_cumulative_observable line: a replay fits each week's "
            "count as the increment of the output it names",
            file="priors.conf"))
    for p in dict.fromkeys(params):
        if p.endswith("__FREE") and p not in named:
            out.append(finding(
                "FREE_NO_PRIOR", f"{p} ends in __FREE but has no prior line: "
                "give it one in priors.conf, or drop __FREE to keep its "
                "written value fixed", file="priors.conf"))
    return out, (cums[0] if cums else ""), "".join(priors)


def replay_conf(files: Mapping[str, str]) -> tuple[str, str]:
    """(the cumulative output, the prior lines) a replay writes into a
    library model's pf.conf: priors.conf parsed (_conf, against model.bngl
    up to end model as _rules cuts it) and written again, never copied:
    the first pf_cumulative_observable's value, and each prior as
    'kind = name low high' with each number its float's repr, in file
    order. Refusal for any problem (resolve has refused such a version
    already)."""
    texts = {f: _lf(files[f]) for f in REPLAY_FILES}
    m = END_MODEL_RE.search(texts["model.bngl"])
    if m:
        texts["model.bngl"] = texts["model.bngl"][:m.end()]
    found, cum, priors = _conf(texts)
    if found:
        raise Refusal(found)
    return cum, priors


def _replay_rules(files: Mapping[str, str]) -> list:
    """priors.conf's rules (_conf), NO_H_WEEKLY and NO_DISPERSION."""
    out = _conf(files)[0]
    bngl = files["model.bngl"]
    if "H_weekly" not in bngl_outputs(bngl):
        out.append(finding(
            "NO_H_WEEKLY", "model.bngl has no observable or function named "
            "H_weekly: a replay's data file names its count column "
            "H_weekly", file="model.bngl"))
    if "r__FREE" not in bngl_parameters(bngl):
        out.append(finding(
            "NO_DISPERSION", "model.bngl defines no r__FREE: a replay fits "
            "the negative-binomial dispersion r__FREE with its prior",
            file="model.bngl"))
    return out


def _rules(texts: Mapping[str, str], shipped: bool) -> list:
    """validate's own rules on the two texts (LF only, _lf): the
    structure of model.bngl, then the placeholder and replay rules on what
    a replay keeps of it, up to end model (FluBNF's actions replace the
    rest, so a placeholder or a block there counts for nothing)."""
    bngl = texts["model.bngl"]
    m = END_MODEL_RE.search(bngl)
    kept = dict(texts, **{"model.bngl": bngl[:m.end()] if m else bngl})
    return (_structure(bngl) + _tokens_rules(kept, shipped)
            + _replay_rules(kept))


def validate(files: Mapping[str, str], *, shipped: bool = False,
             work: Path | None = None) -> list[dict]:
    """Whether model.bngl and priors.conf are ready for replays, as
    findings: FILE_UNREADABLE; the structure of model.bngl; its
    placeholders; the priors.conf keys, the cumulative line, H_weekly and
    r__FREE; and, only when none of these is a problem, Check itself
    (sandbox_check.check) on the stored text with the sample placeholders
    and data (SAMPLE_TOKENS, SAMPLE_EXP), keeping its codes but the data's,
    the actions' and NO_CUMULATIVE. A file's bytes are read as strict
    UTF-8, and the rules read it as replay_text does: no byte order mark,
    LF newlines. shipped allows the shipped models' own placeholders."""
    texts = {f: _text(files.get(f)) for f in REPLAY_FILES}
    out = [finding("FILE_UNREADABLE", f"{f} is missing or is not UTF-8 "
                   "text", file=f) for f, t in texts.items() if t is None]
    if out:
        return out
    texts = {f: _lf(t) for f, t in texts.items()}
    out = _rules(texts, shipped)
    if any(f["tier"] == "problem" for f in out):
        return out
    from app.core.sandbox_check import check
    bngl = replay_text("model.bngl", texts["model.bngl"])
    for t, v in SAMPLE_TOKENS.items():
        bngl = bngl.replace(t, v)
    r = check({"model.bngl": bngl, "priors.conf": texts["priors.conf"],
               "data.exp": SAMPLE_EXP}, work=work)
    return out + [f for f in r["codes"] if f["code"] not in _CHECK_DROPPED]


# ---------------------------------------------------------- shipped models


def _shipped_parts(name: str) -> tuple:
    """(template path, starting values, priors) of a shipped model, as
    engines/pf.py prepare composes it."""
    return {"sihrs": (pf_engine.TEMPLATE, pf_engine.DEFAULTS_BLOCK,
                      pf_engine.VARS_1S),
            "sihrs-2strain": (pf_engine.TEMPLATE_2S, pf_engine.DEFAULTS_2S,
                              pf_engine.VARS_2S),
            "sihrs-natg": (pf_engine.TEMPLATE_NATG, pf_engine.DEFAULTS_BLOCK,
                           pf_engine.VARS_1S)}[name]


def shipped_files(name: str) -> dict[str, str]:
    """A shipped model's two replay files, composed from the repository:
    its template with the starting values spliced in and the placeholders
    kept, and its priors with pf_cumulative_observable."""
    tmpl, start, priors = _shipped_parts(name)
    return {"model.bngl": tmpl.read_text(encoding="utf-8")
                              .replace("begin parameters\n", start, 1),
            "priors.conf": priors + "pf_cumulative_observable = Hobs\n"}


# ---------------------------------------------------------------- references


def parse_ref(ref: str) -> tuple[str, int | None]:
    """(name, version) of name@version, or (name, None) of a bare shipped
    name; MODEL_REF otherwise."""
    # fullmatch: $ alone would take "sihrs\n" for sihrs
    m = REF_RE.fullmatch(ref) if isinstance(ref, str) else None
    if m is None:
        raise Refusal(finding(
            "MODEL_REF", f"{ref!r} is not a model reference: write "
            "name@version, such as beta2@3, or a shipped model's name "
            f"({', '.join(SHIPPED_NAMES)})"))
    name, version = m.group(1), m.group(2)
    if version is None and name not in SHIPPED_NAMES:
        fix = (f"the shipped model is {name.lower()}, in small letters"
               if name.lower() in SHIPPED_NAMES else
               f"write {name}@1 or the version wanted (a library model is "
               "always named with its version)")
        raise Refusal(finding("MODEL_REF",
                              f"{ref!r} names no version: {fix}"))
    if version is not None and name.lower() in SHIPPED_NAMES:
        raise Refusal(finding(
            "MODEL_REF", f"{ref!r}: {name.lower()} is a shipped model, named "
            "without a version"))
    return name, (int(version) if version is not None else None)


def _versions(name: str) -> list[int]:
    """The version numbers under library/<name>/, ascending."""
    d = root() / name
    if not d.is_dir():
        return []
    return sorted(int(p.name) for p in d.iterdir()
                  if p.is_dir() and _VERSION_RE.fullmatch(p.name))


def _names() -> list[str]:
    """The library's model names, sorted ignoring case."""
    if not root().is_dir():
        return []
    return sorted((p.name for p in root().iterdir()
                   if p.is_dir() and sb.NAME_RE.fullmatch(p.name)),
                  key=lambda n: (n.lower(), n))


def _changed(ref: str, what: str) -> Refusal:
    return Refusal(finding(
        "MODEL_CHANGED", f"{ref}: {what} no longer matches as registered; a "
        "version is never edited, so register the model again for a new "
        "one"))


def _verified(name: str, version: int) -> tuple[dict, dict]:
    """(model.json, {file: stored text}) of one version, its bytes hashed
    again: MODEL_CHANGED naming the file (or model.json) that no longer
    matches, or that register would not have stored (a version written
    by hand, however well its hashes agree), FORMAT_UNKNOWN for a
    model.json of another format."""
    ref, d = f"{name}@{version}", root() / name / str(version)
    try:
        manifest = json.loads((d / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _changed(ref, f"{MANIFEST} (missing or unreadable)") from None
    if not isinstance(manifest, dict):
        raise _changed(ref, MANIFEST)
    v = manifest.get("format_version")
    if type(v) is not int or v != FORMAT_VERSION:     # true is not 1
        raise Refusal(finding(
            "FORMAT_UNKNOWN", f"{ref}: {MANIFEST} is format_version "
            f"{v!r}; this FluBNF reads {FORMAT_VERSION} only"))
    hashes = manifest.get("files")
    if not isinstance(hashes, dict) or set(hashes) != set(REPLAY_FILES):
        raise _changed(ref, MANIFEST)
    texts = {}
    for f in REPLAY_FILES:
        try:
            raw = (d / f).read_bytes()
        except OSError:
            raise _changed(ref, f"{f} (missing)") from None
        if hashlib.sha256(raw).hexdigest() != hashes[f]:
            raise _changed(ref, f)
        try:
            texts[f] = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _changed(ref, f"{f} (not UTF-8)") from None
    if fingerprint(hashes) != manifest.get("fingerprint"):
        raise _changed(ref, MANIFEST)
    bad = next((x for x in _rules(texts, False) if x["tier"] == "problem"),
               None)
    if bad is not None:
        raise _changed(ref, f"{bad['file']} ({bad['code']})")
    for f in REPLAY_FILES:              # the rules found end model
        if replay_text(f, texts[f]) != texts[f]:
            raise _changed(ref, f"{f} (not in its replay normal form)")
    return manifest, texts


def resolve(ref: str) -> dict:
    """{"ref", "name", "version", "fingerprint", "files" (the stored
    texts), "folder" (None for a shipped model), "shipped"}; MODEL_REF,
    MODEL_NOT_FOUND (naming the versions there are), MODEL_CHANGED or
    FORMAT_UNKNOWN otherwise."""
    name, version = parse_ref(ref)
    if version is None:
        files = {f: replay_text(f, t) for f, t in shipped_files(name).items()}
        return {"ref": name, "name": name, "version": None,
                "fingerprint": fingerprint(file_hashes(files)),
                "files": files, "folder": None, "shipped": True}
    # the exact name: a folder that differs only in case is another model
    have = _versions(name) if name in _names() else []
    if version not in have:
        there = (f"its versions are {', '.join(map(str, have))}" if have
                 else "the library has no model of that name")
        raise Refusal(finding("MODEL_NOT_FOUND",
                              f"{ref}: no such version; {there}"))
    manifest, texts = _verified(name, version)
    return {"ref": f"{name}@{version}", "name": name, "version": version,
            "fingerprint": manifest["fingerprint"], "files": texts,
            "folder": root() / name / str(version), "shipped": False}


def list_models() -> list[dict]:
    """Every model a replay can name: the shipped ones first, then the
    library's names (ignoring case) with their versions ascending. A
    version whose files no longer match reads intact False."""
    rows = []
    for n in SHIPPED_NAMES:
        r = resolve(n)
        rows.append({"ref": n, "name": n, "version": None,
                     "fingerprint": r["fingerprint"],
                     "short": short(r["fingerprint"]), "registered_utc": None,
                     "note": sb._first_comment(_shipped_parts(n)[0]),
                     "origin": None, "intact": True, "shipped": True})
    for n in _names():
        for v in _versions(n):
            d = root() / n / str(v)
            try:
                manifest, intact = _verified(n, v)[0], True
            except Refusal:
                manifest, intact = _read_json(d / MANIFEST), False
            fp = str(manifest.get("fingerprint") or "")
            rows.append({"ref": f"{n}@{v}", "name": n, "version": v,
                         "fingerprint": fp, "short": short(fp),
                         "registered_utc": manifest.get("registered_utc"),
                         "note": sb._first_comment(d / "model.bngl"),
                         "origin": manifest.get("origin"), "intact": intact,
                         "shipped": False})
    return rows


def _read_json(path: Path) -> dict:
    """A JSON object, or {} (none, unreadable, not an object)."""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


# ------------------------------------------------------------------ register


def _check_name(name: str) -> None:
    """The name rules: a model name, not a shipped one, and not another
    library name in other letter case."""
    if not isinstance(name, str) or not sb.NAME_RE.fullmatch(name):
        raise Refusal(finding(
            "NAME_INVALID", f"{name!r} is not a model name: letters, "
            "digits, _ and -, up to 64 characters, starting with a letter "
            "or digit"))
    if name.lower() in SHIPPED_NAMES:
        raise Refusal(finding(
            "NAME_RESERVED", f"{name} is a shipped model's name; give the "
            "Sandbox model another name to register it"))
    clash = [n for n in _names() if n.lower() == name.lower() and n != name]
    if clash:
        raise Refusal(finding(
            "NAME_INVALID", f"{name} is the same as {clash[0]} ignoring "
            "case: macOS folders ignore case"))


def register(name: str) -> dict:
    """Freeze the Sandbox model `name` as the library's next version of
    it: {"ref", "version", "fingerprint", "new", "findings" (the
    warnings)}. Files identical to an intact version return that version
    with new False and write nothing. Refusal for a bad name or any
    problem validate finds. The Sandbox folder is only read."""
    _check_name(name)
    src = sb.MODELS / name
    raw = {}
    # the exact name: where folders ignore case (macOS, Windows) BETA2
    # would read beta2's files and register them renamed
    if sb.MODELS.is_dir() and name in {p.name for p in sb.MODELS.iterdir()}:
        for f in REPLAY_FILES:
            try:
                raw[f] = (src / f).read_bytes()
            except OSError:
                pass
    found = validate(raw, work=sb.SANDBOX / "check")
    if any(f["tier"] == "problem" for f in found):
        raise Refusal(found)
    stored = {f: replay_text(f, raw[f].decode("utf-8")) for f in REPLAY_FILES}
    hashes = file_hashes(stored)
    fp = fingerprint(hashes)
    for v in _versions(name):
        try:
            if _verified(name, v)[0]["fingerprint"] == fp:
                return {"ref": f"{name}@{v}", "version": v,
                        "fingerprint": fp, "new": False, "findings": found}
        except Refusal:
            continue                       # a changed version is not this one
    manifest = {"format_version": FORMAT_VERSION, "fingerprint": fp,
                "files": hashes, "registered_utc": sb._stamp()}
    origin = sb.read_info(name).get("origin")
    if isinstance(origin, str) and origin:
        manifest["origin"] = origin
    folder = root() / name
    tmp = folder / f".reg-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        tmp.mkdir(parents=True)
        for f in REPLAY_FILES:
            (tmp / f).write_text(stored[f], encoding="utf-8", newline="\n")
        write_json(tmp / MANIFEST, manifest)
        n = max(_versions(name), default=0) + 1
        while True:
            try:
                os.rename(tmp, folder / str(n))
                break
            except OSError as e:
                # another version took n first (a version folder is never
                # empty): EEXIST or ENOTEMPTY here, FileExistsError on
                # Windows
                if e.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                    raise
                n += 1
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            folder.rmdir()                 # only when nothing else is there
        except OSError:
            pass
        raise
    return {"ref": f"{name}@{n}", "version": n, "fingerprint": fp,
            "new": True, "findings": found}


def write_json(path: Path, obj: Mapping) -> None:
    """A record FluBNF writes, in the house style (indent 1, sorted keys,
    one final newline, UTF-8, LF), beside and then replaced into place."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    pf_engine.replace_file(tmp, path)
