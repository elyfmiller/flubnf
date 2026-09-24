"""PRODUCTION: run ledger, workroot leasing, seeds and run-display helpers
(server, engines, retro).

Run ledger, workroot leasing, seed derivation, and run display helpers.

The lab's constitutional rules as code (the lab archive's docs/APP_DESIGN.md):

  rule 1  every run gets a fresh, exclusive workroot        -> lease_workroot()
  rule 2  every conf carries an explicit derived seed        -> derive_seed()
  rule 3  per-state numbers ship as >=3 seeded replicates    -> RunSpec.replicates
  ledger  every run reproducible from its row                -> Ledger

None is advisory: the engines refuse to run outside a leased workroot.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

APP_STATE = Path(__file__).resolve().parents[1] / "state"


def fmt_hms(seconds) -> str:
    """Wall time as h:mm:ss, the one formatter every surface shares; None,
    NaN or negative -> '--' (never a fake zero)."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "--"
    if s < 0 or s != s:                     # negative or NaN: no fake zero
        return "--"
    s = int(round(s))
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


#: location lists up to this long are named in full; longer ones are counted
LOCATION_LIST_LIMIT = 8

#: the FluSight jurisdiction count (50 states, DC, Puerto Rico)
ALL_JURISDICTIONS = 52

ENGINE_LABELS = {"all": "both models (Oracle SIHRS and Groundhog)",
                 "pf": "Oracle SIHRS only",
                 "analogue": "Groundhog only",
                 "amcmc": "adaptive MCMC",
                 "retro": "particle filter (retrospective)"}


def _is_national(loc) -> bool:
    """Local alias of us_national.is_us (lazy import breaks a cycle)."""
    from app.core.us_national import is_us
    return is_us(loc)


def locations_phrase(locations) -> str:
    """A run's location scope for a person: the count, plus names when the
    list is short. US national is reported apart from the state count."""
    locs = [str(l) for l in (locations or [])]
    states = [l for l in locs if not _is_national(l)]
    tail = " plus US national" if len(states) != len(locs) else ""
    if not states:
        return ("US national only" if tail else "none")
    if len(states) >= ALL_JURISDICTIONS:
        return f"all {len(states)} jurisdictions{tail}"
    noun = "state" if len(states) == 1 else "states"
    if len(states) <= LOCATION_LIST_LIMIT:
        return f"{len(states)} {noun}{tail}: " + ", ".join(states)
    return f"{len(states)} {noun}{tail}"


def spec_settings(spec) -> list:
    """The settings that produced a console run, as (label, value) pairs.

    One formatter for the progress card, the run page and the weekly report.
    `spec` may be a RunSpec, the ledger's dict, or its JSON text; an
    unreadable spec yields [] rather than raising.
    """
    if isinstance(spec, RunSpec):
        d = asdict(spec)
    elif isinstance(spec, str):
        try:
            d = json.loads(spec or "{}")
        except (ValueError, TypeError):
            return []
    elif isinstance(spec, dict):
        d = spec
    else:
        return []
    if not isinstance(d, dict) or not d:
        return []
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    if extra.get("dataset"):
        return dataset_settings(d)
    engine = str(d.get("engine", "") or "")
    pairs = [("forecast date", str(d.get("forecast_date", "") or "unknown")),
             ("locations", locations_phrase(d.get("locations"))),
             ("engine", ENGINE_LABELS.get(engine, engine or "unknown")),
             ("replicates", str(d.get("replicates", "") or "")),
             ("particles", f"{int(d.get('particles') or 0):,}")]
    # season start beside the date: it fixes the first observed week and anchor
    if d.get("season_start"):
        pairs.insert(1, ("season start", str(d["season_start"])))
    pairs.append(("weeks dropped", str(int(d.get("weeks_to_drop") or 0))))
    # only when the spec records the choice (older rows would be misdescribed)
    if "drop_same_day" in d:
        pairs.append(("same-day week",
                      "treated as unreported"
                      if d.get("drop_same_day") else "kept"))
    if int(extra.get("members") or 2) == 3:
        pairs.append(("research member", "two-strain SIHRS"))
    # older rows carry no aux key and ran the bare analogue, which this then says
    pairs.append(("Groundhog donors", analogue_donors_label(extra)))
    pairs.append(("Oracle step", oracle_label(extra)))
    # only a spec with a knobs record: shipped and older rows are unchanged
    mk = model_settings_label(d)
    if mk:
        pairs.append(("model settings", mk))
    return [(k, v) for k, v in pairs if v not in ("", None)]


