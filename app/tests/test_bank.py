"""The committed donor banks: provenance, verification, and refusal.

Offline. Every test builds its own tiny bank in a tmp dir; nothing here
reads data/banks/ except the two tests that deliberately assert the
shipped artefact is present and self-consistent.
"""
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import bank as B                                   # noqa: E402

TINY = {("ca", date(2019, 10, 5)): 1.5,
        ("ca", date(2019, 10, 12)): 2.5,
        ("co", date(2019, 10, 5)): 0.75}


@pytest.fixture()
def banks(tmp_path):
    B.write("flusurv", TINY, source_url="https://example.invalid/",
            built_utc="2026-01-01T00:00:00+00:00", banks_dir=tmp_path)
    return tmp_path


# ---------------------------------------------------------------- the digest

def test_the_digest_is_over_content_not_file_bytes():
    """So that reformatting the JSON cannot change it, and a bank rebuilt
    from source can be compared with the committed one without writing a
    file first."""
    same_content_other_order = dict(reversed(list(TINY.items())))
    assert B.digest(same_content_other_order) == B.digest(TINY)


def test_a_changed_value_changes_the_digest():
    other = dict(TINY); other[("ca", date(2019, 10, 5))] = 1.6
    assert B.digest(other) != B.digest(TINY)


def test_a_dropped_cell_changes_the_digest():
    other = dict(TINY); other.pop(("co", date(2019, 10, 5)))
    assert B.digest(other) != B.digest(TINY)


# ------------------------------------------------------- write, read, verify

def test_write_then_read_round_trips(banks):
    got, man = B.read("flusurv", banks)
    assert got == TINY
    assert man["cells"] == 3 and man["location_count"] == 2
    assert man["span"] == ["2019-10-05", "2019-10-12"]
    assert man["source_url"] == "https://example.invalid/"
    assert man["digest"] == B.digest(TINY)


def test_a_bank_edited_without_its_manifest_is_refused(banks):
    """The failure this guards: someone hand-edits a value, the forecast
    changes, and the manifest still claims the original provenance."""
    p = B.bank_path("flusurv", banks)
    raw = json.loads(p.read_text())
    raw["ca|2019-10-05"] = 99.0
    p.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="does not match its manifest"):
        B.read("flusurv", banks)


def test_a_bank_with_no_manifest_is_refused(banks):
    B.manifest_path("flusurv", banks).unlink()
    with pytest.raises(FileNotFoundError, match="no manifest"):
        B.read("flusurv", banks)


def test_a_missing_bank_names_the_command_that_builds_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="flubnf bank build"):
        B.read("flusurv", tmp_path)


def test_an_empty_bank_is_never_written():
    with pytest.raises(ValueError, match="empty"):
        B.summarise({})


def test_an_unknown_stream_is_refused():
    with pytest.raises(ValueError, match="unknown stream"):
        B.write("nonsense", TINY, source_url="x", built_utc="y")


# ------------------------------------------------------------------- compare

def test_compare_reports_identical_when_it_is(banks):
    got, _ = B.read("flusurv", banks)
    d = B.compare(got, TINY)
    assert d["identical"] and d["added"] == 0 and d["removed"] == 0
    assert d["changed"] == 0


def test_compare_separates_added_removed_and_revised():
    fresh = dict(TINY)
    fresh[("ca", date(2019, 10, 5))] = 1.9          # revised
    fresh[("mn", date(2019, 10, 5))] = 3.0          # added
    fresh.pop(("co", date(2019, 10, 5)))            # removed
    d = B.compare(TINY, fresh)
    assert not d["identical"]
    assert d["added"] == 1 and d["removed"] == 1 and d["changed"] == 1
    assert d["changed_sample"][0]["committed"] == 1.5
    assert d["changed_sample"][0]["fresh"] == 1.9


# -------------------------------------------------------------- the engine

def test_a_preset_reads_the_committed_bank_not_the_network():
    from app.core.engines.analogue import AUX_PRESETS
    for name, pools in AUX_PRESETS.items():
        for p in pools:
            assert p.get("committed") is True, (
                f"preset {name!r} would fetch at forecast time; the shipped "
                f"path must not depend on an upstream API being reachable")
            assert "build" not in p and "bank" not in p


def test_the_preset_name_carries_the_bank_digest():
    """run_meta.json records this string and outlives the week manifests,
    so it is the only durable record of WHICH donors a replay used."""
    from app.core.engines.analogue import aux_preset
    got = aux_preset("flusurv").__name__
    assert got.startswith("aux_preset:flusurv+flusurv@")
    _b, man = B.read("flusurv")
    assert got.endswith(man["digest"][:8])


def test_a_pool_naming_two_sources_is_refused(tmp_path):
    from app.core.engines.analogue import splice_args
    spec = SimpleNamespace(forecast_date="2025-12-20", extra={"aux_pools": [
        {"stream": "flusurv", "weight": 0.5, "committed": True, "build": {}}]})
    with pytest.raises(ValueError, match="exactly one of"):
        splice_args(spec, {})


def test_a_pool_naming_no_source_is_refused():
    from app.core.engines.analogue import splice_args
    spec = SimpleNamespace(forecast_date="2025-12-20", extra={"aux_pools": [
        {"stream": "flusurv", "weight": 0.5}]})
    with pytest.raises(ValueError, match="exactly one of"):
        splice_args(spec, {})


# ------------------------------------------------- the shipped artefact

def test_the_shipped_flusurv_bank_is_present_and_self_consistent():
    """A clone must be able to produce a spliced forecast with no network."""
    b, man = B.read("flusurv")
    assert man["cells"] == len(b) > 5000
    assert man["stream"] == "flusurv"
    assert man["source_url"].startswith("https://api.delphi.cmu.edu/")
    # the shape flubnf.analogue.donor_ratios reads
    for (loc, d), v in list(b.items())[:20]:
        assert isinstance(loc, str) and isinstance(d, date) and v > 0


def test_the_shipped_bank_covers_the_seasons_the_arm_was_selected_on():
    b, man = B.read("flusurv")
    assert man["span"][0] < "2010-01-01", "the depth is the point of this stream"
    assert man["span"][1] > "2026-01-01"


def test_every_preset_stream_has_a_committed_bank():
    """A preset that names a stream with no committed bank fails at
    construction. That is the right failure, but it should never happen
    in a clean clone: every stream a preset uses must ship."""
    from app.core.engines.analogue import AUX_PRESETS
    for name, pools in AUX_PRESETS.items():
        for pcfg in pools:
            b, man = B.read(pcfg["stream"])
            assert man["stream"] == pcfg["stream"] and len(b) > 1000, name


def test_every_preset_constructs_offline():
    """aux_preset resolves its banks up front, so a missing or corrupt
    bank fails before the first fit rather than in week 40."""
    from app.core.engines.analogue import AUX_PRESETS, aux_preset
    for name in AUX_PRESETS:
        assert aux_preset(name).__name__.startswith(f"aux_preset:{name}+")
