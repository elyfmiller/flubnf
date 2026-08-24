import json
from pathlib import Path
import numpy as np
import anchor_math as AM
from pybnf.pf import ParticleFilter, systematic_resample

class SlopeAnchoredPF(ParticleFilter):
    anchor = None

    def _write_outputs(self, cloud, mu_hist, repl, rng):
        # 1. the production forward, untouched and bit-identical
        super()._write_outputs(cloud, mu_hist, repl, rng)
        a = self.anchor
        runs = Path(self.out_dir) / 'Results' / 'A_MCMC' / 'Runs'
        base = int(self.config.config.get('seed') or 0)
        r2 = np.random.default_rng(base + 3000 + repl)
        idx = systematic_resample(cloud.weights, r2)
        theta = cloud.theta[idx]
        species = cloud.species[idx]
        names = list(self.names)
        N = float(a['N'])
        s_frac = species[:, int(a['idx_S'])] / N
        t_mod = species[:, int(a['idx_t'])]
        t0m = float(cloud.t_last)
        # origin cloud for the turn gate (equal-weight draws)
        np.savez_compressed(
            runs / ('cloud_%d.npz' % repl),
            theta=theta.astype(np.float32),
            pnames=np.array(names),
            S=species[:, int(a['idx_S'])].astype(np.float32),
            I=species[:, int(a['idx_I'])].astype(np.float32),
            t=t_mod.astype(np.float32))
        dt = (float(np.median(np.diff(self.times)))
              if len(self.times) > 1 else 1.0)
        cols0 = [m[idx] for m in mu_hist]
        diag = {'t_last': t0m, 's_frac_med': float(np.median(s_frac))}
        # a FIXED index per variant name: str.__hash__ is randomised per
        # process unless PYTHONHASHSEED is set, so hashing the name here
        # would silently break run-to-run reproducibility.
        vorder = sorted(a['variants'])
        for vname, spec in a['variants'].items():
            th = AM.apply_anchor(theta, names, float(spec['r_star']),
                                 s_frac, float(a['s0']), t0m,
                                 bool(spec['harmonic']))
            th_i = [dict(zip(names, th[j])) for j in range(th.shape[0])]
            sp = species.copy()
            cols = list(cols0)
            rv = np.random.default_rng(base + 4000 + 17 * repl
                                       + 101 * vorder.index(vname))
            t = t0m
            for _ in range(self.forecast):
                mu = np.empty(sp.shape[0])
                for j in range(sp.shape[0]):
                    sp[j], seg = self.model.simulate_segment(
                        sp[j], th_i[j], t, t + dt)
                    mu[j] = self._mu_from_segment(seg, 0, th_i[j])
                t += dt
                r = np.array([max(d.get('r__FREE', 10.0), 1e-3)
                              for d in th_i])
                cols.append(rv.negative_binomial(
                    r, r / (r + np.maximum(mu, 1e-9))).astype(float))
            np.savetxt(runs / ('traj_slope_%s_chain_%d.txt'
                               % (vname, repl)), np.column_stack(cols))
            diag[vname] = {'reff_anchored_med': float(np.median(
                th[:, names.index('Reff__FREE')]))}
        (runs / ('anchor_diag_%d.json' % repl)).write_text(
            json.dumps(diag))