#: a dataset run's members, as its settings name them
DATASET_ENGINE_LABELS = {
    "all": "Groundhog and SIHRS particle filter (plain)",
    "pf": "SIHRS particle filter (plain) only",
    "analogue": "Groundhog only"}


def groups_phrase(locations) -> str:
    """A dataset run's scope: the group count, names when short."""
    locs = [str(l) for l in (locations or [])]
    if not locs:
        return "none"
    noun = "group" if len(locs) == 1 else "groups"
    if len(locs) <= LOCATION_LIST_LIMIT:
        return f"{len(locs)} {noun}: " + ", ".join(locs)
    return f"{len(locs)} {noun}"


def dataset_settings(d: dict) -> list:
    """spec_settings for a run on a custom dataset (extra['dataset']): the
    data source and groups, the members as they ran on it (no Oracle step,
    the Groundhog's donors), and the PF's size only when the PF ran."""
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    ref = extra.get("dataset") or {}
    engine = str(d.get("engine", "") or "")
    truth = ("final data, not vintage-true"
             if extra.get("dataset_final") else "vintage-true (as_of snapshots)")
    pairs = [("forecast date", str(d.get("forecast_date", "") or "unknown")),
             ("data source", f"{ref.get('name', '?')} (your dataset; {truth})"),
             ("groups", groups_phrase(d.get("locations"))),
             ("models", DATASET_ENGINE_LABELS.get(engine, engine or "unknown"))]
    if engine in ("all", "pf"):
        if d.get("season_start"):
            pairs.append(("season start", str(d["season_start"])))
        pairs += [("replicates", str(d.get("replicates", "") or "")),
                  ("particles", f"{int(d.get('particles') or 0):,}"),
                  ("Oracle step", "off (its donor bank is FluSight-specific)")]
    pairs.append(("weeks dropped", str(int(d.get("weeks_to_drop") or 0))))
    if "drop_same_day" in d:
        pairs.append(("same-day week", "treated as unreported"
                      if d.get("drop_same_day") else "kept"))
    if engine in ("all", "analogue"):
        from app.core.custom_run import analogue_label
        pairs.append(("Groundhog donors", analogue_label(extra)))
    mk = model_settings_label(d)
    if mk:
        pairs.append(("model settings", mk.split(";", 1)[0]))
    pairs.append(("output", "export files under non-hub names; never "
                            "submitted"))
    return [(k, v) for k, v in pairs if v not in ("", None)]


def model_settings_label(spec) -> str:
    """'' for a shipped (or pre-registry) spec; else the knobs label, e.g.
    'modified: oracle.w=0.25 (1a2b3c4d)', plus how its files were named.
    Lazy import: app.core.knobs imports this module."""
    from app.core import knobs as K
    rec = K.record_of(spec)
    if not rec:
        return ""
    why = K.override_reason(spec)
    try:
        text = K.label(K.from_record(rec))
    except Exception:
        text = "modified (unreadable record)"
    return (f"{text}; exported under the hub names by override: {why}" if why
            else f"{text}; files carry the non-hub name "
                 f"(<hub id>{K.MODIFIED_SUFFIX})")


def is_modified(spec) -> bool:
    """A run built with model settings off the shipped ones (a knobs
    record in its spec); never true for an older row."""
    from app.core import knobs as K
    return K.modified(spec)


def is_contained(spec) -> bool:
    """Kept off the shipped-product surfaces (Home, Forecast fans, Output,
    the forecast archive, the public site): a research run, or a modified
    run whose files carry the non-hub name. An override puts it back."""
    from app.core import knobs as K
    return is_research(spec) or not K.hub_names(spec)


def oracle_label(extra: dict | None) -> str:
    """One phrase for the Oracle step from a spec's extra: the plain filter
    for `oracle = none`, else the console default (worded as a default: the
    bank is known only at run time and is named in the OUTCOME, and older
    specs carry no key)."""
    extra = extra if isinstance(extra, dict) else {}
    if str(extra.get("oracle") or "") == "none":
        return "none (the plain filter, a research run)"
    return "on (console default)"


