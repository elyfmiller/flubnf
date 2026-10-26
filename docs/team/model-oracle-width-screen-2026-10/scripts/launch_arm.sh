#!/bin/bash
# launch_arm.sh <arm> [extra --knob ...]: one arm over the three seasons
# (LIVE=0 drops the live knobs: the registered member REG),
# logged, the Mac kept awake (caffeinate) while it runs
S=~/Documents/FluBNF-local/research/oracle-width-screen
source $S/env.sh
ARM=$1; shift
mkdir -p $S/arms $S/logs
cd $SCREEN_WT
KN=$LIVE_KNOBS; [ "${LIVE:-1}" = 0 ] && KN=""
caffeinate -is $PY $S/run_arm.py $ARM $S/arms $KN "$@" > $S/logs/$ARM.log 2>&1
echo "exit $? $(date -u +%FT%TZ)" >> $S/logs/$ARM.log
