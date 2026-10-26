#!/bin/zsh
# prereg c9587ab57ab6db4b: the kernel form over the three replay seasons and the current season's weeks, in parallel
export FLUBNF_HUB=/Users/elymiller/Documents/GitHub/FluSight-forecast-hub
export PYTHONPATH=/private/tmp/claude-501/-Users-elymiller-Documents/dbc89cc0-3f94-4e10-bc4f-722c7bb081c0/scratchpad/wt-hist
cd /Users/elymiller/Documents/FluBNF-local/research/groundhog-hist-ceiling
mkdir -p results
for s in 2025-26 2024-25 2023-24 2026-27; do echo $s; done | \
  xargs -P 4 -I{} sh -c '~/GitHub/flubnf/.venv/bin/python run_kernel.py {} results > results/log_{}.txt 2>&1; tail -1 results/log_{}.txt'