def analogue_donors_label(extra: dict | None) -> str:
    """One phrase for which donors the analogue engine ran with, from a
    spec's research dictionary: the preset and bank digests that
    _run_extra recorded ('flusurv+flusurv@06eff6a7'), or the bare
    analogue when the spec carries no auxiliary pools."""
    extra = extra if isinstance(extra, dict) else {}
    if extra.get("aux_pools"):
        return str(extra.get("analogue_aux") or "auxiliary bank (unnamed)")
    return "none (bare analogue)"


def is_research(spec) -> bool:
    """True when a run's spec is a research configuration: the two-strain
    member (members == 3 or variant 2strain; it failed its gate) or the
    plain filter. Derived from the ledger spec, so every surface agrees.
    Accepts spec_settings' three shapes; unreadable is not research."""
    if isinstance(spec, RunSpec):
        d = asdict(spec)
    elif isinstance(spec, str):
        try:
            d = json.loads(spec or "{}")
        except (ValueError, TypeError):
            return False
    elif isinstance(spec, dict):
        d = spec
    else:
        return False
    extra = d.get("extra") if isinstance(d, dict) else None
    if not isinstance(extra, dict):
        return False
    # the plain filter: file withheld, never the date's forecast; a custom
    # dataset: never the date's forecast either
    return (extra.get("members") == 3 or extra.get("variant") == "2strain"
            or str(extra.get("oracle") or "") == "none"
            or bool(extra.get("dataset")))


def version_pairs(build: str = "", versions: dict | None = None) -> list:
    """The app build and engine versions behind an artifact; omitted when unknown."""
    v = versions or {}
    pairs = []
    if build:
        pairs.append(("app build", str(build)))
    for key, label in (("pybnf", "pybnf"), ("bngsim", "bngsim"),
                       ("bionetgen", "BioNetGen")):
        if v.get(key):
            pairs.append((label, str(v[key])))
    return pairs


#: what the form's two modes are called on a ledger row
MODE_LABELS = {"realtime": "real-time (newest week)",
               "vintage": "vintage (archived week)"}

#: (label, relWIS key, cells key) per scored model, in table order. Older
#: ledger rows may also carry the retired blend's keys; they are not shown.
_RESULT_ROWS = (("Oracle SIHRS", "pf_relwis", "pf_relwis_cells"),
                ("Groundhog", "analogue_relwis", "analogue_relwis_cells"))


def results_html(outcome, spec) -> str:
    """One run's results as a small table: run type, each member's relWIS
    with its cells, PF fits and failures, submissions, report. Markup from
    fixed phrases and numbers only; unreadable input yields ""."""
    if isinstance(outcome, str):
        try:
            o = json.loads(outcome or "{}")
        except (ValueError, TypeError):
            o = {}
    else:
        o = outcome if isinstance(outcome, dict) else {}
    if isinstance(spec, RunSpec):
        d = asdict(spec)
    elif isinstance(spec, str):
        try:
            d = json.loads(spec or "{}")
        except (ValueError, TypeError):
            d = {}
    else:
        d = spec if isinstance(spec, dict) else {}
    if not o and not d:
        return ""
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    if extra.get("dataset"):
        return dataset_results_html(o, d)
    mode = str(extra.get("mode") or "realtime")
    rows = [("Run type", MODE_LABELS.get(mode, mode))]
    for name, key, cells_key in _RESULT_ROWS:
        v = o.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        n = o.get(cells_key)
        cov = (f' <span class="hint">({int(n)} cell{"s" if int(n) != 1 else ""})</span>'
               if n else "")
        rows.append((name, f'<span class="relwis {"ok" if fv < 1 else "bad"}">'
                           f"{fv:.3f}</span>{cov}"))
    if "pf_cells" in o:
        nf = len(o.get("pf_failures") or {})
        fits = f"{int(o['pf_cells'])} fit{'s' if int(o['pf_cells']) != 1 else ''}"
        if nf:
            fits += f', <span class="bad">{nf} failure{"s" if nf != 1 else ""}</span>'
        rows.append(("PF fits", fits))
    elif o.get("pf_skipped"):
        rows.append(("PF fits", "none (analogue-only run)" if "analogue" in str(o["pf_skipped"]) else "none (no engine)"))
    elif o.get("pf_engine_broken"):
        # installed but broken (a different remedy from "no engine"); the
        # message carries a path, so it is escaped
        import html as _html
        rows.append(("PF fits", '<span class="bad">none (engine install '
                                'incomplete)</span> <span class="hint">'
                                f'{_html.escape(str(o["pf_engine_broken"]))}'
                                '</span>'))
    if o.get("submission_withheld"):
        rows.append(("Submission", f'<span class="bad">withheld</span> '
                     f'<span class="hint">{o["submission_withheld"]}</span>'))
    if o.get("submission_errors"):
        n = len(o["submission_errors"])
        rows.append(("Submission errors", f'<span class="bad">{n}</span> '
                     '<span class="hint">on the run page</span>'))
    if o.get("submissions"):
        n = len(o["submissions"])
        rows.append(("Submission files", f"{n} file{'s' if n != 1 else ''}"))
    rows.append(("Weekly report", "written" if o.get("report") else "none"))
    body = "".join(f"<tr><th scope=\"row\">{k}</th><td>{v}</td></tr>" for k, v in rows)
    return (f'<table class="results"><caption class="hint">relWIS vs the '
            f'FluSight baseline, pooled over fitted states (US excluded); '
            f'below 1.000 beats it.</caption>'
            f"{body}</table>")


