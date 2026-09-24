"""`flubnf dataset validate|import|list|delete`: validate prints problems
(exit 1) or a summary (exit 0) and stores nothing; import stores what the
Data tab's upload stores; the group is filed under the Console help panel."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from flubnf.cli import HELP_PANELS, app

FIX = Path(__file__).resolve().parents[1] / "app" / "tests" / "fixtures"
runner = CliRunner()


def test_valid_grouped_template_prints_a_summary():
    r = runner.invoke(app, ["dataset", "validate",
                            str(FIX / "grouped-template-population-head.csv"),
                            "--kind", "count"])
    assert r.exit_code == 0, r.output
    assert "valid" in r.output
    assert "groups      3: Adult, Overall, Pediatric" in r.output
    assert "population  yes" in r.output


def test_undeclared_kind_is_reported_as_inferred():
    r = runner.invoke(app, ["dataset", "validate",
                            str(FIX / "grouped-template-head.csv")])
    assert r.exit_code == 0, r.output
    assert "count (inferred; declare it)" in r.output


def test_problems_are_printed_and_exit_1(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,target_group,value\n"
                 "2024-08-03,A,1\n2024-08-04,A,-2\n2024-08-24,A,3\n")
    r = runner.invoke(app, ["dataset", "validate", str(p), "--kind", "count"])
    assert r.exit_code == 1
    assert "problem(s)" in r.output
    assert "not Saturdays" in r.output and "negative" in r.output
    assert "Missing weeks" in r.output


def test_sunday_option_and_missing_file(tmp_path):
    p = tmp_path / "sun.csv"
    p.write_text("date,target_group,value\n2024-07-28,A,1\n2024-08-04,A,2\n")
    assert runner.invoke(app, ["dataset", "validate", str(p)]).exit_code == 1
    r = runner.invoke(app, ["dataset", "validate", str(p), "--sunday"])
    assert r.exit_code == 0, r.output
    assert "2024-08-03 to 2024-08-10" in r.output
    assert runner.invoke(app, ["dataset", "validate",
                               str(tmp_path / "nope.csv")]).exit_code == 2


def test_dataset_is_on_the_console_panel():
    assert "dataset" in HELP_PANELS["Console"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app.core import datasets as D
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    return D


def test_import_list_delete(store):
    src = FIX / "grouped-template-population-head.csv"
    r = runner.invoke(app, ["dataset", "import", str(src), "--kind", "count",
                            "--name", "Kids"])
    assert r.exit_code == 0, r.output
    (d,) = store.list_datasets()
    assert f"stored 'Kids' as {d.id}" in r.output
    assert "population  yes" in r.output and "none (final data)" in r.output
    again = runner.invoke(app, ["dataset", "import", str(src), "--kind",
                                "count", "--name", "Kids"])
    assert again.exit_code == 0 and len(store.list_datasets()) == 1
    r = runner.invoke(app, ["dataset", "list"])
    assert d.id in r.output and "3 group(s), 10 week(s), count" in r.output
    r = runner.invoke(app, ["dataset", "delete", d.id], input="n\n")
    assert r.exit_code == 1 and store.list_datasets()
    r = runner.invoke(app, ["dataset", "delete", d.id, "--yes"])
    assert r.exit_code == 0 and store.list_datasets() == []
    assert "no datasets stored" in runner.invoke(app, ["dataset", "list"]).output
    assert runner.invoke(app, ["dataset", "delete", d.id, "--yes"]).exit_code == 1


def test_import_prints_problems_and_stores_nothing(store, tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,target_group,value\n2024-08-03,A,-1\n")
    r = runner.invoke(app, ["dataset", "import", str(p), "--kind", "count"])
    assert r.exit_code == 1 and "negative" in r.output
    assert store.list_datasets() == []
    r = runner.invoke(app, ["dataset", "import", str(p)])
    assert r.exit_code == 2                           # --kind is required
