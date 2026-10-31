"""Shared setup for the launcher and CLI tests."""
import pytest


@pytest.fixture(autouse=True)
def _private_engine_unless_asked(monkeypatch):
    """Every test sees the default engine (private) whatever the shell
    exports (FLUBNF_ENGINE=public, from .flubnf.env)."""
    for var in ("FLUBNF_ENGINE", "FLUBNF_PY_ENGINE_PUBLIC", "FLUBNF_ENGINE_LOCK"):
        monkeypatch.delenv(var, raising=False)