def dataset_results_html(o: dict, d: dict) -> str:
    """results_html for a run on a custom dataset: each member's relWIS
    against the in-house persistence baseline (named), the national group
    beside the pooled figure, abstentions and the export files. Fixed
    phrases and numbers only, group names escaped."""
    import html as _html
    from app.core.custom_run import BASELINE, EXPORT_IDS, MEMBER_LABELS
    rows = []
    scores = o.get("custom_scores") or {}
    for m in ("pf", "analogue"):
        sc = scores.get(m)
        if not sc or sc.get("relwis") is None:
            continue
        fv = float(sc["relwis"])
        n = int(sc.get("cells") or 0)
        cell = (f'<span class="relwis {"ok" if fv < 1 else "bad"}">{fv:.3f}'
                f'</span> <span class="hint">({n} cell{"s" if n != 1 else ""})'
                '</span>')
        nat = sc.get("national") or {}
        if nat.get("relwis") is not None:
            cell += (f' <span class="hint">· national group '
                     f'{float(nat["relwis"]):.3f}, beside</span>')
        rows.append((MEMBER_LABELS[m], cell))
    if "pf_cells" in o:
        nf = len(o.get("pf_failures") or {})
        fits = f"{int(o['pf_cells'])} fit{'s' if int(o['pf_cells']) != 1 else ''}"
        if nf:
            fits += f', <span class="bad">{nf} failure{"s" if nf != 1 else ""}</span>'
        rows.append(("PF fits", fits))
    elif o.get("pf_skipped"):
        rows.append(("PF fits", "none (" + _html.escape(str(o["pf_skipped"]))
                     + ")"))
    for m, names in sorted((o.get("abstained") or {}).items()):
        rows.append((f"{MEMBER_LABELS.get(m, m)} abstained",
                     _html.escape(", ".join(names[:8]))
                     + (" …" if len(names) > 8 else "")))
    ex = o.get("exports") or {}
    rows.append(("Export files", f"{len(ex)} file{'s' if len(ex) != 1 else ''}"
                 if ex else "none"))
    if o.get("export_errors"):
        rows.append(("Export errors", f'<span class="bad">'
                     f'{len(o["export_errors"])}</span>'))
    body = "".join(f"<tr><th scope=\"row\">{k}</th><td>{v}</td></tr>"
                   for k, v in rows)
    return (f'<table class="results"><caption class="hint">relWIS vs the '
            f'{BASELINE}, pooled over the groups (national group '
            f'excluded); below 1.000 beats it.</caption>{body}</table>')


