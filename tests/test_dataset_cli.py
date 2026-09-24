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
    assert "count (inferred from the values)" in r.output
    assert "format      grouped (comma-separated, UTF-8)" in r.output


def test_problems_are_printed_and_exit_1(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("date,target_group,value\n"
                 "2024-08-03,A,1\n2024-08-04,A,-2\n2024-08-24,A,3\n")
    r = runner.invoke(app, ["dataset", "validate", str(p), "--kind", "count"])
    assert r.exit_code == 1
    assert "3 problem(s), nothing stored" in r.output
    assert "different weekdays" in r.output and "negative" in r.output
    assert "Missing weeks" in r.output
    # grouped by kind, each with its rows
    out = r.output
    assert out.index("Dates:") < out.index("Values:") < out.index("Weeks:")
    assert "(row 3; e.g., 2024-08-04 (Sunday))" in out


def test_sunday_file_moves_by_itself_and_the_old_option_is_ignored(tmp_path):
    p = tmp_path / "sun.csv"
    p.write_text("date,target_group,value\n2024-07-28,A,1\n2024-08-04,A,2\n")
    for extra in ([], ["--sunday"]):
        r = runner.invoke(app, ["dataset", "validate", str(p), *extra])
        assert r.exit_code == 0, r.output
        assert "2024-08-03 to 2024-08-10" in r.output
        assert "note: Dates moved to week-ending Saturdays: +6 days" in r.output
    assert "--sunday" not in runner.invoke(app, ["dataset", "validate",
                                                 "--help"]).output
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
    assert "Values:" in r.output and "(row 2; e.g., -1)" in r.output


def test_import_infers_the_kind(store, tmp_path):
    p = tmp_path / "rates.csv"
    p.write_text("date;target_group;value\n2024-08-03;A;1,5\n"
                 "2024-08-10;A;2,25\n")
    r = runner.invoke(app, ["dataset", "import", str(p)])
    assert r.exit_code == 0, r.output
    assert "kind        rate (inferred from the values; --kind to change)" \
        in r.output
    assert "decimal commas" in r.output
    (d,) = store.list_datasets()
    assert d.kind == "rate" and d.name == "rates"


def test_column_mapping_on_the_command_line(store, tmp_path):
    p = tmp_path / "odd.csv"
    p.write_text("day,area,amount\n2024-08-03,A,1\n2024-08-10,A,2\n")
    r = runner.invoke(app, ["dataset", "validate", str(p)])
    assert r.exit_code == 1
    assert "Columns in the file: #1 day, #2 area, #3 amount" in r.output
    assert "--column ROLE=HEADER" in r.output
    assert "e.g. --column date=day." in r.output
    r = runner.invoke(app, ["dataset", "import", str(p), "--column",
                            "date=day", "--column", "group=#2",
                            "--column", "value=amount"])
    assert r.exit_code == 0, r.output
    (d,) = store.list_datasets()
    assert d.meta["columns"]["value"] == "amount"
    r = runner.invoke(app, ["dataset", "validate", str(p), "--column",
                            "when=day"])
    assert r.exit_code == 2 and "ROLE=HEADER" in r.output


@pytest.mark.parametrize("raw,says", [
    (b"date,target_group,value\n2024-01-06,A,1,234\n2024-01-13,A,987\n",
     "row(s) have more fields than the header"),
    # the second half in an ignored column, from a lazy writer
    (b"date,target_group,value,comment\n2024-01-06,A,1,234\n"
     b"2024-01-13,A,987\n", "look like a number split in two"),
    # a stray quote that took in every row below it
    (b'date,target_group,value,note\n2024-01-06,A,5,\n2024-01-13,A,6,"x\n'
     b'2024-01-20,A,7,\n2024-01-06,B,1,\n2024-01-13,B,2,\n',
     "open a quote"),
    ("date,target_group,value\n2024-01-06,Zürich,1\n".encode()
     + b"2024-01-13,Z\xfcrich,2\n", "The file mixes encodings"),
])
def test_what_would_read_wrong_is_refused_on_the_command_line(store, tmp_path,
                                                              raw, says):
    p = tmp_path / "bad.csv"
    p.write_bytes(raw)
    for cmd in ("validate", "import"):
        r = runner.invoke(app, ["dataset", cmd, str(p)])
        assert r.exit_code == 1 and says in r.output, r.output
    assert store.list_datasets() == []


def test_a_spreadsheet_unicode_text_file_imports(store, tmp_path):
    p = tmp_path / "unicode.txt"
    p.write_bytes("Week Ending\tRegion\tCases\n2024-08-03\tÅland\t3\n"
                  "2024-08-10\tÅland\t4\n".encode("utf-16"))
    r = runner.invoke(app, ["dataset", "validate", str(p)])
    assert r.exit_code == 0, r.output
    assert "(tab-separated, UTF-16)" in r.output
    assert runner.invoke(app, ["dataset", "import", str(p)]).exit_code == 0
    assert store.list_datasets()[0].groups == ["Åland"]
