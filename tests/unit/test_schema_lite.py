"""The stdlib schema checker against each keyword the contract uses (TASK-25, TEST-46 tooling)."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_lite import SchemaError, check  # type: ignore[import-not-found]

ROOT_SCHEMA = {
    "components": {
        "schemas": {
            "Id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 4,
                "pattern": "^[a-z]+$",
            },
        }
    }
}


@pytest.mark.parametrize(
    ("value", "schema", "valid"),
    [
        ("ab", {"type": "string"}, True),
        (3, {"type": "integer"}, True),
        (True, {"type": "integer"}, False),  # a bool is not an integer
        (1.5, {"type": "number"}, True),
        (None, {"type": ["string", "null"]}, True),
        ({"a": 1}, {"type": "object", "required": ["a", "b"]}, False),
        ({"a": 1}, {"type": "object", "properties": {"a": {"type": "string"}}}, False),
        (
            {"a": 1, "x": 2},
            {"type": "object", "properties": {"a": {}}, "additionalProperties": False},
            False,
        ),
        ({"a": 1, "x": 2}, {"type": "object", "properties": {"a": {}}}, True),
        (
            {"a": 1, "x": "no"},
            {"type": "object", "additionalProperties": {"type": "integer"}},
            False,
        ),
        ("c", {"enum": ["a", "b"]}, False),
        ("a", {"const": "a"}, True),
        ("b", {"const": "a"}, False),
        ("abcde", {"type": "string", "maxLength": 4}, False),
        ("A", {"type": "string", "pattern": "^[a-z]+$"}, False),
        (0, {"type": "integer", "minimum": 1}, False),
        (201, {"type": "integer", "maximum": 200}, False),
        ([1, 2], {"type": "array", "maxItems": 1}, False),
        ([1, "x"], {"type": "array", "items": {"type": "integer"}}, False),
        ("x", {"$ref": "#/components/schemas/Id"}, True),
        ("ABC", {"$ref": "#/components/schemas/Id"}, False),
        ({"a": 1}, {"allOf": [{"type": "object"}, {"required": ["b"]}]}, False),
        (1, {"anyOf": [{"type": "string"}, {"type": "integer"}]}, True),
        ("x", {"anyOf": [{"type": "integer"}, {"type": "boolean"}]}, False),
        (
            {"kind": "card"},
            {
                "if": {"properties": {"kind": {"const": "card"}}},
                "then": {"required": ["pan"]},
            },
            False,
        ),
        (
            {"kind": "ach"},
            {
                "if": {"properties": {"kind": {"const": "card"}}},
                "then": {"required": ["pan"]},
            },
            True,
        ),
        ({"a": 1}, {"dependentRequired": {"a": ["b"]}}, False),
        ({"a": 1, "b": 2}, {"dependentRequired": {"a": ["b"]}}, True),
    ],
)
def test_each_keyword_accepts_and_refuses_as_the_contract_states(value, schema, valid):
    errors = check(value, schema, ROOT_SCHEMA)
    assert (errors == []) is valid, errors


def test_an_unsupported_keyword_is_an_error_not_a_pass():
    with pytest.raises(SchemaError):
        check(1, {"type": "integer", "not": {"const": 2}}, ROOT_SCHEMA)


def test_a_broken_reference_is_an_error():
    with pytest.raises(SchemaError):
        check("x", {"$ref": "#/components/schemas/Missing"}, ROOT_SCHEMA)
