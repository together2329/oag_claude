#!/usr/bin/env python3
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from oag_wavefront_core import JsonObject, load_json


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"[]", "null", "None"}:
        return [] if value == "[]" else None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return value.strip('"').strip("'")


def load_simple_yaml_template(path: Path) -> JsonObject:
    data = _load_with_optional_pyyaml(path)
    if data is not None:
        return data

    root: JsonObject = {}
    tasks: list[JsonObject] = []
    current: JsonObject | None = None
    list_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line == "tasks:":
            root["tasks"] = tasks
            current = None
            list_key = None
            continue
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            root[key.strip()] = parse_scalar(value)
            continue
        if indent == 2 and line.startswith("- "):
            current = {}
            tasks.append(current)
            item = line[2:].strip()
            if item and ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = parse_scalar(value)
            list_key = None
            continue
        if current is None:
            continue
        if indent == 4 and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            parsed = parse_scalar(value)
            if value.strip() == "":
                parsed = []
                list_key = key
            else:
                list_key = None
            current[key] = parsed
            continue
        if indent == 6 and line.startswith("- ") and list_key:
            current.setdefault(list_key, []).append(parse_scalar(line[2:]))
    if tasks:
        root["tasks"] = tasks
    return root


def _load_with_optional_pyyaml(path: Path) -> JsonObject | None:
    try:
        yaml = importlib.import_module("yaml")
    except ModuleNotFoundError:
        return None

    try:
        safe_load = getattr(yaml, "safe_load")
        yaml_error = getattr(yaml, "YAMLError")
    except AttributeError:
        return None
    try:
        data = safe_load(path.read_text(encoding="utf-8"))
    except yaml_error:
        return None
    if isinstance(data, dict):
        return data
    return None


def load_template(path: Path) -> JsonObject:
    if path.suffix.lower() == ".json":
        data = load_json(path)
    else:
        data = load_simple_yaml_template(path)
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ValueError(f"template must contain a tasks list: {path}")
    return data
