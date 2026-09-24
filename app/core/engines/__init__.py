"""The console's forecasting engines.

SHIPPED
  pf        the Oracle SIHRS filter: writes pf.conf and runs PyBNF
            `fit_type=pf` (the fork) in the engine venv; its samples go
            through the Oracle step (app/core/oracle.py, flubnf/oracle*.py).
  analogue  the Groundhog: flubnf.analogue with the shipped auxiliary donor
            bank spliced in (SHIPPED_AUX).
"""
