#!/usr/bin/env python3
"""Small JSON Schema validator for OAG runtime records.

This intentionally implements only the Draft-07 subset used by the OAG schemas
so the pack has no dependency on jsonschema for team release smoke checks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _type_ok(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _path(parent: str, key: str) -> str:
    if parent == "$":
        return f"$.{key}"
    return f"{parent}.{key}"


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def validate_value(schema: dict[str, Any], value: Any, path: str = "$") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(schema, dict):
        return issues

    if "const" in schema and value != schema["const"]:
        issues.append(_issue("CONST", path, f"expected {schema['const']!r}, got {value!r}"))
        return issues

    if "enum" in schema:
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            issues.append(_issue("ENUM", path, f"expected one of {enum!r}, got {value!r}"))
            return issues

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_type_ok(item, value) for item in expected_type if isinstance(item, str)):
            issues.append(_issue("TYPE", path, f"expected one of {expected_type!r}, got {type(value).__name__}"))
            return issues
    elif isinstance(expected_type, str):
        if not _type_ok(expected_type, value):
            issues.append(_issue("TYPE", path, f"expected {expected_type}, got {type(value).__name__}"))
            return issues

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            issues.append(_issue("MIN_LENGTH", path, f"expected at least {min_length} characters"))
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    issues.append(_issue("PATTERN", path, f"value does not match {pattern!r}"))
            except re.error as exc:
                issues.append(_issue("SCHEMA_PATTERN", path, f"invalid pattern {pattern!r}: {exc}"))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(_issue("MIN_ITEMS", path, f"expected at least {min_items} items"))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(validate_value(item_schema, item, f"{path}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for field in required:
                if isinstance(field, str) and field not in value:
                    issues.append(_issue("REQUIRED", _path(path, field), "required field is missing"))
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for field, field_schema in properties.items():
                if field in value and isinstance(field_schema, dict):
                    issues.extend(validate_value(field_schema, value[field], _path(path, field)))
        additional = schema.get("additionalProperties", True)
        if additional is False and isinstance(properties, dict):
            extra = sorted(set(value) - set(properties))
            for field in extra:
                issues.append(_issue("ADDITIONAL_PROPERTY", _path(path, field), "additional property is not allowed"))

    return issues


def validate_document(schema: dict[str, Any], document: Any) -> list[dict[str, str]]:
    return validate_value(schema, document, "$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_result(schema_path: Path, document_path: Path) -> dict[str, Any]:
    try:
        schema = load_json(schema_path)
        document = load_json(document_path)
        issues = validate_document(schema, document)
    except Exception as exc:
        issues = [_issue("LOAD_ERROR", "$", str(exc))]
    return {
        "schema_version": "oag_json_validation.v1",
        "status": "fail" if issues else "pass",
        "schema": str(schema_path),
        "document": str(document_path),
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OAG JSON document against an OAG schema.")
    parser.add_argument("--schema", required=True, help="JSON Schema file.")
    parser.add_argument("--document", help="JSON document file.")
    parser.add_argument("--json-file", help="Alias for --document.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result.")
    parser.add_argument("document_pos", nargs="?", help="Optional JSON document file.")
    args = parser.parse_args(argv)

    document = args.document or args.json_file or args.document_pos
    if not document:
        parser.error("--document or --json-file is required")
    result = build_result(Path(args.schema), Path(document))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print("PASS json schema validation")
    else:
        print("FAIL json schema validation", file=sys.stderr)
        for item in result["issues"]:
            print(f"- {item['code']} {item['path']}: {item['message']}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
