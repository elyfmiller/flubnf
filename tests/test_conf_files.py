"""Tests for flubnf.conf_files."""

from __future__ import annotations

import pytest

from flubnf import conf_files
from flubnf.conf_files import (
    materialize_conf_from_template, read_uniform_vars,
    set_starting_params, update_keys, update_uniform_vars,
)


class TestMaterialize:
    def test_substitutes_paths_and_state(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        text = path.read_text()
        # State substitution.
        assert "Arizona.bngl" in text
        assert "Arizona_flu.exp" in text
        assert "Alabama" not in text
        # Path substitution.
        assert str(tmp_workspace.bngl_dir) in text
        assert str(tmp_workspace.exp_dir) in text
        assert str(tmp_workspace.results_dir) in text
        # No leftover tokens.
        assert "{{" not in text

    def test_idempotent(self, tmp_workspace, config):
        p1 = materialize_conf_from_template("Arizona", tmp_workspace, config)
        body1 = p1.read_text()
        p2 = materialize_conf_from_template("Arizona", tmp_workspace, config)
        assert p1 == p2
        assert p2.read_text() == body1


class TestUniformVars:
    def test_read(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        params = read_uniform_vars(path)
        names = [p.name for p in params]
        assert "b0__FREE" in names
        assert "gamma__FREE" in names

    def test_update_existing(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        update_uniform_vars(path, {"b0__FREE": (0.03, 0.07)})
        params = {p.name: (p.low, p.high) for p in read_uniform_vars(path)}
        assert params["b0__FREE"] == (0.03, 0.07)
        # Other params untouched.
        assert "gamma__FREE" in params

    def test_append_new(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        update_uniform_vars(path, {"b1__FREE": (0.05, 0.10), "t1__FREE": (3, 10)})
        params = {p.name: (p.low, p.high) for p in read_uniform_vars(path)}
        assert params["b1__FREE"] == (0.05, 0.10)
        assert params["t1__FREE"] == (3.0, 10.0)
        # Original params still present.
        assert "b0__FREE" in params

    def test_new_lines_appear_inside_uniform_block(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        update_uniform_vars(path, {"b1__FREE": (0.1, 0.2)})
        lines = path.read_text().splitlines()
        uniform_idx = [i for i, ln in enumerate(lines)
                       if ln.startswith("uniform_var")]
        # Should be a contiguous block.
        assert uniform_idx == list(range(uniform_idx[0], uniform_idx[-1] + 1))


class TestUpdateKeys:
    def test_replaces_existing(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        update_keys(path, {"fit_type": "am", "max_iterations": 30000})
        text = path.read_text()
        assert "fit_type = am" in text
        assert "max_iterations = 30000" in text

    def test_appends_unknown(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        update_keys(path, {"smoothing": 0.5})
        assert "smoothing = 0.5" in path.read_text()


class TestStartingParams:
    def test_appends_when_missing(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        set_starting_params(path, [0.5, 1.0, 2.0])
        text = path.read_text()
        assert "starting_params = 0.5 1 2" in text

    def test_replaces_existing(self, tmp_workspace, config):
        path = materialize_conf_from_template("Arizona", tmp_workspace, config)
        set_starting_params(path, [0.5, 1.0, 2.0])
        set_starting_params(path, [9, 8, 7])
        text = path.read_text()
        assert text.count("starting_params") == 1
        assert "starting_params = 9 8 7" in text
