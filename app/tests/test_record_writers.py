"""The big JSON records are written through the C encoder (P2, F5).

json.dump runs CPython's pure-Python encoder; json.dumps the C one, about
twice as fast on a week's draws. The three writers (a week's samples, a
console run's filter record, oracle.json) now encode once with json.dumps
and write the text in slices. The stored JSON must not change by a byte:
the writers as they stood (frozen below) and the new ones give equal
decompressed bytes on a record built to trip any encoder difference
(numpy floats as values and keys, NaN and infinities, non-ASCII, a big
int, an IntEnum, bool and None keys). A gz header carries its write time,
so the decompressed JSON is the artifact compared, as everywhere.
"""
import enum
import gzip
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz                        # noqa: E402
from app.core import oracle                                # noqa: E402
from app.core import retro_store                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402


# --------------------------------------------- the writers before P2 (frozen)

def _old_write_week_samples(wd: Path, obj: dict) -> Path:
    wd = Path(wd)
    fp = wd / retro_store.SAMPLES_GZ
    tmp = wd / (retro_store.SAMPLES_GZ + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        json.dump(hz.record_to_stored(obj), f)
    os.replace(tmp, fp)
    (wd / retro_store.SAMPLES_JSON).unlink(missing_ok=True)
    try:
        retro_store.write_week_quantiles(wd, retro_store.member_quantiles(obj, wd))
    except Exception:
        pass
    return fp


def _old_write_provenance(out_dir, prov: dict) -> Path:
    fp = Path(out_dir) / oracle.PROVENANCE_NAME
    tmp = fp.with_name(fp.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(prov, fh)
    os.replace(tmp, fp)
    return fp


def _old_write_filter_record(workroot, asof: str, raw: dict) -> Path:
    fp = Path(workroot) / oracle.FILTER_RECORD_NAME
    tmp = fp.with_name(fp.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(hz.record_to_stored({"asof": asof, oracle.FILTER_KEY: raw}),
                  fh)
    os.replace(tmp, fp)
    return fp


# ------------------------------------------------------------------ records

class _Level(enum.IntEnum):
    LOW = 3


def _odd_values() -> dict:
    """Every value and key kind the two encoders could treat differently."""
    return {
        "np_float": np.float64(1234.5678901234567),
        "np_float_tiny": np.float64(5e-324),
        "floats": [0.1, 1e300, -0.0, 1.0, 2.5e-8, 123456789.123456789],
        "nan": float("nan"), "inf": float("inf"), "ninf": float("-inf"),
        "np_nan": np.float64("nan"),
        "big_int": 2 ** 70, "neg": -17, "enum": _Level.LOW,
        "bool": True, "none": None,
        "text": "Zoë 東京 \U0001F600 \"quoted\" back\\slash\nline\ttab",
        "nested": [[1, 2.0, "x"], {"a": [None, False]}],
        np.float64(0.025): "np float key", 0.975: "float key",
        7: "int key", True: "bool key", None: "None key",
    }


def _week(seed=7, draws=2_000) -> dict:
    """A canonical week record: pf draws (with a NaN and a numpy float),
    the analogue's quantile sets, the odd values riding along."""
    rng = np.random.default_rng(seed)
    pf, an = {}, {}
    for loc in ("Ohio", "Utah", "Puerto Rico", "US"):
        pf[loc] = {h: [float(v) for v in rng.gamma(4.0, 30.0, draws)]
                   for h in [hz.ORIGIN, *hz.HORIZONS]}
        an[loc] = {h: {float(L): float(100 + (L - 0.5) * 40 + i)
                       for L in QL}
                   for i, h in enumerate(hz.HORIZONS)}
    pf["Ohio"][hz.HORIZONS[0]][3] = float("nan")
    pf["Utah"][hz.HORIZONS[1]][5] = np.float64(42.125)
    return {"asof": "2025-01-11", "pf": pf, "analogue": an,
            "extra": _odd_values()}


def _gunzip(fp: Path) -> bytes:
    with gzip.open(fp, "rb") as f:
        return f.read()


@pytest.fixture(params=[retro_store.WRITE_SLICE, 7],
                ids=["4MiB-slices", "7-char-slices"])
def slices(request, monkeypatch):
    """The production slice, and a tiny one (every slice boundary)."""
    monkeypatch.setattr(retro_store, "WRITE_SLICE", request.param)
    return request.param


# ------------------------------------------------------------------- pins

def test_a_weeks_samples_are_the_same_json(tmp_path, slices):
    rec = _week()
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(), new.mkdir()
    a = _gunzip(_old_write_week_samples(old, rec))
    b = _gunzip(retro_store.write_week_samples(new, rec))
    assert a == b and len(a) > 50_000
    # ASCII (ensure_ascii), the stored horizon convention, one line
    a.decode("ascii")
    assert b"\n" not in a
    # the sidecar beside it is unchanged too
    assert ((old / retro_store.QUANTILES_NAME).read_bytes()
            == (new / retro_store.QUANTILES_NAME).read_bytes())
    # no tmp left behind; the plain leftover is retired as before
    assert sorted(p.name for p in new.iterdir()) == \
        sorted(p.name for p in old.iterdir())


def test_the_samples_read_back_as_before(tmp_path):
    rec = _week(draws=50)
    rec.pop("extra")
    fp = retro_store.write_week_samples(tmp_path, rec)
    back = retro_store.read_samples(fp)
    assert back["asof"] == rec["asof"]
    assert back["analogue"]["Ohio"][hz.HORIZONS[0]][str(float(QL[0]))] == \
        rec["analogue"]["Ohio"][hz.HORIZONS[0]][float(QL[0])]
    assert back["pf"]["Utah"][hz.HORIZONS[2]] == rec["pf"]["Utah"][hz.HORIZONS[2]]


def test_a_runs_filter_record_is_the_same_json(tmp_path, slices):
    rec = _week(seed=11)
    raw = rec["pf"]
    raw["extra"] = rec["extra"]
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(), new.mkdir()
    a = _gunzip(_old_write_filter_record(old, "2025-01-11", raw))
    b = _gunzip(oracle.write_filter_record(new, "2025-01-11", raw))
    assert a == b and len(a) > 50_000


def test_oracle_json_is_the_same_bytes(tmp_path):
    prov = {"written_by": "app.core.oracle", "asof": "2025-01-11",
            "applied": True, "member": oracle.MEMBER_NAME,
            "quantiles": {"null": _week(draws=10)["analogue"]},
            "odd": _odd_values()}
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir(), new.mkdir()
    a = _old_write_provenance(old, prov).read_bytes()
    b = oracle.write_provenance(new, prov).read_bytes()
    assert a == b
    assert oracle.read_provenance(new)["asof"] == "2025-01-11"
    assert not list(new.glob("*.tmp"))


def test_an_unencodable_record_fails_as_before(tmp_path):
    """A value neither encoder takes (a numpy int) raises the same error
    and never replaces the stored file."""
    rec = {"asof": "2025-01-11", "pf": {}, "bad": np.int64(3)}
    with pytest.raises(TypeError) as old_err:
        _old_write_week_samples(tmp_path, rec)
    with pytest.raises(TypeError) as new_err:
        retro_store.write_week_samples(tmp_path, rec)
    assert str(old_err.value) == str(new_err.value)
    assert not (tmp_path / retro_store.SAMPLES_GZ).exists()