def settings_html(pairs, title: str = "Run settings",
                  cls: str = "hint runsettings", el_id: str = "") -> str:
    """The one rendering of a settings block (every surface uses it): a
    two-column dl.kv grid inside the runsettings wrapper. The title is a
    literal callers key on (report_season.SETTINGS_MARK). Everything is
    escaped (values include user-supplied location names).
    """
    import html as _html
    items = [(k, v) for k, v in (pairs or []) if v not in ("", None)]
    if not items:
        return ""
    body = "".join(f"<dt>{_html.escape(str(k))}</dt>"
                   f"<dd>{_html.escape(str(v))}</dd>" for k, v in items)
    ident = f' id="{_html.escape(el_id)}"' if el_id else ""
    base = _html.escape(cls)
    wrap = f"{base} runsettings" if "runsettings" not in cls else base
    return (f'<div class="{wrap}"{ident}>'
            f'<strong>{_html.escape(title)}</strong>'
            f'<dl class="kv">{body}</dl></div>')


def run_id_time(run_id: str) -> str:
    """The local time a workroot id carries ('20260821T163029-5dbec2' ->
    '2026-08-21 16:30', minted in open_run); '' when it has none."""
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})\d{2}", run_id or "")
    if not m:
        return ""
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d} {h}:{mi}"


def run_display(run_id: str, spec=None, created_utc=None) -> dict:
    """How one run reads to a person, from its ledger row and id:

      what      'Forecast for <date>' / 'Retrospective fit <date>' /
                'Unrecorded run';
      when      the ledger's created_utc, else the id's timestamp;
      scope     locations_phrase, '' when unrecorded;
      recorded  whether a ledger row stood behind the label.

    Accepts spec_settings' three shapes; never raises (orphaned workroots
    must still render)."""
    if isinstance(spec, RunSpec):
        d = asdict(spec)
    elif isinstance(spec, str):
        try:
            d = json.loads(spec or "")
        except (ValueError, TypeError):
            d = None
    elif isinstance(spec, dict):
        d = spec
    else:
        d = None
    when = ""
    if created_utc:
        try:
            when = time.strftime("%Y-%m-%d %H:%M",
                                 time.localtime(float(created_utc)))
        except (TypeError, ValueError, OSError):
            when = ""
    when = when or run_id_time(run_id)
    if not isinstance(d, dict) or not d:
        return {"what": "Unrecorded run", "when": when, "scope": "",
                "recorded": False}
    kind = ("Retrospective fit" if str(d.get("engine")) == "retro"
            else "Forecast for")
    date = str(d.get("forecast_date") or "").strip()
    return {"what": f"{kind} {date}" if date else kind.split()[0],
            "when": when,
            "scope": locations_phrase(d.get("locations")),
            "recorded": True}


def derive_seed(location: str, forecast_date: str, replicate: int) -> int:
    """Deterministic per-(location, date, replicate) seed.

    Unseeded draws moved relWIS 0.894 vs 0.946 on the same script; identical
    specs must reproduce bit-for-bit.
    """
    h = hashlib.sha256(f"{location}|{forecast_date}|{replicate}".encode()).digest()
    return int.from_bytes(h[:4], "little") % (2**31 - 1)


def default_season_start(forecast_date: str) -> str:
    """August 1 of the season a forecast date belongs to: the archive's
    season boundary and the basis of every sealed number. Empty in,
    empty out."""
    if not forecast_date:
        return ""
    y, m = int(forecast_date[:4]), int(forecast_date[5:7])
    return f"{y if m >= 8 else y - 1}-08-01"


