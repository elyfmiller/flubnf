"""The Oracle SIHRS member: the filter's stored forward samples with their
growth replaced by a blend of the filter's own origin growth and one
calendar-matched donor growth path from past seasons.

THE MEMBER (pre-registration PREREG_oracle_member_FROZEN.md, sha256
PREREG_SHA256 below; sections 4.1, 4.2, 4.3 LB, 10.3, addendum A1)
--------------------------------------------------------------------
For one cell (location L, as-of Saturday T) the stored particle-filter
samples are x_ih, i over the sample paths, h = 1..4 the PHYSICAL forecast
weeks; block "0" is the anchored origin. The cell quantities, from the
filter's own output alone:

    m_0   = median of the finite entries of block "0"
    m_h   = the 0.5 entry of the finite-only quantile vector of block h
    lam_T = ln(m_1 / m_0)          the filter's own first-week growth
    G_T   = gamma + lam_T           the filter's own G at the origin instant
    o_h   = ln(m_h / m_0)           the filter's own cumulated log path

A cell is eligible when m_0 > 0, m_1..m_4 > 0 and G_T > 0 (no guard on the
size of lam_T, S3). A date is active when the week's donor pool is
admissible under the identity rule (flubnf.oracle_bank). On every cell that
is not active the member is the identity: the filter's samples untouched.

Each stored sample path i draws one donor path d_i from the pool (one
uniform u_i per sample path, d_i = floor(u_i n)), and its four segment
levels are the GEOMETRIC blend, in G, of the filter's origin G and the
donor's midpoint stamps:

    ln G_k = w ln G_T + (1 - w) ln Ghat_d(W + k - 0.5),   k = 1..4,

w = 0.5 fixed a priori (W_PRODUCTION); w = 0.25 is the registered
secondary (A1 (2)), logged beside the primary and shipping nothing. The
closed form of 4.2 under reading F (the filter's own state at T, its own
half week inside the last observed week) gives the cumulated log median
path

    P_h(d) = lam_T - ln phi(lam_T) + sum_{i<h} lam_i(d) + ln phi(lam_h(d)),
    lam_k = G_k - gamma,   phi(x) = (exp(x) - 1) / x,   phi(0) = 1,

and the REPLACE factor F_h(d) = exp(P_h(d) - o_h). The member's samples are
x'_ih = x_ih * F_h(d_i): the stored spread rides on the new median path and
the donor draw adds the donors' spread of level on top. Check: G_k = G_T
for all k gives P_h = h lam_T and F = 1.

A drawn path with a non-positive midpoint stamp is an abstention: F = 1
for that (cell, sample), counted (0 on the registered pool). Non-finite
samples stay non-finite through the transform and are dropped before every
quantile, the console's rule.

THE DONOR INDEX (S14, the producer's draw). One uniform per stored sample
path from numpy.random.default_rng([seed, season index, T.toordinal(),
int(FIPS)]) with the season index flubnf.analogue.season_of(T) - 2023
(0 / 1 / 2 for 2023-24 / 2024-25 / 2025-26); the same uniforms serve every
horizon and every weight, so the primary and the secondary are paired.
Five seeds, 2026091801 to 2026091805; the submitted quantiles come from
the first (the producer's choice C2), the other four are logged for the
season-end reading.

THE SHIPPED BANK (bank change B2, addendum A2). The member ships on the
mixture bank of flubnf.oracle_mix: the admissions pool above plus a
FluSurv-NET path pool, the Groundhog's own donor bank. With `aux_pool` the
draw takes a SECOND uniform v_i from the same generator: v_i < w_aux (0.5
when both halves are admissible) draws the FluSurv-NET path
floor((v_i / w_aux) n_aux), and every other sample keeps its admissions
donor floor(u_i n_adm) exactly as the admissions-only member draws it, so
that member is recovered bitwise at w_aux = 0. A week with only one
admissible half draws from it alone (w_aux 1 or 0); a week with neither is
the identity (R_EITHER, S-B2-3).

HORIZONS. Everything here counts PHYSICAL weeks, 1 to 4, the library's
unit; the app translates at its own edge (app/core/oracle.py), and every
hub-facing row still goes through app.core.submit.quantile_rows. Nothing
in this module reads a vintage, a truth file or a hub.

Every numeric step is written as the registered screen's arms.py wrote it,
so the member quantiles are bitwise the screen's per seed where the stored
block holds the same finite values (tests/test_oracle.py pins that against
the record where the record is on the machine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from . import analogue as AN
from . import oracle_bank as OB
from .quantiles import FLUSIGHT_QUANTILES

#: The frozen pre-registration, version 2 with addendum A1 (2,490 lines),
#: recomputed at the wiring and equal to the value the producer refuses to
#: run without. Written into every week's provenance.
PREREG_SHA256 = "67c9fa49a195908312f34ca783b21d85377759309df14461f86fbfd54d30c56f"

#: Bank change B2 (b2/PREREG_b2_FROZEN.md, 1,008 lines): the mixture donor
#: bank of flubnf.oracle_mix, every blank at its printed recommendation.
B2_SHA256 = "2ce3564622296f490a435b773a3b34d431d889b3e0d4fe4b32ff6aeb8ede9249"
#: Addendum A2 to section 10.3 (PREREG_oracle_member_ADDENDUM_A2.md, a
#: separate file so PREREG_SHA256 does not move): the lead's decision of
#: 2026-09-23 to ship the member on the B2 bank (LBGH). All three hashes
#: go into every week's provenance.
ADDENDUM_A2_SHA256 = "85ac546416bbb20ed1b87ce9289f50645ff1e22169b0bed9ae0a054e3e449f27"

GAMMA = OB.GAMMA
H4 = 4

#: The weight, fixed a priori (section 3, "weight"): the only weight that
#: treats the two sources alike, and the lab never fits blend weights.
W_PRODUCTION = 0.5
#: The registered secondary (A1 (2)): logged beside the primary, ships nothing.
W_SECONDARY = 0.25

#: S14: the five donor-index seeds. The submitted quantiles are the first
#: seed's realisation (the producer's recorded choice C2); the screen
#: measured the seed noise at sd <= 7e-5 on every contrast.
SEEDS = (2026091801, 2026091802, 2026091803, 2026091804, 2026091805)
SUBMITTED_SEED = SEEDS[0]

#: The 23 FluSight levels, as a list (numpy.quantile takes the list).
QL = [float(q) for q in FLUSIGHT_QUANTILES]
QA = np.array(QL)


# ---------------------------------------------------------------------------
# the closed form (screen/arms.py, verbatim)
# ---------------------------------------------------------------------------

def lnphi(x):
    x = np.asarray(x, float)
    small = np.abs(x) < 1e-12
    xs = np.where(small, 1.0, x)
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        v = np.log(np.expm1(xs) / xs)
    return np.where(small, 0.0, v)


def closed_form_P(lam0, LAM):
    """lam0 (n,), LAM (n, 4) -> P (n, 4) of 4.2 (reading F when lam0 == lam_T)."""
    n = LAM.shape[0]
    P = np.empty((n, H4))
    base = lam0 - lnphi(lam0)
    cs = np.cumsum(LAM, axis=1)
    for h in range(H4):
        prev = cs[:, h - 1] if h > 0 else 0.0
        P[:, h] = base + prev + lnphi(LAM[:, h])
    return P


def factors(cell: dict, G, lam0=None):
    """G (n, 4) segment levels; lam0 (n,) or None (reading F). Returns
    (F (n, 4), valid (n,)) with F = 1 on invalid rows (abstention)."""
    G = np.atleast_2d(np.asarray(G, float))
    n = G.shape[0]
    valid = np.isfinite(G).all(axis=1) & (G > 0).all(axis=1)
    if lam0 is None:
        lam0 = np.full(n, cell['lam_T'])
    else:
        lam0 = np.asarray(lam0, float)
        valid &= np.isfinite(lam0) & (lam0 + GAMMA > 0)
    LAM = np.where(valid[:, None], G, GAMMA) - GAMMA
    lam0s = np.where(valid, lam0, cell['lam_T'])
    P = closed_form_P(lam0s, LAM)
    F = np.exp(P - cell['o'][None, :])
    F[~valid] = 1.0
    return F, valid


def blend(G_T: float, Gd, w: float):
    """The geometric blend in G: exp(w ln G_T + (1 - w) ln Ghat_d). A
    non-positive stamp gives nan here and an abstention in `factors`; the
    warning numpy would print for it is noise, not information."""
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.exp(w * np.log(G_T) + (1.0 - w) * np.log(Gd))


# ---------------------------------------------------------------------------
# the cell, the draw, the quantiles
# ---------------------------------------------------------------------------

def finite_quantiles(x) -> np.ndarray:
    """numpy.quantile (linear) of the finite values at the 23 levels, the
    rule of app.core.submit.quantile_rows and ensemble.member_quantiles;
    a nan vector when nothing is finite."""
    x = np.asarray(x, float)
    s = x[np.isfinite(x)]
    if not s.size:
        return np.full(len(QL), np.nan)
    return np.quantile(s, QL)


def cell_quantities(x0, xh: list) -> dict:
    """4.1 from one location's stored samples: x0 the origin block, xh the
    four forecast blocks in PHYSICAL order (weeks 1 to 4)."""
    x = [np.asarray(a, float) for a in xh]
    if len(x) != H4:
        raise ValueError(f"a cell needs {H4} forecast blocks, got {len(x)}")
    n_total = [int(len(a)) for a in x]
    n_finite = [int(np.isfinite(a).sum()) for a in x]
    x0 = np.asarray(x0, float)
    n0_total, n0_finite = int(len(x0)), int(np.isfinite(x0).sum())
    m0 = float(np.median(x0[np.isfinite(x0)])) if n0_finite else float('nan')
    q_null = np.array([finite_quantiles(a) for a in x])          # (4, 23)
    m = q_null[:, 11].copy()                                      # the 0.5 level
    eligible = bool(np.isfinite(m0) and m0 > 0 and np.isfinite(m).all() and (m > 0).all())
    lam_T = float(np.log(m[0] / m0)) if eligible else float('nan')
    G_T = GAMMA + lam_T if eligible else float('nan')
    eligible = eligible and G_T > 0
    return {'x': x, 'n_total': n_total, 'n_finite': n_finite,
            'n0_total': n0_total, 'n0_finite': n0_finite,
            'm0': m0, 'm': m, 'q_null': q_null, 'eligible': eligible,
            'lam_T': lam_T, 'G_T': G_T,
            'o': (np.log(m / m0) if eligible else np.full(H4, np.nan))}


def season_index(asof: date) -> int:
    """The season index in the RNG key: 0 / 1 / 2 for 2023-24 / 2024-25 /
    2025-26 (the screen's SC1), extended by the same rule."""
    return AN.season_of(asof) - 2023


def uniforms(seed: int, asof: date, fips: str, n: int) -> np.ndarray:
    """One uniform per stored sample path (S14, the producer's draw)."""
    rng = np.random.default_rng([int(seed), season_index(asof), asof.toordinal(), int(fips)])
    return rng.random(n)


def two_uniforms(seed: int, asof: date, fips: str, n: int) -> tuple:
    """(u, v): u is `uniforms` (the first call on the frozen generator,
    bitwise), v the second call on the same generator, the mixture's coin
    (b2 S-B2-2)."""
    rng = np.random.default_rng([int(seed), season_index(asof), asof.toordinal(), int(fips)])
    return rng.random(n), rng.random(n)


def donor_index(u: np.ndarray, n: int) -> tuple:
    """d_i = floor(u_i n), with min(d_i, n - 1) as a guard; returns
    (d, guard hits)."""
    d = (u * n).astype(int)
    g = int((d >= n).sum())
    if g:
        d = np.minimum(d, n - 1)
    return d, g


def member_levels(cell: dict, pool: dict, w: float):
    """The LB arm's segment levels for every path of an admissible pool:
    (n, 4), the geometric blend of the cell's G_T and the pool's midpoint
    stamps; None when the pool is not admissible (the identity)."""
    if pool['rule'] != 1 or pool['n'] == 0:
        return None
    return blend(cell['G_T'], pool['G_mid'], w)


def _admissible(pool) -> bool:
    return pool is not None and pool['rule'] == 1 and pool['n'] > 0


def mixture_rows(Fa, va, Fx, vx, u, v, w_aux: float, n_adm: int, n_aux: int) -> tuple:
    """The per-sample factor rows of the mixture (b2 S-B2-2, the screen's
    arms_b2.build_date): at 0 < w_aux < 1, v_i < w_aux draws the FluSurv-NET
    path floor((v_i / w_aux) n_aux) and every other sample keeps the
    admissions donor floor(u_i n_adm); at w_aux = 1 the index is
    floor(v_i n_aux); at w_aux = 0 it is floor(u_i n_adm), the
    admissions-only member. The guard min(d, n - 1) counts only the indices
    used. Returns (rows (n, 4), changed (n,) bool, abstentions, guard hits)."""
    n = len(u)
    if w_aux == 0.0:
        d, g = donor_index(u, n_adm)
        return Fa[d], np.zeros(n, bool), int((~va[d]).sum()), g
    if w_aux == 1.0:
        d, g = donor_index(v, n_aux)
        return Fx[d], np.ones(n, bool), int((~vx[d]).sum()), g
    sel = v < w_aux
    ix = ((v / w_aux) * n_aux).astype(int)
    ia = (u * n_adm).astype(int)
    g = int((ix[sel] >= n_aux).sum() + (ia[~sel] >= n_adm).sum())
    if g:
        ix = np.minimum(ix, n_aux - 1)
        ia = np.minimum(ia, n_adm - 1)
    rows = np.empty((n, H4))
    rows[~sel] = Fa[ia[~sel]]
    rows[sel] = Fx[ix[sel]]
    ab = int((~va[ia[~sel]]).sum() + (~vx[ix[sel]]).sum())
    return rows, sel, ab, g


@dataclass
class CellMember:
    """The member on one cell: eligibility, activity, the NULL and the
    per-seed quantiles, the submitted seed's transformed samples."""
    eligible: bool
    active: bool
    m0: float
    m: np.ndarray                    # (4,) the filter's medians
    lam_T: float
    G_T: float
    q_null: np.ndarray               # (4, 23)
    q_seed: dict                     # seed -> (4, 23) quantiles
    samples: list                    # the submitted seed's four transformed blocks
    abstentions: int = 0
    guard_hits: int = 0
    n_total: list = field(default_factory=list)
    n_finite: list = field(default_factory=list)
    n0_total: int = 0
    n0_finite: int = 0
    #: the week's FluSurv-NET probability this cell drew with (None: the
    #: identity; 0.0: the admissions half alone)
    w_aux: float | None = None
    #: samples of the submitted seed that drew a FluSurv-NET path
    n_aux_drawn: int = 0

    def q_mean(self) -> np.ndarray:
        return np.mean(np.stack([self.q_seed[s] for s in self.q_seed]), axis=0)


def member_for_cell(x0, xh: list, pool: dict, asof: date, fips: str, *,
                    w: float = W_PRODUCTION, seeds=SEEDS,
                    submitted_seed: int = SUBMITTED_SEED,
                    aux_pool: dict | None = None, w_aux="auto") -> CellMember:
    """The member on one cell: the transformed samples of `submitted_seed`
    and the 23 finite-only quantiles of every seed in `seeds`.

    `x0` is the origin block, `xh` the four forecast blocks in PHYSICAL
    order, `pool` the admissions half as flubnf.oracle_bank reads it (rule 1
    with G_mid (n, 4), or rule 0 for the identity), `fips` the
    two-character FIPS the RNG key uses.

    Without `aux_pool` this is the admissions-only member of the frozen
    document (LB), unchanged. With `aux_pool` (the FluSurv-NET half as
    flubnf.oracle_mix.shrunk_pool gives it: G_mid already shrunk) it is the
    shipped mixture member (LBGH, bank change B2): `w_aux` "auto" resolves
    the week's FluSurv-NET probability under R_EITHER
    (flubnf.oracle_mix.resolve_w_aux: 0.5 when both halves are admissible,
    1 or 0 when one is, the identity when neither is); a number or None
    sets it (None: the identity), for research controls.

    A cell that is not eligible, or a week with no admissible half, returns
    the identity: the NULL quantiles under every seed and the samples
    untouched, active False.
    """
    if aux_pool is None:
        wa = 0.0 if _admissible(pool) else None
    elif isinstance(w_aux, str):
        if w_aux != "auto":
            raise ValueError(f"w_aux must be 'auto', a number or None, got {w_aux!r}")
        from . import oracle_mix as MX
        wa = MX.resolve_w_aux(_admissible(pool), _admissible(aux_pool))
    else:
        wa = None if w_aux is None else float(w_aux)
        if wa is not None and not 0.0 <= wa <= 1.0:
            raise ValueError(f"w_aux must lie in [0, 1], got {wa}")
        if wa is not None and ((wa < 1.0 and not _admissible(pool))
                               or (wa > 0.0 and not _admissible(aux_pool))):
            raise ValueError(f"w_aux {wa} draws from a half that is not admissible")
    c = cell_quantities(x0, xh)
    x = c['x']
    null_q = c['q_null']
    seeds = tuple(int(s) for s in seeds)
    identity = CellMember(
        eligible=c['eligible'], active=False, m0=c['m0'], m=c['m'],
        lam_T=c['lam_T'], G_T=c['G_T'], q_null=null_q,
        q_seed={s: null_q.copy() for s in seeds}, samples=list(x),
        n_total=c['n_total'], n_finite=c['n_finite'],
        n0_total=c['n0_total'], n0_finite=c['n0_finite'], w_aux=None)
    if not c['eligible'] or wa is None:
        return identity
    cell = {'lam_T': c['lam_T'], 'G_T': c['G_T'], 'o': c['o']}
    Fa = va = Fx = vx = None
    if wa < 1.0:
        Fa, va = factors(cell, member_levels(c, pool, w))
        assert np.isfinite(Fa).all() and (Fa > 0).all(), (fips, asof)
    if wa > 0.0:
        Fx, vx = factors(cell, blend(c['G_T'], aux_pool['G_mid'], w))
        assert np.isfinite(Fx).all() and (Fx > 0).all(), (fips, asof)
    n_adm = pool['n'] if Fa is not None else 0
    n_aux = aux_pool['n'] if Fx is not None else 0
    lengths = {len(a) for a in x}
    if len(lengths) != 1:
        raise ValueError(f"{fips} {asof}: the four forecast blocks differ in "
                         f"length ({sorted(lengths)}); a torn record is not transformed")
    n_paths = len(x[0])
    q_seed, samples, absten, guard, n_drawn = {}, None, 0, 0, 0
    for s in seeds:
        if wa == 0.0:
            u, v = uniforms(s, asof, fips, n_paths), None
        else:
            u, v = two_uniforms(s, asof, fips, n_paths)
        rows, changed, ab, g = mixture_rows(Fa, va, Fx, vx, u, v, wa, n_adm, n_aux)
        guard += g
        absten += ab
        out = np.empty((H4, len(QL)))
        xs = []
        for hi in range(H4):
            xp = x[hi] * rows[:, hi]
            xs.append(xp)
            out[hi] = finite_quantiles(xp)
        q_seed[s] = out
        if s == submitted_seed:
            samples = xs
            n_drawn = int(changed.sum())
    if samples is None:
        raise ValueError(f"the submitted seed {submitted_seed} is not among the seeds run {seeds}")
    return CellMember(
        eligible=True, active=True, m0=c['m0'], m=c['m'],
        lam_T=c['lam_T'], G_T=c['G_T'], q_null=null_q, q_seed=q_seed,
        samples=samples, abstentions=absten, guard_hits=guard,
        n_total=c['n_total'], n_finite=c['n_finite'],
        n0_total=c['n0_total'], n0_finite=c['n0_finite'],
        w_aux=wa, n_aux_drawn=n_drawn)
