"""FluBNF science package: the modules behind the FluBNF console (app/).

Each module's docstring opens with its role: SHIPPED (used by the console),
or the `flubnf` CLI itself (cli.py, and doctor.py behind `flubnf doctor`).
"""

# Lockstep with pyproject.toml, CITATION.cff and FluBNF.app's Info.plist
# (CFBundleShortVersionString, CFBundleVersion).
__version__ = "1.1.0"
