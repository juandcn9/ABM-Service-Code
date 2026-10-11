"""A standard-library JSON Schema checker for the keywords used by contracts/openapi.yaml (TASK-25, TEST-46).

Supported: $ref (local), type, properties, required, additionalProperties, enum, const, items,
minItems, maxItems, minLength, maxLength, pattern, minimum, maximum, allOf, anyOf, if/then,
dependentRequired. Any other keyword is an error, so an unsupported contract construct cannot be
silently skipped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SUPPORTED = {
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "const",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "allOf",
    "anyOf",
    "if",
    "then",
    "dependentRequired",
    "description",
    "title",
    "default",
    "format",
    "example",
    "examples",
    "x-error-codes",
    "$schema",
}
_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: type(v) is int,
    "number": lambda v: type(v) in (int, float),
    "boolean": lambda v: type(v) is bool,
    "object": lambda v: isinstance(v, Mapping),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


class SchemaError(Exception):
    """A keyword the checker does not support, or a broken reference."""


def _resolve(root: Mapping[str, Any], ref: str) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported reference {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, Mapping) or part not in node:
            raise SchemaError(f"broken reference {ref}")
        node = node[part]
    return node


def check(
    value: Any, schema: Mapping[str, Any], root: Mapping[str, Any], path: str = "$"
) -> list[str]:
    """All violations of `schema` by `value`, as 'path: reason' strings. Empty means valid."""
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported keyword(s) {sorted(unknown)} at {path}")
    errors: list[str] = []
    if "$ref" in schema:
        return check(value, _resolve(root, schema["$ref"]), root, path)
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[kind](value) for kind in kinds):
            return [f"{path}: expected {'/'.join(kinds)}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: not one of the allowed values")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path}: does not match the pattern")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors += check(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(value, Mapping):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required {name}")
        for name, sub in schema.get("properties", {}).items():
            if name in value:
                errors += check(value[name], sub, root, f"{path}.{name}")
        extra_rule = schema.get("additionalProperties", True)
        for name in value:
            if name in schema.get("properties", {}):
                continue
            if extra_rule is False:
                errors.append(f"{path}: unexpected property {name}")
            elif isinstance(extra_rule, Mapping):
                errors += check(value[name], extra_rule, root, f"{path}.{name}")
        for name, needed in schema.get("dependentRequired", {}).items():
            if name in value:
                for other in needed:
                    if other not in value:
                        errors.append(f"{path}: {name} requires {other}")
    for sub in schema.get("allOf", []):
        errors += check(value, sub, root, path)
    if "anyOf" in schema and not any(
        not check(value, sub, root, path) for sub in schema["anyOf"]
    ):
        errors.append(f"{path}: matches none of the anyOf branches")
    if (
        "if" in schema
        and not check(value, schema["if"], root, path)
        and "then" in schema
    ):
        errors += check(value, schema["then"], root, path)
    return errors
