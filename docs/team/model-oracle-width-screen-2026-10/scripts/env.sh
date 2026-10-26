# sourced by every script of the screen: one worktree, one hub, one engine
export SCREEN=~/Documents/FluBNF-local/research/oracle-width-screen
export SCREEN_WT=$SCREEN/wt
# replays read the dated vintages from the research hub clone (09c96ec8)
export FLUBNF_HUB=~/Documents/FluBNF-local/research/groundhog-beta/oracle_member/us_national/hub
# the production engine pin, read-only; bngsim 0.15.1 and numpy 1.26.4 as on
# Ely's laptop and the cloud testbed (not ~/.venvs/flubnf, bngsim 0.13.0)
export FLUBNF_PYBNF=$HOME/GitHub/PyBNF-pf
export FLUBNF_PY_ENGINE=$HOME/.venvs/flubnf-engine/bin/python
# which weeks are scoreable: the FluSight-baseline files (lab clone, read-only)
export SCREEN_BASELINE=$HOME/GitHub/FluSight-forecast-hub/model-output/FluSight-baseline
export PY=$HOME/GitHub/flubnf/.venv/bin/python
# the live configuration of the 2026-10-24 round (submission.md 2026-10-21)
export LIVE_KNOBS="--knob pf.seed_denominator=season_total_early --knob oracle.w=0.25 --knob oracle.narrow=0.7"
