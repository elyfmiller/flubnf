"""FluBNF science package: the modules behind the FluBNF console (app/).

Each module's docstring opens with its role: SHIPPED (used by the console),
LEGACY (the DE/AMCMC workspace loop behind the legacy `flubnf` commands) or
RESEARCH (only tests import it). The `flubnf` CLI lives in flubnf.cli.
"""

# Lockstep with pyproject.toml, CITATION.cff and FluBNF.app's Info.plist
# (CFBundleShortVersionString, CFBundleVersion).
__version__ = "1.1.0"
