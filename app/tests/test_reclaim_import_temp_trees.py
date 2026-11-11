"""Storage's reclaim passes over an import's temp tree and a Replace's old
run set aside (the review of #105 at 1ce301ed, finding 3, and the
independent check beside it).

reclaim._season_entries took every folder under the retro root with a
weeks folder for a season tree, so <run>.importing-<pid>-<random> and
<run>.replaced-<pid>-<random> came back in the survey's compress_ids, and
the perform step gzipped a live import's samples (the import was then
refused, "removed from the import's temporary folder"). Both steps now
skip any name replay_bundle's temp pattern matches, alike, so the
stale-confirmation counts stay equal. Since the seventh pass's check, the
research roots' loop (an import with --root into one) does the same.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import reclaim                               # noqa: E402
from app.core import replay_bundle as rb                   # noqa: E402
from test_reclaim import SEASON, W1, _mk_week, _snapshot   # noqa: E402

RUN = f"{SEASON}__archived_20980204T101500Z"

TEMPS = [f"{RUN}.importing-{os.getpid()}-0a0b0c0d",
         f"{RUN}.replaced-{os.getpid()}-1a1b1c1d",
         f"{RUN}.dropping-{os.getpid()}-2a2b2c2d",   # an old run let go
         f"{RUN}.importing"]                      # an older build's name


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A retro root with one archived run (plain samples, fit leftovers)
    and, beside it, the same tree under each temp name."""
    monkeypatch.setattr(reclaim, "APP_STATE", tmp_path)
    import flubnf.settings as settings_mod
    monkeypatch.setattr(settings_mod, "HUB", tmp_path / "hub")
    rr = tmp_path / "retro"
    for name in [RUN, *TEMPS]:
        _mk_week(rr / name, W1)
    return {"rr": rr, "workroots": tmp_path / "workroots"}


def test_the_survey_and_the_perform_step_pass_over_the_temp_trees(world):
    rr = world["rr"]
    before = {n: _snapshot(rr / n) for n in TEMPS}
    plan = reclaim.survey(rr, world["workroots"], research_roots=())
    assert plan["season_ids"] == [RUN]
    assert plan["compress_ids"] == [RUN]
    assert reclaim.plan_counts(plan) == (1, 0, 1)
    out = reclaim.execute(rr, world["workroots"], research_roots=())
    assert (out["weeks"], out["workroots"], out["compress_files"]) == \
        reclaim.plan_counts(plan)
    for n in TEMPS:
        assert _snapshot(rr / n) == before[n], f"{n} was touched"
    assert (rr / RUN / "weeks" / W1 / "samples.json.gz").is_file()


def test_the_temp_names_are_the_imports_own():
    """One definition, replay_bundle's: what its sweep knows, reclaim
    skips; names that only look like one are season trees as before."""
    for n in TEMPS:
        assert rb.is_temp_name(n), n
    for n in (SEASON, RUN, f"{RUN}.importing-x", f"{RUN}.replaced",
              f"{RUN}.replaced-12-x", f"{RUN}.importingz", f"{RUN}.dropping",
              f"{RUN}.dropping-12-x", ""):
        assert not rb.is_temp_name(n), n


def test_a_research_root_passes_over_the_temp_trees_too(world, tmp_path):
    """The seventh pass's check: the research roots' loop (compress-only)
    took any folder with a weeks folder, temp names included, in the
    survey and the perform step. Both now pass over them, alike."""
    research = tmp_path / "retro_2s"
    for name in [RUN, *TEMPS]:
        _mk_week(research / name, W1)
    before = {n: _snapshot(research / n) for n in TEMPS}
    plan = reclaim.survey(tmp_path / "no-retro", world["workroots"],
                          research_roots=[research])
    assert plan["compress_ids"] == [RUN]
    assert reclaim.plan_counts(plan) == (0, 0, 1)
    out = reclaim.execute(tmp_path / "no-retro", world["workroots"],
                          research_roots=[research])
    assert (out["weeks"], out["workroots"], out["compress_files"]) == \
        reclaim.plan_counts(plan)
    for n in TEMPS:
        assert _snapshot(research / n) == before[n], f"{n} was touched"
    assert (research / RUN / "weeks" / W1 / "samples.json.gz").is_file()


def test_an_import_into_a_research_root_is_not_compressed_under_it(
        world, tmp_path, monkeypatch):
    """The check's case: `flubnf retro import --root` into a research root;
    a reclaim runs while it extracts. Its temp tree is in neither step's
    list, nothing is compressed, and the import lands whole."""
    from test_retro_import_directory_and_swap import _bundle, _files
    bundle = _bundle(tmp_path)
    ref = rb.import_bundle(bundle, tmp_path / "reference").root
    research = tmp_path / "retro_2s"
    research.mkdir()
    real, n, seen = rb._extract_member, [0], {}

    def extract(z, name, d, *a):
        real(z, name, d, *a)
        n[0] += 1
        if n[0] == 6:                 # several weeks' samples are in by now
            seen["plan"] = reclaim.survey(tmp_path / "no-retro",
                                          world["workroots"],
                                          research_roots=[research])
            seen["out"] = reclaim.execute(tmp_path / "no-retro",
                                          world["workroots"],
                                          research_roots=[research])
    monkeypatch.setattr(rb, "_extract_member", extract)
    r = rb.import_bundle(bundle, research)
    assert seen["plan"]["compress_ids"] == []
    assert seen["out"]["compress_files"] == 0
    assert _files(r.root) == _files(ref)
