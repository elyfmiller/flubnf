import sys
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
import report as R
arm, c0 = sys.argv[2], sys.argv[3]
ra = R.rules_frame(R.load(arm)); rc = R.rules_frame(R.load(c0))
oa, ha = R.loso(ra); oc, hc = R.loso(rc)
print("held-out exact: arm %.5f / %.5f  C0 %.5f / %.5f" % (ha['rel'], ha['log'], hc['rel'], hc['log']))
for (s, k, rule, p), (_, kc, rulec, pc) in zip(oa, oc):
    print(f"  {s}: arm {p['rel']:.5f} C0 {pc['rel']:.5f} diff {p['rel']-pc['rel']:+.5f} | log arm {p['log']:.4f} C0 {pc['log']:.4f}")
# (iv) variants
def pick(r, s, k, rule):
    return r[(r.season == s) & (r.k == k) & (r.rule == rule)]
# a) both at C0's per-season held-out choice
A = pd.concat([pick(ra, s, kc, rc_) for (s, kc, rc_, _) in oc]); C = pd.concat([pick(rc, s, kc, rc_) for (s, kc, rc_, _) in oc])
d = R.boot_diff(A, C, 2000); print("both at C0's per-season choice: %+.4f [%+.4f, %+.4f] | log %+.4f [%+.4f, %+.4f]" % d)
# b) held-out arm at its choices minus held-out C0 at its choices
A = pd.concat([pick(ra, s, k, rule) for (s, k, rule, _) in oa]); C = pd.concat([pick(rc, s, kc, rc_) for (s, kc, rc_, _) in oc])
d = R.boot_diff(A, C, 2000); print("held-out vs held-out (own choices): %+.4f [%+.4f, %+.4f] | log %+.4f [%+.4f, %+.4f]" % d)
# c) fixed settings
for kk, rr in ((0.7, "clip 15x"), (0.7, "clip 10x"), (0.7, "none"), (0.8, "clip 15x"), (0.8, "clip 10x"), (0.8, "shrink 20x"), (0.8, "none")):
    ya = ra[(ra.k == kk) & (ra.rule == rr)]; yc = rc[(rc.k == kk) & (rc.rule == rr)]
    d = R.boot_diff(ya, yc, 2000)
    pa, pc = R.pooled(ya), R.pooled(yc)
    seas = " ".join(f"{s} {R.pooled(ya[ya.season==s])['rel']-R.pooled(yc[yc.season==s])['rel']:+.3f}" for s in sorted(ya.season.unique()))
    ga, gc = R.gate(ya), R.gate(yc)
    print(f"k {kk} {rr}: arm {pa['rel']:.3f}/{pa['log']:.3f} c95 {pa['c95']:.3f} >30x {ga['over30']:.3f} | C0 {pc['rel']:.3f}/{pc['log']:.3f} c95 {pc['c95']:.3f} >30x {gc['over30']:.3f} | diff %+.4f [%+.4f, %+.4f] | log %+.4f [%+.4f, %+.4f] | {seas}" % d)
# early weeks at live settings
for kk, rr in ((0.7, "clip 15x"), (0.7, "clip 10x")):
    ya = ra[(ra.k == kk) & (ra.rule == rr) & ra.early]; yc = rc[(rc.k == kk) & (rc.rule == rr) & rc.early]
    d = R.boot_diff(ya, yc, 2000); print(f"Sep-Nov k {kk} {rr}: arm {R.pooled(ya)['rel']:.3f} C0 {R.pooled(yc)['rel']:.3f} c95 {R.pooled(ya)['c95']:.2f}/{R.pooled(yc)['c95']:.2f} diff %+.4f [%+.4f, %+.4f] | log %+.4f [%+.4f, %+.4f]" % d)
