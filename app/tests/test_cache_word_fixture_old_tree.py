"""test_cache_lock_word_clear.py's fixture on a tree without pf._CODEGEN_SAID
(review of #93 at d5a7eb16, finding 3).

Its autouse fixture (fresh_word) set pf._CODEGEN_SAID with
monkeypatch.setattr's default raising=True, so on sources older than the
word every one of its 13 tests errored at setup, the 7 that test unchanged
behavior too. Here the fixture runs, as there, on a pf whose _CODEGEN_SAID
is taken away first: it must go through. Nothing is launched or written.
"""
import pytest

from app.core.engines import pf

from test_cache_lock_word_clear import fresh_word      # noqa: E402,F401


@pytest.fixture
def monkeypatch(monkeypatch):
    """The fixture's own monkeypatch, with pf as an older tree has it: no
    _CODEGEN_SAID (put back after the test)."""
    monkeypatch.delattr(pf, "_CODEGEN_SAID", raising=False)
    return monkeypatch


def test_the_fixture_goes_through_on_a_tree_without_the_word():
    # fresh_word (autouse) ran first, on a pf without _CODEGEN_SAID
    assert pf._CODEGEN_SAID == {}
