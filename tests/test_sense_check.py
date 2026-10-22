"""scripts/sense_check.py, the pre-submission tail gate: the 97.5% quantile
at each horizon over the recent level (mean of the last three reported
weeks), FAIL when any horizon-3 ratio exceeds the threshold."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sense_check.py"

LEVELS = [0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
          0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99]


@pytest.fixture(scope="module")
def sc():
    spec = importlib.util.spec_from_file_location("sense_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def truth_frame() -> pd.DataFrame:
    # four reported weeks; the recent level is the mean of the last three:
    # Ohio (10, 20, 30) -> 20; Wyoming (0, 0, 0) -> 0; US (100, 200, 300) -> 200
    rows = []
    for d, oh, wy, us in [("2026-09-26", 99, 5, 999), ("2026-10-03", 10, 0, 100),
                          ("2026-10-10", 20, 0, 200), ("2026-10-17", 30, 0, 300)]:
        rows += [(d, "39", "Ohio", oh), (d, "56", "Wyoming", wy), (d, "US", "US", us)]
    return pd.DataFrame(rows, columns=["date", "location", "location_name", "value"])


def submission(upper_h3_ohio: float, upper_h3_wy: float = 50.0) -> pd.DataFrame:
    """Quantile rows for Ohio, Wyoming and US at horizons 0-3; every level
    below 0.975 sits at the median, the 0.975 and 0.99 levels at the given
    upper. Plus one pmf-style row and one other-target row the gate must
    ignore."""
    rows = []
    for loc, med, up3 in [("39", 40.0, upper_h3_ohio), ("56", 2.0, upper_h3_wy), ("US", 400.0, 2000.0)]:
        for h in range(4):
            up = up3 if h == 3 else med * 1.5
            for lv in LEVELS:
                v = up if lv >= 0.975 else (med * 0.5 if lv <= 0.025 else med)
                rows.append(("2026-10-24", "wk inc flu hosp", h, "2026-10-24", loc, "quantile", str(lv), v))
    rows.append(("2026-10-24", "wk flu hosp rate change", 3, "2026-11-14", "39", "pmf", "large_increase", 1.0))
    rows.append(("2026-10-24", "peak inc flu hosp", 3, "2026-11-14", "39", "quantile", "0.975", 99999.0))
    return pd.DataFrame(rows, columns=["reference_date", "target", "horizon", "target_end_date",
                                       "location", "output_type", "output_type_id", "value"]).astype(str)


def test_the_recent_level_is_the_mean_of_the_last_three_reported_weeks(sc):
    recent, last, dates = sc.recent_levels(truth_frame())
    assert dates == ["2026-10-03", "2026-10-10", "2026-10-17"]
    assert recent["39"] == 20 and recent["56"] == 0 and recent["US"] == 200
    assert last["39"] == 30


def test_a_horizon_3_ratio_over_the_threshold_fails_the_file(sc):
    recent, _, _ = sc.recent_levels(truth_frame())
    passed, over, by_h = sc.gate(submission(upper_h3_ohio=620.0), recent)       # 620 / 20 = 31x
    assert not passed and list(over.index) == ["39"]
    assert over.loc["39", "ratio"] == pytest.approx(31.0)
    assert by_h[3].loc["39", "band"] == pytest.approx((620 - 20) / 40)
    passed, over, _ = sc.gate(submission(upper_h3_ohio=580.0), recent)          # 29x
    assert passed and over.empty


def test_the_threshold_is_a_parameter_and_only_horizon_3_gates(sc):
    recent, _, _ = sc.recent_levels(truth_frame())
    sub = submission(upper_h3_ohio=580.0)                                        # h3 29x; h0-h2 are 3x
    assert sc.gate(sub, recent, threshold=20.0)[0] is False
    assert sc.gate(sub, recent, threshold=29.5)[0] is True
    # a wide horizon 2 alone does not fail the file
    sub2 = sub.copy()
    wide = (sub2["location"] == "39") & (sub2["horizon"] == "2") & (pd.to_numeric(sub2["output_type_id"], errors="coerce") >= 0.975)
    sub2.loc[wide, "value"] = "9000"
    passed, _, by_h = sc.gate(sub2, recent)
    assert passed and by_h[2].loc["39", "ratio"] == pytest.approx(450.0)


def test_a_zero_recent_level_never_fails_and_other_targets_are_ignored(sc):
    recent, _, _ = sc.recent_levels(truth_frame())
    passed, over, by_h = sc.gate(submission(upper_h3_ohio=100.0, upper_h3_wy=5000.0), recent)
    assert passed and over.empty
    assert pd.isna(by_h[3].loc["56", "ratio"])          # Wyoming's recent level is 0
    assert by_h[3].loc["39", "upper"] == 100.0          # the 99999 peak row did not leak in


def test_the_script_reports_and_exits_1_on_a_failing_file(tmp_path: Path):
    truth = tmp_path / "target-hospital-admissions.csv"
    truth_frame().to_csv(truth, index=False)
    bad = tmp_path / "2026-10-24-NAU_PyBNF-OracleSIHRS.csv"
    good = tmp_path / "2026-10-24-NAU_PyBNF-GroundHogCGR.csv"
    submission(upper_h3_ohio=620.0).to_csv(bad, index=False)
    submission(upper_h3_ohio=100.0).to_csv(good, index=False)
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(truth), str(bad), str(good)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 1, r.stderr
    assert "FAIL (1 at horizon 3): Ohio 31x (97.5% 620, median 40, recent 20.0, last 30)" in r.stdout
    assert r.stdout.count("PASS") == 1 and "GroundHogCGR" in r.stdout
    assert "recent level = mean of 2026-10-03..2026-10-17; threshold 30x" in r.stdout
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(truth), str(good), "--threshold", "2"],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 1 and "over 2x" in r.stdout
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(truth), str(tmp_path / "missing.csv")],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 2 and "not found" in r.stderr
