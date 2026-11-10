"""Shared setup for the launcher and CLI tests."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _engine_pinned_private(monkeypatch):
    """The suite pins the private engine (the fallback), whose stub fork
    about 90 test files encode, whatever the shell exports. The default,
    the public engine, has its own tests: they set FLUBNF_ENGINE
    themselves."""
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    for var in ("FLUBNF_PY_ENGINE_PUBLIC", "FLUBNF_ENGINE_LOCK"):
        monkeypatch.delenv(var, raising=False)
    lwf = sys.modules.get("app.core.engines.lwf")    # not imported: no cache
    if lwf is not None:
        lwf._CHECK.clear()
        lwf._BUILD.clear()
        lwf._PENDING.clear()


@pytest.fixture(scope="session")
def _no_record_root(tmp_path_factory):
    """An install folder with no .flubnf.env and no .flubnf.env.cmd."""
    return tmp_path_factory.mktemp("no-record")


@pytest.fixture(autouse=True)
def _no_engine_record(monkeypatch, _no_record_root):
    """settings reads no engine record from the checkout (INSTALL_ROOT is
    an empty folder), whatever its .flubnf.env says, so a test that unsets
    FLUBNF_ENGINE gets the default. Imported here whether or not the test's
    file imports it: a test that imports settings inside itself, in a file
    run alone, read the checkout's own record (a private one picked the
    private engine). The launcher tests run the scripts, which never read
    this."""
    from flubnf import settings
    monkeypatch.setattr(settings, "INSTALL_ROOT", _no_record_root)
    settings.forget_record()
    yield
    settings.forget_record()
