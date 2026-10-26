#!/bin/bash
# The screen's queue after C0 (PREREG.md section 1, amendment R): score C0,
# the registered member REG, the
# season-end fits and boxes, R20, R22, then HP and HS once amendment 1 is
# hashed. No arm starts after START_BY; WATCH stops a running arm before
# CDC's 2026-10-28 target-data update.
S=~/Documents/FluBNF-local/research/oracle-width-screen
source $S/env.sh
START_BY=2026-10-28T18:00:00Z
STOP_AT=2026-10-28T19:00:00Z
say() { echo "$(date -u +%FT%TZ) $*" >> $S/logs/chain.log; }
before() { [[ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" < "$1" ]]; }
wait_for() { while ! grep -q '^exit' $S/logs/$1.log 2>/dev/null; do sleep 60; done; }
score() {   # score an arm in the background at low priority, checks on
  ( cd $SCREEN_WT && FLUBNF_HUB=$SCREEN/scorehub nice -n 10 $PY $S/score_arm.py \
      $S/arms/$1 $S/arms/$1.cells.pkl --check > $S/logs/score_$1.log 2>&1;
    echo "exit $?" >> $S/logs/score_$1.log ) &
}
arm() { before $START_BY || { say "not starting $1: past $START_BY"; exit 0; }
        say "start $1 $*"; $S/launch_arm.sh "$@"; say "done $1 $(tail -1 $S/logs/$1.log)"; score $1; }
# the watchdog: request a stop on every arm root at STOP_AT
( while before $STOP_AT; do sleep 300; done
  cd $SCREEN_WT && $PY -c "
import sys; from pathlib import Path; from app.core import retro
for r in Path('$S/arms').glob('*/20??-??'): retro.request_stop(r)
print('stop requested')" >> $S/logs/chain.log 2>&1 ) &
say "chain waiting for C0"
# C0 was launched before this chain: wait for its replay process to end
while pgrep -f "run_arm.py C0 " > /dev/null; do sleep 60; done
say "C0 ended: $(tail -1 $S/logs/C0.log)"; score C0
before $START_BY || exit 0
say "start REG"; LIVE=0 $S/launch_arm.sh REG; say "done REG $(tail -1 $S/logs/REG.log)"; score REG
before $START_BY || exit 0
say "start FITS"
( export FLUBNF_HUB=$SCREEN/fitshub; cd $SCREEN_WT; caffeinate -is $PY $S/run_arm.py FITS $S/arms \
    --seasons 2022-23,2023-24,2024-25 --weeks 2023-06-10,2024-04-27,2025-06-14 \
    --all-weeks --keep-params --oracle-none --aux none \
    --knob pf.seed_denominator=season_total_early > $S/logs/FITS.log 2>&1; echo "exit $?" >> $S/logs/FITS.log )
say "FITS $(tail -1 $S/logs/FITS.log)"
cd $SCREEN_WT && $PY $S/build_boxes.py $S > $S/logs/boxes.log 2>&1 \
  && (cd $S && chmod a-w AMENDMENT1.md && shasum -a 256 AMENDMENT1.md > AMENDMENT1.sha256) \
  && say "amendment 1 $(cut -c1-16 $S/AMENDMENT1.sha256)" || say "boxes FAILED"
arm R20 --knob pf.prior.Reff=0.6,2.0
arm R22 --knob pf.prior.Reff=0.6,2.2
[ -f $S/AMENDMENT1.sha256 ] || { say "no amendment 1: HP and HS not started"; exit 0; }
HPK=$($PY -c "
import json; b = json.load(open('$S/boxes.json'))['boxes']
out = []
for s, v in b.items():
    for p in ('eps1', 'phi1'):
        lo, hi = v['HP'][p]; out += ['--season-knob', f'{s}:pf.prior.{p}={lo:g},{hi:g}']
print(' '.join(out))")
$PY -c "
import json; b = json.load(open('$S/boxes.json'))['boxes']
json.dump({s: v['HS'] for s, v in b.items()}, open('$S/hs_table.json', 'w'), indent=1)"
arm HP $HPK
arm HS --hs-table $S/hs_table.json
wait; say "chain done"
