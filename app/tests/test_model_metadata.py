"""The hub model cards against the hub's own schema.

The FluSight hub validates a metadata pull request against
hub-config/model-metadata-schema.json. A card that fails there (the
Oracle SIHRS card's `methods` ran to 226 characters against the schema's
200 until 2026-09-23) is caught here instead, on every run and in CI,
which has no hub: the schema is vendored beside this file as a byte copy
(hub_model_metadata_schema.json, sha256 below), and checked against the
hub clone whenever one is present.

The validator here covers exactly the keywords the schema uses and fails
if the schema ever uses another, so a hub-side change cannot pass
silently; when jsonschema is installed the cards are validated by it as
well (Draft 2020-12).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "hub_model_metadata_schema.json"
SCHEMA_SHA256 = ("7fb27f66e7e2a573dffd63d2ad5eb7bac2874076e2f01fdd28d7b155cee"
                 "03fad")
CARDS = sorted((REPO / "model-metadata").glob("*.yml"))

#: every keyword the validator below implements
KNOWN = {"$schema", "title", "description", "type", "properties", "items",
         "required", "additionalProperties", "maxLength", "pattern", "enum",
         "format", "examples"}

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _keywords(node, out=None) -> set:
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            if k == "properties":
                for sub in v.values():
                    _keywords(sub, out)
            elif k == "items":
                _keywords(v, out)
    return out


def _validate(value, schema, path="card") -> list:
    """Errors of `value` against `schema`, for the keyword set above."""
    errs = []
    t = schema.get("type")
    if t and not isinstance(value, _TYPES[t]):
        return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: {len(value)} characters, the schema allows "
                        f"{schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} does not match "
                        f"{schema['pattern']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: required {k!r} missing")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errs.append(f"{path}: {k!r} is not allowed")
        for k, v in value.items():
            if k in props:
                errs += _validate(v, props[k], f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errs += _validate(v, schema["items"], f"{path}[{i}]")
    return errs


def test_the_vendored_schema_is_the_hubs_bytes():
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == SCHEMA_SHA256
    assert _keywords(_schema()) <= KNOWN, _keywords(_schema()) - KNOWN


def test_the_vendored_schema_equals_the_hub_clone_when_there_is_one():
    from flubnf.settings import HUB
    live = Path(HUB) / "hub-config" / "model-metadata-schema.json"
    if not live.is_file():
        pytest.skip("no FluSight hub clone on this machine")
    assert live.read_bytes() == SCHEMA.read_bytes(), (
        "the hub's model-metadata schema changed: re-vendor it, re-check "
        "both cards, and update SCHEMA_SHA256")


@pytest.mark.parametrize("card", CARDS, ids=[c.name for c in CARDS])
def test_every_card_validates_against_the_hub_schema(card):
    meta = yaml.safe_load(card.read_text(encoding="utf-8"))
    assert _validate(meta, _schema()) == []


@pytest.mark.parametrize("card", CARDS, ids=[c.name for c in CARDS])
def test_every_card_validates_with_jsonschema_when_installed(card):
    jsonschema = pytest.importorskip("jsonschema")
    meta = yaml.safe_load(card.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(_schema()).validate(meta)


def test_the_validator_catches_what_the_hub_would_refuse():
    """A validator that passes everything proves nothing."""
    meta = yaml.safe_load(
        (REPO / "model-metadata" / "NAU_PyBNF-OracleSIHRS.yml").read_text())
    long_methods = dict(meta, methods="x" * 201)
    assert any("201 characters" in e for e in _validate(long_methods,
                                                        _schema()))
    bad_abbr = dict(meta, model_abbr="Oracle-SIHRS")
    assert any("does not match" in e for e in _validate(bad_abbr, _schema()))
    extra = dict(meta, shipped=True)
    assert any("'shipped' is not allowed" in e
               for e in _validate(extra, _schema()))
    missing = {k: v for k, v in meta.items() if k != "methods_long"}
    assert any("'methods_long' missing" in e
               for e in _validate(missing, _schema()))


def test_the_oracle_card_says_what_the_member_is():
    from app.core import oracle_text as ot
    meta = yaml.safe_load(
        (REPO / "model-metadata" / "NAU_PyBNF-OracleSIHRS.yml").read_text())
    assert meta["model_name"] == "Oracle SIHRS"
    assert len(meta["methods"]) <= 200
    long = meta["methods_long"]
    # the one marked place for the donor bank's streams, verbatim
    assert ot.BANK_TEXT["card"] in long
    assert ot.PREREG_SHA256 in long
    for needle in ("SIHRS compartment model", "particle filter",
                   "geometric mean", "same calendar week",
                   "own state", "Uncertainty:", "Spatial correlation:",
                   "frozen-specification replication",
                   "2026-27 season is its prospective test",
                   ot.fmt(ot.RECORD["both"]["filter"]) + " to "
                   + ot.fmt(ot.RECORD["both"]["oracle"]),
                   ot.cells(ot.RECORD["both"]["cells"]) + " cells"):
        assert needle in long, needle
    # plain ASCII, no dashes the repository does not use
    assert all(ord(ch) < 128 for ch in long + meta["methods"])
