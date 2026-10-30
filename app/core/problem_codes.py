"""REGISTRY: every problem code the student workspace says, with its one
tier and its meaning (Check in app/core/sandbox_check.py, the library in
app/core/library.py, experiments in app/core/experiments.py).

A finding is {"code", "tier", "text"}, plus "file" and "line" when they
are known: the code for callers and tests, the text in words for people.
Tiers: "problem" (a run or a registration would fail), "warning" (worth
a look) and "machine" (this computer, never the model).

Codes are UPPER_SNAKE and append-only: never renamed, reused or moved to
another tier (app/tests/golden/problem_codes.json holds each code's tier,
and may only grow). app/core/datasets keeps its own lowercase codes
(datasets/report.py): a separate namespace on purpose.
"""
from __future__ import annotations

TIERS = ("problem", "warning", "machine")

#: code -> (tier, one-line meaning); append-only
CODES: dict[str, tuple[str, str]] = {
    # Sandbox Check (app/core/sandbox_check.py check(); its texts)
    "NO_SUFFIX": ("problem", "the simulate action names no suffix"),
    "NO_GENERATE_NETWORK": ("problem",
                            "the actions never call generate_network"),
    "EXP_UNREADABLE": ("problem", "data.exp cannot be read: dates, the "
                       "header, a row's width, no rows, or a value that is "
                       "not a number"),
    "EXP_TIME_ORDER": ("problem", "data.exp's times do not increase"),
    "PRIORS_LINE": ("problem", "a priors.conf line has no '='"),
    "KEY_RESERVED": ("problem",
                     "priors.conf sets a key the run settings write"),
    "NO_FREE_PARAMETER": ("problem", "priors.conf has no *_var line"),
    "PRIOR_MALFORMED": ("problem", "a prior lacks a name and two numbers, "
                        "or they are not numbers"),
    "PRIOR_UNDEFINED": ("problem", "a prior names a parameter the "
                        "parameters block does not define"),
    "PRIOR_BOUNDS": ("problem", "a prior's low end is not below its high "
                     "end, a loguniform low end is at or below 0, or a "
                     "spread is at or below 0"),
    "PRIOR_RENAMED": ("problem", "one name in priors.conf, another in "
                      "model.bngl"),
    "FREE_NO_PRIOR": ("problem", "a __FREE parameter has no prior"),
    "PRIOR_NOT_FREE": ("problem", "a prior on a parameter whose name does "
                       "not end in __FREE"),
    "CUMULATIVE_NOT_OUTPUT": ("problem", "pf_cumulative_observable names no "
                              "observable or function"),
    "NETWORK_FAILS": ("problem", "BNG2.pl cannot generate the network, or "
                      "it timed out"),
    "CHECK_FAILED": ("problem", "the check itself failed"),
    "FREE_LOWERCASE": ("warning", "__free in small letters is not fitted"),
    "START_OUTSIDE_PRIOR": ("warning", "a written value lies outside its "
                            "range prior"),
    "NO_CUMULATIVE": ("warning", "no pf_cumulative_observable line (the "
                      "Sandbox only)"),
    "ROW_BEFORE_START": ("warning",
                         "a data row at or before pf_start_time"),
    "KEY_RETIRED": ("warning", "pf_observable_mode is retired"),
    "KEY_UNKNOWN": ("warning",
                    "a pf_ key the installed engine does not know"),
    "ONE_ROW": ("warning", "one data row on an engine that needs two"),
    "SCALE_OFF": ("warning", "the model at its written values is tenfold "
                  "off the data"),
    "MACHINE": ("machine", "this computer cannot check or fit yet; the "
                "text says why"),
    # ready for replays (library.validate)
    "FILE_UNREADABLE": ("problem", "a file is missing or not UTF-8 text"),
    "NO_MODEL_BLOCK": ("problem", "no begin model ... end model"),
    "OUTSIDE_MODEL": ("problem", "a statement outside every block before "
                      "end model"),
    "BLOCK_NOT_ALLOWED": ("problem", "a block inside the model that is not "
                          "a model block"),
    "TOKEN_MALFORMED": ("problem", "stray double braces in model.bngl, or "
                        "any in priors.conf"),
    "TOKEN_UNKNOWN": ("problem",
                      "a token FluBNF does not fill for this model"),
    "NO_STATE_TOKENS": ("problem", "neither {{POP}} nor {{I0FRAC}}: every "
                        "location would run one location's values"),
    "NO_H_WEEKLY": ("problem", "no output named H_weekly"),
    "NO_DISPERSION": ("problem", "model.bngl defines no r__FREE"),
    "KEY_NOT_ALLOWED": ("problem", "a priors.conf key other than the prior "
                        "kinds and pf_cumulative_observable"),
    "CUMULATIVE_REQUIRED": ("problem", "no pf_cumulative_observable line"),
    "ACTIONS_DROPPED": ("warning", "the model's actions do more than "
                        "generate and simulate; a replay runs FluBNF's"),
    "GAMMA_ASSUMED": ("warning", "the model lacks {{GAMMA}}, yet FluBNF "
                      "assumes 7/3.2 per week: in the i0 pin when it uses "
                      "{{I0FRAC}}, and in the Oracle step when that is on"),
    # the library (library.register, resolve)
    "NAME_INVALID": ("problem", "not a model name, or the same as another "
                     "library name ignoring case"),
    "NAME_RESERVED": ("problem", "a shipped model's name"),
    "MODEL_REF": ("problem", "not name@version, a bare name that is not "
                  "shipped, or a version on a shipped name"),
    "MODEL_NOT_FOUND": ("problem", "no such model name or version"),
    "MODEL_CHANGED": ("problem", "a version's files, or its model.json, no "
                      "longer match as registered"),
    "FORMAT_UNKNOWN": ("problem", "a record's format_version is not 1"),
    # experiments (experiments.read, plan)
    "EXPERIMENT_UNREADABLE": ("problem", "the experiment file is missing, "
                              "not JSON, or not an object"),
    "FIELD_UNKNOWN": ("problem", "a key other than model, season, size and "
                      "oracle"),
    "FIELD_MISSING": ("problem", "model or season absent"),
    "FIELD_TYPE": ("problem", "a value of the wrong type"),
    "SIZE_UNKNOWN": ("problem", "a size other than smoke, pilot or full"),
    "SEASON_NO_WEEKS": ("problem", "not an available season here, or the "
                        "size's rule picks no week"),
    "EXPERIMENT_CHANGED": ("problem", "the folder's run record holds "
                           "another experiment fingerprint"),
    "NO_REFERENCE": ("warning", "no shipped replay here on the shipped "
                     "settings holding the needed member; the summary has "
                     "no shipped side"),
    # ready for replays, since the engine runs a registered model
    # (library._tokens_rules, library._structure)
    "SUFFIX_IN_MODEL": ("problem", "model.bngl names a suffix (suffix=>) "
                        "before end model"),
    "LINE_BREAK_NOT_ALLOWED": ("problem", "a line break other than a "
                               "newline up to end model: PyBNF reads a "
                               "line there and BNG2.pl does not"),
    # the Sandbox's placeholder fill (sandbox_data.filled_bngl)
    "PLACEHOLDERS_UNFILLED": ("problem", "model.bngl keeps a placeholder "
                              "the Sandbox cannot fill from data.exp: no "
                              "location or population, rates, no "
                              "admissions, or one it does not fill"),
}


def finding(code: str, text: str, *, file: str | None = None,
            line: int | None = None) -> dict:
    """One finding, its tier read from CODES; ValueError on a code CODES
    does not hold."""
    if code not in CODES:
        raise ValueError(f"{code!r} is not a problem code")
    out = {"code": code, "tier": CODES[code][0], "text": str(text)}
    if file is not None:
        out["file"] = str(file)
    if line is not None:
        out["line"] = int(line)
    return out


class Refusal(ValueError):
    """What the library or an experiment refuses: .findings (each one, the
    warnings too), .code (the first problem's code) and, as str(), the
    problems' texts one per line, the first problem first."""

    def __init__(self, findings):
        found = [findings] if isinstance(findings, dict) else list(findings)
        problems = [f for f in found if f["tier"] == "problem"] or found
        super().__init__("\n".join(f["text"] for f in problems))
        self.findings = found
        self.code = problems[0]["code"] if problems else ""
