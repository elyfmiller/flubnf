"""A library model run by the real engine (opt-in): the shipped SIHRS
stored as a library version draws what the shipped SIHRS draws, and the
engine reads every prior kind a library model may write.

Skipped unless FLUBNF_BNG_REAL=1, test_real_bng.py's flag (CI's steps
that set it name their files, so CI never runs this one), and skipped
when this machine's engine is missing or stale, or the hub clone
FLUBNF_TEST_HUB names holds no 2024-12-28 vintage. One week and one
location: Vermont as of 2024-12-28, 1 replicate of 500 particles.
"""
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402

from app.core import data as core_data                   # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.core.runs import RunSpec                        # noqa: E402
from app.tests.test_library import _by_hand              # noqa: E402
from flubnf import settings                              # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("FLUBNF_BNG_REAL") != "1",
    reason="runs the real engine: set FLUBNF_BNG_REAL=1")

ASOF = "2024-12-28"
#: draws equal to the last digit off Apple silicon: the private engine's
#: BLAS products can differ there between two runs (docs/team/engine.md)
EXACT = sys.platform == "darwin" and platform.machine() == "arm64"


@pytest.fixture
def real(monkeypatch, tmp_path):
    """This machine's engine, Perl, BNG2.pl and hub clone; the library in
    tmp_path."""
    monkeypatch.setattr(pf, "PYBNF_PF", settings.PYBNF)  # not the stub fork
    if not (pf.perl_available() and pf.engine_available()
            and pf.engine_current()):
        pytest.skip("this machine's engine is missing or stale, or Perl is")
    hub = os.environ.get("FLUBNF_TEST_HUB")
    arch = hub and Path(hub) / "auxiliary-data" / "target-data-archive"
    if not (arch and (arch / f"target-hospital-admissions_{ASOF}.csv")
            .is_file()):
        pytest.skip(f"no {ASOF} vintage in the hub clone FLUBNF_TEST_HUB "
                    "names")
    monkeypatch.setattr(core_data, "ARCHIVE", arch)
    monkeypatch.setattr(core_data, "LOCATIONS",
                        Path(hub) / "auxiliary-data" / "locations.csv")
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    return tmp_path


def _fit(root: Path, extra: dict) -> dict:
    """Vermont's week prepared, fitted and collected: its draws."""
    spec = RunSpec(engine="retro", forecast_date=ASOF, locations=["Vermont"],
                   season_start="2024-08-01", replicates=1, particles=500,
                   extra=extra)
    pf.prepare(spec, root)
    assert pf.execute(root, width=1) == {"Vermont_r0": "ok"}
    return pf.collect(root)["Vermont"]


def _stored(edit=lambda t: t) -> dict:
    files = L.shipped_files("sihrs")
    files["priors.conf"] = edit(files["priors.conf"])
    return {f: L.replay_text(f, t) for f, t in files.items()}


def test_a_library_copy_of_sihrs_draws_what_sihrs_draws(real):
    _by_hand("ctl", _stored())
    shipped = _fit(real / "shipped", {})
    copy = _fit(real / "copy", {"model": "ctl@1"})
    assert set(copy) == set(shipped)
    for h in shipped:
        a, b = np.asarray(shipped[h]), np.asarray(copy[h])
        if EXACT:
            assert np.array_equal(a, b), h
        else:
            np.testing.assert_allclose(b, a, rtol=1e-6, err_msg=h)


def test_the_engine_reads_every_prior_kind(real):
    _by_hand("kinds", _stored(lambda t: t
                              .replace("uniform_var = eps1__FREE 0.0 1.0",
                                       "normal_var = eps1__FREE 0.15 0.05")
                              .replace("loguniform_var = r__FREE 0.1 40.0",
                                       "lognormal_var = r__FREE 0.9 0.2")))
    conf = L.replay_conf(L.resolve("kinds@1")["files"])[1]
    assert {ln.split(" = ")[0] for ln in conf.splitlines()} == {
        "uniform_var", "loguniform_var", "normal_var", "lognormal_var"}
    assert _fit(real / "kinds", {"model": "kinds@1"})