@dataclass
class RunSpec:
    """Everything that defines one model run. The ledger stores this verbatim."""
    # (einn is retired: it emits no quantiles; see research/2026-08-21-nn-landscape.md)
    engine: str                      # 'pf' | 'analogue' | 'amcmc'
    forecast_date: str               # YYYY-MM-DD, a Saturday
    locations: list = field(default_factory=list)
    season_start: str = ""
    weeks_to_drop: int = 0           # trim newest N weeks before fitting
    weeks_to_nowcast: int = 0        # framework now, method later (no-op nowcaster)
    #: Treat the vintage's same-day week (archived hours into its reporting
    #: window: ~92% complete nationally, ~1% for some states) as unreported;
    #: the engines drop that row per state, labels stay as-of-relative.
    #: DEFAULT OFF: enabling it degraded 2023-24 pooled relWIS 0.813 -> 1.055
    #: (the row carries the turn signal). Recorded per run; a ~1%-reported
    #: anchor gets a loud warning instead.
    drop_same_day: bool = False
    replicates: int = 3
    particles: int = 10_000          # sit-down verdict 2026-08-17
    #: Liu-West kernel scale: 0.15 per the regularizer sweep (the seal ran 0.30
    #: on the sealed fork's raw-space kernel; reproducing it needs 0.30 explicitly)
    jitter: float = 0.15
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        # a blank season_start derives from the date (Aug-Jul); a typed one
        # is kept verbatim so the ledger records what actually ran
        if not self.season_start and self.forecast_date:
            self.season_start = default_season_start(self.forecast_date)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def _git_sha(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


class Ledger:
    """Append-only sqlite record: spec, seeds, engine versions, git SHAs,
    workroot, outcome. Reproducing any submission = re-executing its row."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else APP_STATE / "ledger.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("""CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, created_utc REAL, spec_json TEXT,
            flubnf_sha TEXT, pybnf_sha TEXT, engine_versions TEXT,
            workroot TEXT, status TEXT, outcome_json TEXT)""")
        # wall-time columns, added by migration (old rows report none)
        have = {r[1] for r in self._db.execute("PRAGMA table_info(runs)")}
        for col in ("finished_utc", "elapsed_s"):
            if col not in have:
                # concurrent Ledgers race the migration; duplicate column = applied
                try:
                    self._db.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
        self._db.commit()

    def open_run(self, spec: RunSpec, workroot: Path,
                 engine_versions: dict) -> str:
        run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        root = Path(__file__).resolve().parents[2]
        # named columns, never positional: the table grows by migration
        self._db.execute(
            "INSERT INTO runs (run_id, created_utc, spec_json, flubnf_sha, "
            "pybnf_sha, engine_versions, workroot, status, outcome_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, time.time(), spec.to_json(), _git_sha(root),
             _git_sha(__import__("flubnf.settings", fromlist=["PYBNF"]).PYBNF),
             json.dumps(engine_versions), str(workroot), "running", "{}"))
        self._db.commit()
        return run_id

    def set_workroot(self, run_id: str, workroot: Path) -> None:
        """Replace the open-time placeholder with the leased workroot."""
        self._db.execute("UPDATE runs SET workroot=? WHERE run_id=?",
                         (str(workroot), run_id))
        self._db.commit()

    def close_run(self, run_id: str, status: str, outcome: dict) -> None:
        """Record the outcome and wall time (elapsed_s derived in SQL from
        the row's own created_utc)."""
        now = time.time()
        self._db.execute(
            "UPDATE runs SET status=?, outcome_json=?, finished_utc=?, "
            "elapsed_s=MAX(0, ? - created_utc) WHERE run_id=?",
            (status, json.dumps(outcome), now, now, run_id))
        self._db.commit()

    def rows(self, limit: int = 50) -> list:
        # sha and engine versions: the run page names what produced the run
        cur = self._db.execute(
            "SELECT run_id, created_utc, spec_json, status, outcome_json, "
            "finished_utc, elapsed_s, flubnf_sha, engine_versions "
            "FROM runs ORDER BY created_utc DESC LIMIT ?", (limit,))
        return [dict(zip(("run_id", "created_utc", "spec", "status", "outcome",
                          "finished_utc", "elapsed_s", "flubnf_sha",
                          "engine_versions"), r))
                for r in cur.fetchall()]

    def delete_runs(self, run_ids) -> int:
        """Permanently remove the named rows; returns the count. Callers must
        never pass an active run, and must tell the user only the ledger
        entry goes (the workroot stays until the storage panel deletes it)."""
        ids = [str(r) for r in (run_ids or []) if r]
        if not ids:
            return 0
        marks = ",".join("?" for _ in ids)
        cur = self._db.execute(
            f"DELETE FROM runs WHERE run_id IN ({marks})", ids)
        self._db.commit()
        return cur.rowcount


def lease_workroot(run_id: str, base: Optional[Path] = None) -> Path:
    """Fresh, exclusive directory for ONE run. Never reused, never shared.

    mkdir(exist_ok=False): a collision is an ERROR, never a silent overlap.
    """
    root = (base or APP_STATE / "workroots") / run_id
    root.mkdir(parents=True, exist_ok=False)
    return root


