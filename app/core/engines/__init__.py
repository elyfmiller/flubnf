"""The console's forecasting engines.

SHIPPED
  pf        the Oracle SIHRS filter: writes pf.conf and runs the filter in
            its own venv; its samples go through the Oracle step
            (app/core/oracle.py, flubnf/oracle*.py). By default the public
            engine runs it (lwf); FLUBNF_ENGINE=private runs PyBNF
            `fit_type=pf` (the lab's fork) instead, the fallback.
  lwf       the public engine: lanl/PyBNF's job_type = lwf (the Liu–West
            filter), from the venv engine-requirements.txt pins; pf hands
            each prepared cell to it.
  analogue  the Groundhog: flubnf.analogue with the shipped auxiliary donor
            bank spliced in (SHIPPED_AUX).
"""
