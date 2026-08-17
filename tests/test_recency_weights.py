"""The PyBNF recency-weighting patch must weight, and must weight correctly.

This targets the ONE phase where SIHRS loses to the FluSight baseline: the
post-peak shoulder, relWIS 1.205, forecasting 1.5-3.3x too low because a
single-wave fit held in place by months of pre-peak data extrapolates continued
decline. If these weights are silently not applied -- or applied unnormalised --
a tau sweep would measure nothing, or would measure MCMC temperature instead of
data weighting, and the result would look like a finding either way.

Applied by patches/pybnf_recency_weights.py. Skipped if that has not been run.
"""
from __future__ import annotations

import numpy as np
import pytest

pybnf_config = pytest.importorskip("pybnf.config")
from pybnf.data import Data  # noqa: E402

apply_recency_weights = getattr(pybnf_config, "apply_recency_weights", None)
pytestmark = pytest.mark.skipif(
    apply_recency_weights is None,
    reason="run patches/pybnf_recency_weights.py to install recency weighting")


@pytest.fixture
def exp_file(tmp_path):
    """A 20-week .exp in the same format write_exp() emits."""
    p = tmp_path / "s_flu.exp"
    rows = "\n".join(f"{i} {10.0 + i:.6f}" for i in range(20))
    p.write_text("# time H_weekly\n" + rows + "\n")
    return p


@pytest.fixture
def data(exp_file):
    return Data(file_name=str(exp_file))


class TestOffByDefault:
    def test_unpatched_behaviour_is_all_ones(self, data):
        """The default must be byte-identical to stock PyBNF, or every fit ever
        run before this patch becomes non-reproducible."""
        assert np.allclose(data.weights, 1.0)

    def test_default_config_is_zero(self):
        assert pybnf_config.Configuration.default_config()["recency_tau"] == 0.0

    @pytest.mark.parametrize("tau", [0, 0.0, None, -1.0])
    def test_non_positive_tau_is_a_no_op(self, data, tau):
        apply_recency_weights(data, tau)
        assert np.allclose(data.weights, 1.0)


class TestWeighting:
    def test_recent_points_outweigh_old_ones(self, data):
        apply_recency_weights(data, 8.0)
        w = data.weights[:, 1]
        assert w[-1] > w[0]
        assert np.all(np.diff(w) > 0), "weights must increase monotonically in time"

    def test_decay_is_exponential_with_the_stated_tau(self, data):
        """w_i / w_j == exp((t_i - t_j)/tau) -- survives the mean-1 rescale."""
        tau = 5.0
        apply_recency_weights(data, tau)
        w = data.weights[:, 1]
        t = data.data[:, 0]
        assert w[10] / w[4] == pytest.approx(np.exp((t[10] - t[4]) / tau), rel=1e-9)

    def test_mean_weight_is_one(self, data):
        """Unnormalised weights would shrink the total log-likelihood and so
        change the Metropolis acceptance temperature -- a tau sweep would then
        confound weighting with sampler temperature."""
        for tau in (2.0, 8.0, 40.0):
            apply_recency_weights(data, tau)
            assert data.weights[:, 1].mean() == pytest.approx(1.0, rel=1e-12)

    def test_large_tau_approaches_uniform(self, data):
        apply_recency_weights(data, 1e7)
        assert np.allclose(data.weights, 1.0, atol=1e-4)

    def test_small_tau_concentrates_on_the_last_weeks(self, data):
        apply_recency_weights(data, 2.0)
        w = data.weights[:, 1]
        assert w[-4:].sum() / w.sum() > 0.5, "tau=2 should localise on recent weeks"

    def test_shape_matches_the_data(self, data):
        """objective.py indexes weights[rownum, cols[col_name]], so a 1-D array
        or a transposed one would raise or silently mis-weight."""
        apply_recency_weights(data, 8.0)
        assert data.weights.shape == data.data.shape

    def test_every_column_carries_the_row_weight(self, data):
        apply_recency_weights(data, 8.0)
        for j in range(data.data.shape[1]):
            assert np.allclose(data.weights[:, j], data.weights[:, 0])


class TestReachesTheObjective:
    def test_objective_actually_consumes_the_weights(self, data):
        """The real integration seam: SummationObjective multiplies each point
        by exp_data.weights. Verified by evaluating the SAME sim data against
        weighted and unweighted exp data and requiring a different answer."""
        from pybnf.objective import SumOfSquaresObjective

        # The residual MUST vary with time. With a constant residual, mean-1
        # weights give sum(w_i * c) = c * n regardless of tau, so a correct
        # patch and an inert one produce the identical number.
        resid = np.linspace(1.0, 9.0, data.data.shape[0])
        sim = Data(arr=np.column_stack([data.data[:, 0], data.data[:, 1] + resid]))
        sim.cols, sim.headers = dict(data.cols), dict(data.headers)

        obj = SumOfSquaresObjective(ind_var_rounding=1)
        flat = obj.evaluate(sim, data, show_warnings=False)
        apply_recency_weights(data, 3.0)
        weighted = obj.evaluate(sim, data, show_warnings=False)

        assert flat is not None and weighted is not None
        assert weighted != pytest.approx(flat), (
            "weights did not reach the objective -- the patch is inert")
        # Residuals grow with time, so up-weighting recent points must RAISE the
        # objective. A patch that weighted backwards would pass the != check.
        assert weighted > flat

    def test_uniform_weights_leave_the_objective_unchanged(self, data):
        """A huge tau is ~uniform, so it must reproduce the unweighted value.
        Without this, the previous test would pass for a patch that corrupts
        the objective rather than weights it."""
        from pybnf.objective import SumOfSquaresObjective

        # The residual MUST vary with time. With a constant residual, mean-1
        # weights give sum(w_i * c) = c * n regardless of tau, so a correct
        # patch and an inert one produce the identical number.
        resid = np.linspace(1.0, 9.0, data.data.shape[0])
        sim = Data(arr=np.column_stack([data.data[:, 0], data.data[:, 1] + resid]))
        sim.cols, sim.headers = dict(data.cols), dict(data.headers)

        obj = SumOfSquaresObjective(ind_var_rounding=1)
        flat = obj.evaluate(sim, data, show_warnings=False)
        apply_recency_weights(data, 1e9)
        assert obj.evaluate(sim, data, show_warnings=False) == pytest.approx(flat, rel=1e-6)
