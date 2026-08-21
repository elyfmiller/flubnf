"""Token derivation for the two-age-class SIHRS candidate.

STANDALONE ON PURPOSE. Nothing under flubnf/ or app/ imports this, and this
imports nothing from them, so it can be reviewed and tested while the rest of
the tree is being edited. If the candidate graduates, fold `age2_tokens()`
into flubnf/sihrs_fit.py and delete this file.

Everything here is a pure function of FIXED constants -- no fitted parameter
reaches these values, which is what makes them tokens rather than parameters.
"""
from __future__ import annotations

import math

# Anchor for the seed split. Sits ABOVE the prior mean because the cost of a
# shared initial condition is asymmetric in theta: cheap below the anchor,
# expensive above it. See the template header for the measured table.
THETA_ANCHOR = 0.45

# Prior support for theta. The upper end is set by that same table: at 0.7 the
# worst-case early-growth bias is 4.4%, at 0.9 it is 18%.
THETA_PRIOR = (0.0, 0.7)


def ngm(theta: float, fk: float, qk: float, uk: float = 1.0):
    """Next-generation matrix summary for the two-class model.

    Returns (lam, ped_infection_share), where `lam` is the leading eigenvalue
    used to normalize beta0 and `ped_infection_share` is the paediatric entry
    of the dominant eigenvector, normalized to sum to 1.

    Mirrors the BNGL parameter block EXACTLY. If you change one, change both;
    a silent divergence here would misnormalize Reff without any error.
    """
    fa = 1.0 - fk
    ua = (1.0 - uk * fk) / fa
    Q = qk * fk + fa
    m11 = uk * ((1 - theta) * qk * qk * fk / Q + theta * qk)
    m12 = uk * (1 - theta) * qk * fk / Q
    m21 = ua * (1 - theta) * qk * fa / Q
    m22 = ua * ((1 - theta) * fa / Q + theta)
    disc = (m11 - m22) ** 2 + 4 * m12 * m21
    lam = ((m11 + m22) + math.sqrt(disc)) / 2
    vk, va = m12, lam - m11          # va >= 0 always, from the sqrt bound
    return lam, vk / (vk + va) if (vk + va) > 0 else 0.0


def split_rho(rho: float, ped_admission_share: float,
              ped_infection_share: float) -> tuple:
    """Split the state's pinned aggregate IHR into class-specific IHRs.

    The constraint that matters: at the anchor infection split, the model's
    admission share must equal the state's OBSERVED baseline paediatric
    admission share. Otherwise the binomial channel spends its weight
    arguing about the level -- which the triage showed carries no predictive
    information -- instead of the dynamics, which carry all of it.

    Solves, with pI the infection share and pA the target admission share:
        rhoK * pI / (rhoK * pI + rhoA * (1 - pI)) = pA
        rhoK * pI + rhoA * (1 - pI)               = rho   (aggregate preserved,
                                                           so rho*mult keeps its
                                                           pinned meaning)
    """
    pI, pA = float(ped_infection_share), float(ped_admission_share)
    if not 0 < pI < 1:
        raise ValueError("ped_infection_share must be strictly inside (0,1)")
    if not 0 < pA < 1:
        raise ValueError("ped_admission_share must be strictly inside (0,1)")
    rhoK = rho * pA / pI
    rhoA = rho * (1 - pA) / (1 - pI)
    return rhoK, rhoA


def age2_tokens(*, fk: float, qk: float, rho: float,
                ped_admission_share: float, uk: float = 1.0) -> dict:
    """Build the extra_tokens dict for materialize_model().

    fk   child (0-17) population fraction, census
    qk   child contact intensity relative to adults, sourced and FIXED
    rho  the state's pinned aggregate IHR (as the single-class model uses)
    ped_admission_share  observed baseline paediatric share of age-coded
         admissions for this state, from the season's first as-of reading
    uk   child relative susceptibility; HARD CONSTRAINT uk <= 1/s0
    """
    _, pI = ngm(THETA_ANCHOR, fk, qk, uk)
    rhoK, rhoA = split_rho(rho, ped_admission_share, pI)
    return {
        "{{FKID}}": f"{fk:.6f}",
        "{{QKID}}": f"{qk:.4f}",
        "{{UKID}}": f"{uk:.4f}",
        "{{RHOKID}}": f"{rhoK:.8g}",
        "{{RHOADULT}}": f"{rhoA:.8g}",
        "{{PEDI0}}": f"{pI:.6f}",
    }


def check_uk(uk: float, s0: float) -> None:
    """Fail loudly rather than let a negative R seed through silently."""
    if uk * s0 > 1.0:
        raise ValueError(
            f"uk={uk} with s0={s0} gives s0k={uk*s0:.4f} > 1: the child R "
            f"compartment seeds NEGATIVE. Ceiling is uk <= {1/s0:.4f}.")


if __name__ == "__main__":
    fk, qk, rho = 0.205, 2.0, 0.02
    tok = age2_tokens(fk=fk, qk=qk, rho=rho, ped_admission_share=0.12)
    lam, pI = ngm(THETA_ANCHOR, fk, qk)
    print(f"lam(anchor)={lam:.6f}  ped infection share={pI:.6f}")
    for k, v in tok.items():
        print(f"  {k:14} {v}")
    rhoK, rhoA = float(tok["{{RHOKID}}"]), float(tok["{{RHOADULT}}"])
    print(f"  check aggregate IHR: {rhoK*pI + rhoA*(1-pI):.6f} (target {rho})")
    print(f"  check admission share: {rhoK*pI/(rhoK*pI+rhoA*(1-pI)):.6f} (target 0.12)")
