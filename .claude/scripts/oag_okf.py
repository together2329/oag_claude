#!/usr/bin/env python3
"""Generate and consume OKF views for OAG knowledge.

OAG remains the canonical verification state. OKF is a generated, human- and
agent-readable interchange view over that state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import oag_cli  # noqa: E402

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML is expected in normal OAG use.
    yaml = None  # type: ignore


SCHEMA_VERSION = "oag_okf_bundle.v1"
OKF_VERSION = "0.1"
RESERVED_NAMES = {"index.md", "log.md"}
CANONICAL_IMPORT_GUARD_PATHS = [
    "req/locked_truth.md",
    "req/requirements.yaml",
    "req/contracts.yaml",
    "req/evidence_plan.yaml",
    "ontology/ip.yaml",
    "ontology/requirements.yaml",
    "ontology/obligations.yaml",
    "ontology/contracts.yaml",
    "ontology/design_rules.yaml",
    "ontology/structure.yaml",
    "ontology/decomposition.yaml",
    "ontology/policies.yaml",
    "ontology/protection.yaml",
    "ontology/stages.yaml",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(value: str, fallback: str = "concept") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return text[:96] or fallback


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML is required to read OAG YAML files")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_source_hashes(ip: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in CANONICAL_IMPORT_GUARD_PATHS:
        path = ip / rel
        if path.is_file():
            hashes[rel] = _sha256(path)
    return hashes


def _load_record(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        data = _read_json(path)
    else:
        data = _read_yaml(path)
    return data if isinstance(data, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _items(path: Path, key: str) -> list[dict[str, Any]]:
    data = _read_yaml(path)
    items = data.get(key) if isinstance(data, dict) else []
    return [item for item in _as_list(items) if isinstance(item, dict)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sentence(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", _text(value))
    return text[: limit - 3].rstrip() + "..." if len(text) > limit else text


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_quote(str(item))}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {_yaml_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _write_concept(path: Path, meta: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not meta.get("type"):
        raise ValueError(f"OKF concept missing type: {path}")
    path.write_text(_frontmatter(meta) + body.rstrip() + "\n", encoding="utf-8")


def _rel_link(target: str, text: str | None = None) -> str:
    return f"[{text or target}]({target})"


def _id_link(kind: str, item_id: str) -> str:
    if not item_id:
        return ""
    return _rel_link(f"/{kind}/{_slug(item_id)}.md", item_id)


def _is_obsidian(profile: str) -> bool:
    return profile == "obsidian"


def _obsidian_wiki_link(kind: str, item_id: str, text: str | None = None) -> str:
    if not item_id:
        return ""
    return f"[[{kind}/{_slug(item_id)}|{text or item_id}]]"


def _profiled_id_link(kind: str, item_id: str, profile: str) -> str:
    link = _id_link(kind, item_id)
    if _is_obsidian(profile) and link:
        return f"{link} / {_obsidian_wiki_link(kind, item_id)}"
    return link


def _module_source_file(module: dict[str, Any]) -> str:
    source = module.get("source") if isinstance(module.get("source"), dict) else {}
    return _text(module.get("file") or module.get("path") or source.get("file"))


def _common_meta(*, concept_type: str, title: str, description: str, resource: str, tags: list[str]) -> dict[str, Any]:
    return {
        "type": concept_type,
        "title": title,
        "description": description,
        "resource": resource,
        "tags": tags,
        "timestamp": _now(),
        "producer": "ip-dev-agent",
        "okf_version": OKF_VERSION,
    }


def _with_obsidian_meta(
    meta: dict[str, Any],
    *,
    profile: str,
    ip_name: str,
    oag_kind: str,
    item_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _is_obsidian(profile):
        return meta
    tags = [str(tag) for tag in _as_list(meta.get("tags"))]
    tags.extend(["oag", f"oag/{oag_kind}", f"ip/{_slug(ip_name)}"])
    title = _text(meta.get("title"))
    aliases = []
    for alias in [item_id, title]:
        if alias and alias not in aliases:
            aliases.append(alias)
    meta.update(
        {
            "tags": list(dict.fromkeys(tags)),
            "aliases": aliases,
            "okf_profile": "obsidian",
            "ip": ip_name,
            "oag_kind": oag_kind,
            "oag_id": item_id or title,
        }
    )
    if extra:
        meta.update({key: value for key, value in extra.items() if value is not None})
    return meta


def _git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _export_root_index(out: Path, ip: Path, counts: dict[str, int], profile: str) -> None:
    body = [
        "# OAG OKF Bundle",
        "",
        f"- IP: `{ip.name}`",
        f"- OAG view schema: `{SCHEMA_VERSION}`",
        f"- OKF target version: `{OKF_VERSION}`",
        f"- Export profile: `{profile}`",
        f"- Generated at: `{_now()}`",
        f"- Git HEAD: `{_git_head(ip.parent)}`",
        "",
        "## Concepts",
        "",
    ]
    for label, rel, count in [
        ("Requirements", "requirements/", counts.get("requirements", 0)),
        ("Obligations", "obligations/", counts.get("obligations", 0)),
        ("Contracts", "contracts/", counts.get("contracts", 0)),
        ("Knowledge Records", "records/", counts.get("records", 0)),
        ("Validations", "validations/", counts.get("validations", 0)),
        ("Design Modules", "design/modules/", counts.get("modules", 0)),
    ]:
        body.append(f"* [{label}]({rel}) - {count} concepts")
    if _is_obsidian(profile):
        body.extend(
            [
                "",
                "## Obsidian",
                "",
                "* [[OAG Knowledge.base|OAG Knowledge Base views]]",
                "* Embed all views with `![[OAG Knowledge.base]]`",
            ]
        )
    (out / "index.md").write_text(
        _frontmatter(
            {
                "okf_version": OKF_VERSION,
                "title": f"{ip.name} OAG OKF Bundle",
                "description": "Generated OKF view over canonical OAG DB state.",
                "profile": profile,
                "timestamp": _now(),
            }
        )
        + "\n".join(body)
        + "\n",
        encoding="utf-8",
    )


def _write_dir_index(out_dir: Path, title: str, entries: list[tuple[str, str, str]]) -> None:
    lines = [f"# {title}", ""]
    for label, href, desc in sorted(entries, key=lambda item: item[0]):
        suffix = f" - {desc}" if desc else ""
        lines.append(f"* [{label}]({href}){suffix}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _export_rocev_objects(ip: Path, out: Path, profile: str) -> dict[str, int]:
    reqs = _items(ip / "ontology" / "requirements.yaml", "requirements")
    obligations = _items(ip / "ontology" / "obligations.yaml", "obligations")
    contracts = _items(ip / "ontology" / "contracts.yaml", "contracts")
    counts = {"requirements": len(reqs), "obligations": len(obligations), "contracts": len(contracts)}

    req_entries: list[tuple[str, str, str]] = []
    for req in reqs:
        req_id = _text(req.get("id"))
        title = req_id or "Requirement"
        body = [
            f"# {title}",
            "",
            _text(req.get("text")),
            "",
            "## OAG Metadata",
            "",
            f"- Status: `{_text(req.get('status'))}`",
            f"- Source: `{_text(req.get('source') or 'ontology/requirements.yaml')}`",
        ]
        _write_concept(
            out / "requirements" / f"{_slug(req_id)}.md",
            _with_obsidian_meta(
                _common_meta(
                    concept_type="OAG Requirement",
                    title=title,
                    description=_sentence(req.get("text") or req_id),
                    resource=f"oag://ip/{ip.name}/requirement/{req_id}",
                    tags=["oag", ip.name, "requirement"],
                ),
                profile=profile,
                ip_name=ip.name,
                oag_kind="requirement",
                item_id=req_id,
                extra={"requirement_id": req_id, "status": _text(req.get("status"))},
            ),
            "\n".join(body),
        )
        req_entries.append((title, f"{_slug(req_id)}.md", _sentence(req.get("text"))))

    obl_entries: list[tuple[str, str, str]] = []
    for obligation in obligations:
        obl_id = _text(obligation.get("id"))
        contracts_value = [_text(item) for item in _as_list(obligation.get("contracts"))]
        body = [
            f"# {obl_id or 'Obligation'}",
            "",
            _text(obligation.get("text")),
            "",
            "## Contracts",
            "",
        ]
        body.extend(f"- {_profiled_id_link('contracts', contract, profile)}" for contract in contracts_value)
        _write_concept(
            out / "obligations" / f"{_slug(obl_id)}.md",
            _with_obsidian_meta(
                _common_meta(
                    concept_type="OAG Obligation",
                    title=obl_id or "Obligation",
                    description=_sentence(obligation.get("text") or obl_id),
                    resource=f"oag://ip/{ip.name}/obligation/{obl_id}",
                    tags=["oag", ip.name, "obligation"],
                ),
                profile=profile,
                ip_name=ip.name,
                oag_kind="obligation",
                item_id=obl_id,
                extra={"obligation_id": obl_id, "status": _text(obligation.get("status"))},
            ),
            "\n".join(body),
        )
        obl_entries.append((obl_id, f"{_slug(obl_id)}.md", _sentence(obligation.get("text"))))

    contract_entries: list[tuple[str, str, str]] = []
    for contract in contracts:
        contract_id = _text(contract.get("id"))
        body = [
            f"# {contract_id or 'Contract'}",
            "",
            "## Method",
            "",
            _text(contract.get("method")),
            "",
            "## Pass Condition",
            "",
            _text(contract.get("pass_condition")),
            "",
            "## Evidence Kinds",
            "",
        ]
        body.extend(f"- `{_text(kind)}`" for kind in _as_list(contract.get("evidence_kinds")))
        _write_concept(
            out / "contracts" / f"{_slug(contract_id)}.md",
            _with_obsidian_meta(
                _common_meta(
                    concept_type="OAG Contract",
                    title=contract_id or "Contract",
                    description=_sentence(contract.get("pass_condition") or contract_id),
                    resource=f"oag://ip/{ip.name}/contract/{contract_id}",
                    tags=["oag", ip.name, "contract"],
                ),
                profile=profile,
                ip_name=ip.name,
                oag_kind="contract",
                item_id=contract_id,
                extra={"contract_id": contract_id},
            ),
            "\n".join(body),
        )
        contract_entries.append((contract_id, f"{_slug(contract_id)}.md", _sentence(contract.get("pass_condition"))))

    _write_dir_index(out / "requirements", "Requirements", req_entries)
    _write_dir_index(out / "obligations", "Obligations", obl_entries)
    _write_dir_index(out / "contracts", "Contracts", contract_entries)
    return counts


def _available_rocev_ids(ip: Path) -> dict[str, set[str]]:
    return {
        "requirements": {_text(item.get("id")) for item in _items(ip / "ontology" / "requirements.yaml", "requirements")},
        "obligations": {_text(item.get("id")) for item in _items(ip / "ontology" / "obligations.yaml", "obligations")},
        "contracts": {_text(item.get("id")) for item in _items(ip / "ontology" / "contracts.yaml", "contracts")},
    }


def _record_rocev_links(record: dict[str, Any], available: dict[str, set[str]], profile: str) -> list[str]:
    rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
    links: list[str] = []
    for key, folder in [("requirement", "requirements"), ("obligation", "obligations"), ("contract", "contracts")]:
        value = rocev.get(key) if isinstance(rocev.get(key), dict) else {}
        item_id = _text(value.get("id"))
        if item_id:
            if item_id in available.get(folder, set()):
                links.append(f"- {key}: {_profiled_id_link(folder, item_id, profile)}")
            else:
                links.append(f"- {key}: `{item_id}` (not in current exported ontology)")
    return links


def _export_records(ip: Path, out: Path, profile: str) -> int:
    entries: list[tuple[str, str, str]] = []
    records_dir = ip / "knowledge" / "records"
    available = _available_rocev_ids(ip)
    for path in sorted(records_dir.glob("IKL_*")) if records_dir.is_dir() else []:
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        record = _load_record(path)
        record_id = _text(record.get("id") or path.stem)
        title = _text(record.get("claim") or record_id)
        validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
        evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
        actor = record.get("actor") if isinstance(record.get("actor"), dict) else {}
        body = [
            f"# {title}",
            "",
            _text(record.get("summary")),
            "",
            "## ROCEV Links",
            "",
            *(_record_rocev_links(record, available, profile) or ["- none"]),
            "",
            "## Validation",
            "",
            f"- Status: `{_text(validation.get('status'))}`",
            f"- Verdict: `{_text(validation.get('verdict'))}`",
            f"- Rationale: {_text(validation.get('rationale'))}",
            "",
            "## Evidence Files",
            "",
        ]
        body.extend(f"- `{_text(item)}`" for item in _as_list(evidence.get("files")))
        file_hashes = [item for item in _as_list(evidence.get("file_hashes")) if isinstance(item, dict)]
        if file_hashes:
            body.extend(["", "## Evidence Hashes", ""])
            for item in file_hashes:
                body.append(f"- `{_text(item.get('path'))}` sha256=`{_text(item.get('sha256'))}`")
        body.extend(["", "## Actor", ""])
        body.extend(f"- {key}: `{_text(actor.get(key))}`" for key in ["kind", "id", "surface"])
        _write_concept(
            out / "records" / f"{_slug(record_id)}.md",
            _with_obsidian_meta(
                _common_meta(
                    concept_type=f"OAG {record.get('type') or 'Record'}",
                    title=title,
                    description=_sentence(record.get("summary") or title),
                    resource=f"oag://ip/{ip.name}/record/{record_id}",
                    tags=["oag", ip.name, "record", _text(record.get("type") or "log")],
                ),
                profile=profile,
                ip_name=ip.name,
                oag_kind="record",
                item_id=record_id,
                extra={
                    "record_id": record_id,
                    "record_type": _text(record.get("type") or "log"),
                    "validation_status": _text(validation.get("status")),
                    "verdict": _text(validation.get("verdict")),
                },
            ),
            "\n".join(body),
        )
        entries.append((record_id, f"{_slug(record_id)}.md", _sentence(record.get("summary") or title)))
    _write_dir_index(out / "records", "Knowledge Records", entries)
    return len(entries)


def _export_validations(ip: Path, out: Path, profile: str) -> int:
    entries: list[tuple[str, str, str]] = []
    validations_dir = ip / "ontology" / "validations"
    for path in sorted(validations_dir.glob("*.json")) if validations_dir.is_dir() else []:
        data = _read_json(path)
        validation_id = _text(data.get("id") or path.stem)
        title = validation_id
        decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
        evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
        body = [
            f"# {title}",
            "",
            "## Decision",
            "",
            f"- Action: `{_text(data.get('action') or decision.get('claim'))}`",
            f"- Allowed: `{_text(data.get('allowed'))}`",
            f"- Reason: `{_text(data.get('reason'))}`",
            f"- Verdict: `{_text(decision.get('verdict'))}`",
            f"- Rationale: {_text(decision.get('rationale'))}",
            "",
            "## Evidence",
            "",
            f"- Check OK: `{_text(evidence.get('check_ok'))}`",
            f"- Inspect validation: `{_text(evidence.get('inspect_validation'))}`",
        ]
        _write_concept(
            out / "validations" / f"{_slug(validation_id)}.md",
            _with_obsidian_meta(
                _common_meta(
                    concept_type="OAG Validation",
                    title=title,
                    description=_sentence(decision.get("rationale") or data.get("reason") or title),
                    resource=f"oag://ip/{ip.name}/validation/{validation_id}",
                    tags=["oag", ip.name, "validation"],
                ),
                profile=profile,
                ip_name=ip.name,
                oag_kind="validation",
                item_id=validation_id,
                extra={
                    "validation_id": validation_id,
                    "allowed": _text(data.get("allowed")),
                    "action": _text(data.get("action") or decision.get("claim")),
                    "verdict": _text(decision.get("verdict")),
                },
            ),
            "\n".join(body),
        )
        entries.append((validation_id, f"{_slug(validation_id)}.md", _sentence(decision.get("rationale") or data.get("reason"))))
    _write_dir_index(out / "validations", "Validations", entries)
    return len(entries)


def _export_design_modules(ip: Path, out: Path, profile: str) -> int:
    facts = _read_json(ip / "ontology" / "generated" / "design_facts_graph.json")
    modules = facts.get("modules") if isinstance(facts, dict) else []
    if not isinstance(modules, list):
        modules = []
    module_names = {_text(module.get("name") or module.get("module")) for module in modules if isinstance(module, dict)}
    entries: list[tuple[str, str, str]] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        name = _text(module.get("name") or module.get("module"))
        if not name:
            continue
        source_file = _module_source_file(module)
        ports = module.get("ports") if isinstance(module.get("ports"), list) else []
        params = module.get("parameters") if isinstance(module.get("parameters"), list) else []
        instances = module.get("instances") if isinstance(module.get("instances"), list) else []
        body = [
            f"# {name}",
            "",
            f"- Source: `{source_file}`",
            "",
            "## Ports",
            "",
        ]
        body.extend(f"- `{_text(port.get('name') if isinstance(port, dict) else port)}`" for port in ports)
        body.extend(["", "## Parameters", ""])
        body.extend(f"- `{_text(param.get('name') if isinstance(param, dict) else param)}`" for param in params)
        body.extend(["", "## Instances", ""])
        for inst in instances:
            if isinstance(inst, dict):
                inst_name = _text(inst.get("name"))
                inst_module = _text(inst.get("module"))
                target = _profiled_id_link("design/modules", inst_module, profile) if inst_module in module_names else ""
                suffix = f" -> {target}" if target else ""
                body.append(f"- `{inst_name}`{suffix}")
            else:
                body.append(f"- `{_text(inst)}`")
        meta = _with_obsidian_meta(
            _common_meta(
                concept_type="OAG RTL Module",
                title=name,
                description=f"Extracted RTL design facts for module {name}.",
                resource=f"oag://ip/{ip.name}/module/{name}",
                tags=["oag", ip.name, "design", "rtl", "module"],
            ),
            profile=profile,
            ip_name=ip.name,
            oag_kind="module",
            item_id=name,
            extra={"module_name": name},
        )
        meta["source_file"] = source_file
        _write_concept(
            out / "design" / "modules" / f"{_slug(name)}.md",
            meta,
            "\n".join(body),
        )
        entries.append((name, f"{_slug(name)}.md", "Extracted RTL module facts."))
    _write_dir_index(out / "design" / "modules", "Design Modules", entries)
    _write_dir_index(out / "design", "Design", [("Modules", "modules/", f"{len(entries)} extracted module concepts")])
    return len(entries)


def _write_obsidian_base(out: Path) -> None:
    base = """filters:
  or:
    - 'oag_kind == "requirement"'
    - 'oag_kind == "obligation"'
    - 'oag_kind == "contract"'
    - 'oag_kind == "record"'
    - 'oag_kind == "validation"'
    - 'oag_kind == "module"'

formulas:
  concept: 'oag_kind'
  source: 'if(source_file, source_file, "")'

properties:
  ip:
    displayName: "IP"
  oag_kind:
    displayName: "Kind"
  oag_id:
    displayName: "OAG ID"
  requirement_id:
    displayName: "Requirement"
  obligation_id:
    displayName: "Obligation"
  contract_id:
    displayName: "Contract"
  record_id:
    displayName: "Record"
  record_type:
    displayName: "Record Type"
  validation_id:
    displayName: "Validation"
  module_name:
    displayName: "Module"
  source_file:
    displayName: "RTL Source"
  status:
    displayName: "Status"
  verdict:
    displayName: "Verdict"
  validation_status:
    displayName: "Validation Status"
  action:
    displayName: "Action"
  allowed:
    displayName: "Allowed"
  formula.concept:
    displayName: "Concept"
  formula.source:
    displayName: "Source"

views:
  - type: table
    name: "Requirements"
    filters: 'oag_kind == "requirement"'
    order:
      - file.name
      - requirement_id
      - status
      - ip
      - file.links
  - type: table
    name: "Obligations"
    filters: 'oag_kind == "obligation"'
    order:
      - file.name
      - obligation_id
      - status
      - ip
      - file.links
  - type: table
    name: "Contracts"
    filters: 'oag_kind == "contract"'
    order:
      - file.name
      - contract_id
      - ip
      - file.links
  - type: table
    name: "Records"
    filters: 'oag_kind == "record"'
    order:
      - file.name
      - record_id
      - record_type
      - validation_status
      - verdict
      - file.links
  - type: table
    name: "Validations"
    filters: 'oag_kind == "validation"'
    order:
      - file.name
      - validation_id
      - action
      - allowed
      - verdict
      - file.links
  - type: table
    name: "RTL Modules"
    filters: 'oag_kind == "module"'
    order:
      - file.name
      - module_name
      - source_file
      - ip
      - file.links
  - type: cards
    name: "Knowledge Cards"
    order:
      - file.name
      - formula.concept
      - file.links
"""
    (out / "OAG Knowledge.base").write_text(base, encoding="utf-8")


def cmd_export(args: argparse.Namespace) -> int:
    ip = Path(args.ip_dir).resolve()
    if not ip.is_dir():
        raise SystemExit(f"IP directory not found: {ip}")
    profile = args.profile
    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            raise SystemExit(f"output exists; pass --force to replace: {out}")
        if out.is_dir():
            shutil.rmtree(out)
        else:
            out.unlink()
    out.mkdir(parents=True, exist_ok=True)
    counts = _export_rocev_objects(ip, out, profile)
    counts["records"] = _export_records(ip, out, profile)
    counts["validations"] = _export_validations(ip, out, profile)
    counts["modules"] = _export_design_modules(ip, out, profile)
    if _is_obsidian(profile):
        _write_obsidian_base(out)
    _export_root_index(out, ip, counts, profile)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "okf_version": OKF_VERSION,
        "profile": profile,
        "ip": ip.name,
        "created_at": _now(),
        "git_head": _git_head(ip.parent),
        "counts": counts,
        "canonical_state": {
            "req": "req",
            "ontology": "ontology",
            "knowledge": "knowledge",
        },
        "note": "Generated OKF view only; OAG DB remains canonical.",
    }
    (out / "oag_okf_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive_path = ""
    if args.archive:
        archive = Path(args.archive).resolve()
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(out, arcname=out.name)
        archive_path = str(archive)
    print(json.dumps({"status": "pass", "out": str(out), "archive": archive_path, "profile": profile, "counts": counts}, indent=2))
    return 0


def _split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing frontmatter: {path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"unterminated frontmatter: {path}")
    raw = text[4:end]
    body = text[end + 5 :]
    if yaml is None:
        meta: dict[str, Any] = {}
        for line in raw.splitlines():
            if ":" in line and not line.startswith(" "):
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip().strip('"')
    else:
        loaded = yaml.safe_load(raw) or {}
        meta = loaded if isinstance(loaded, dict) else {}
    return meta, body


def _iter_markdown_links(text: str) -> list[str]:
    return re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)


def _iter_wiki_links(text: str) -> list[str]:
    return re.findall(r"\[\[([^]\n]+)\]\]", text)


def _link_target_exists(root: Path, source: Path, target: str) -> bool:
    clean = target.split("#", 1)[0].strip()
    if not clean:
        return True
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean):
        return True
    if clean.startswith("/"):
        path = root / clean.lstrip("/")
    else:
        path = source.parent / clean
    if path.is_dir():
        return (path / "index.md").is_file()
    return path.is_file()


def _wiki_target_exists(root: Path, source: Path, target: str) -> bool:
    clean = target.split("|", 1)[0].split("#", 1)[0].strip()
    if not clean:
        return True
    candidates = [
        root / clean,
        root / f"{clean}.md",
        source.parent / clean,
        source.parent / f"{clean}.md",
    ]
    return any(path.is_file() for path in candidates)


def _folder_concept_count(root: Path, rel: str) -> int:
    folder = root / rel
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.glob("*.md") if path.name not in RESERVED_NAMES)


def _manifest_count_issues(root: Path) -> list[str]:
    manifest_path = root / "oag_okf_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return [f"oag_okf_manifest.json: {exc}"]
    issues: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append("oag_okf_manifest.json: schema_version mismatch")
    if manifest.get("okf_version") != OKF_VERSION:
        issues.append("oag_okf_manifest.json: okf_version mismatch")
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    expected = {
        "requirements": _folder_concept_count(root, "requirements"),
        "obligations": _folder_concept_count(root, "obligations"),
        "contracts": _folder_concept_count(root, "contracts"),
        "records": _folder_concept_count(root, "records"),
        "validations": _folder_concept_count(root, "validations"),
        "modules": _folder_concept_count(root, "design/modules"),
    }
    for key, actual in expected.items():
        if counts.get(key) != actual:
            issues.append(f"oag_okf_manifest.json: count mismatch for {key}: manifest={counts.get(key)} actual={actual}")
    return issues


def _validate_bundle(root: Path) -> dict[str, Any]:
    issues: list[str] = []
    if not root.is_dir():
        return {
            "schema_version": "oag_okf_validation.v1",
            "ok": False,
            "concept_count": 0,
            "issues": [f"bundle directory not found: {root}"],
        }
    manifest: dict[str, Any] = {}
    manifest_path = root / "oag_okf_manifest.json"
    if manifest_path.is_file():
        try:
            loaded = _read_json(manifest_path)
            manifest = loaded if isinstance(loaded, dict) else {}
        except Exception as exc:
            issues.append(f"oag_okf_manifest.json: {exc}")
    profile = _text(manifest.get("profile") or "okf")
    if profile not in {"okf", "obsidian"}:
        issues.append(f"oag_okf_manifest.json: unsupported profile: {profile}")
    issues.extend(_manifest_count_issues(root))
    if profile == "obsidian":
        base_path = root / "OAG Knowledge.base"
        if not base_path.is_file():
            issues.append("OAG Knowledge.base: missing Obsidian Bases file")
        elif yaml is None:
            issues.append("OAG Knowledge.base: PyYAML is required to validate Obsidian Bases YAML")
        else:
            try:
                base_data = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
                views = base_data.get("views") if isinstance(base_data, dict) else None
                if not isinstance(views, list) or not views:
                    issues.append("OAG Knowledge.base: missing views")
            except Exception as exc:
                issues.append(f"OAG Knowledge.base: invalid YAML: {exc}")
    concept_count = 0
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.name in RESERVED_NAMES:
            if path.name == "log.md":
                headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
                bad = [heading for heading in headings if not re.match(r"^\d{4}-\d{2}-\d{2}$", heading.strip())]
                if bad:
                    issues.append(f"{rel}: log.md date heading is not YYYY-MM-DD: {bad[0]}")
            for target in _iter_markdown_links(text):
                if not _link_target_exists(root, path, target):
                    issues.append(f"{rel}: broken markdown link: {target}")
            if profile == "obsidian":
                for target in _iter_wiki_links(text):
                    if not _wiki_target_exists(root, path, target):
                        issues.append(f"{rel}: broken wiki link: {target}")
            continue
        concept_count += 1
        try:
            meta, body = _split_frontmatter(path)
        except Exception as exc:
            issues.append(f"{rel}: {exc}")
            continue
        for field in ["type", "title", "resource", "okf_version"]:
            if not _text(meta.get(field)):
                issues.append(f"{rel}: missing required frontmatter field: {field}")
        if _text(meta.get("okf_version")) and _text(meta.get("okf_version")) != OKF_VERSION:
            issues.append(f"{rel}: unsupported okf_version: {_text(meta.get('okf_version'))}")
        resource = _text(meta.get("resource"))
        if resource and not resource.startswith("oag://"):
            issues.append(f"{rel}: resource must use oag:// URI")
        if profile == "obsidian":
            for field in ["oag_kind", "oag_id", "ip"]:
                if not _text(meta.get(field)):
                    issues.append(f"{rel}: missing Obsidian frontmatter field: {field}")
            aliases = meta.get("aliases")
            if not isinstance(aliases, list) or not aliases:
                issues.append(f"{rel}: missing Obsidian aliases")
        for target in _iter_markdown_links(body):
            if not _link_target_exists(root, path, target):
                issues.append(f"{rel}: broken markdown link: {target}")
        if profile == "obsidian":
            for target in _iter_wiki_links(body):
                if not _wiki_target_exists(root, path, target):
                    issues.append(f"{rel}: broken wiki link: {target}")
        if _text(meta.get("type")) == "OAG RTL Module":
            if not _text(meta.get("source_file")):
                issues.append(f"{rel}: RTL module concept missing source_file")
            if re.search(r"^- Source:\s*``\s*$", body, flags=re.MULTILINE):
                issues.append(f"{rel}: RTL module Source is empty")
    return {
        "schema_version": "oag_okf_validation.v1",
        "ok": not issues,
        "concept_count": concept_count,
        "issues": issues,
    }


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.bundle).resolve()
    result = _validate_bundle(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def _safe_rel(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    if not rel or rel.startswith("/") or ".." in PurePosixPath(rel).parts:
        raise ValueError(f"unsafe path: {path}")
    return rel


def cmd_import_draft(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle).resolve()
    ip = Path(args.ip_dir).resolve()
    result = _validate_bundle(bundle)
    if not result["ok"]:
        print(json.dumps({"status": "blocked", "validation": result}, indent=2))
        return 2
    facts: list[str] = []
    for path in sorted(bundle.rglob("*.md")):
        if path.name in RESERVED_NAMES:
            continue
        meta, body = _split_frontmatter(path)
        rel = _safe_rel(path, bundle)
        facts.append(
            f"{rel}: type={_text(meta.get('type'))}; title={_text(meta.get('title'))}; "
            f"description={_text(meta.get('description'))}; body_chars={len(body)}"
        )
    title = args.title or f"OKF import draft {_stamp()}"
    before_hashes = _canonical_source_hashes(ip)
    draft = oag_cli.dispatch_call(
        {
            "tool": "oag.draft",
            "arguments": {
                "ip_dir": str(ip),
                "stage": args.stage,
                "title": title,
                "summary": args.summary or f"Imported {len(facts)} OKF concepts as draft knowledge. This does not modify locked truth.",
                "facts": facts[: args.limit],
                "decisions": [],
                "assumptions": ["OKF import is draft-only until promoted through human-approved OAG gates."],
                "open_questions": [],
                "actor": {"kind": "ai", "id": os.environ.get("USER") or "unknown", "surface": "okf-import"},
                "source": str(bundle),
            },
        }
    )
    after_hashes = _canonical_source_hashes(ip)
    changed = [
        rel
        for rel in sorted(set(before_hashes) | set(after_hashes))
        if before_hashes.get(rel) != after_hashes.get(rel)
    ]
    if changed:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "canonical_oag_concept_changed",
                    "changed": changed,
                    "validation": result,
                    "draft": draft.get("result"),
                },
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": "pass",
                "validation": result,
                "canonical_sources_preserved": True,
                "draft": draft.get("result"),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="export an OAG IP as an OKF bundle")
    export.add_argument("--ip-dir", required=True)
    export.add_argument("--out", required=True)
    export.add_argument(
        "--profile",
        choices=["okf", "obsidian"],
        default="okf",
        help="export profile: okf keeps generic Markdown; obsidian adds wiki links, aliases, and Bases views",
    )
    export.add_argument("--archive", help="optional .tar.gz archive path")
    export.add_argument("--force", action="store_true")
    export.set_defaults(func=cmd_export)

    validate = sub.add_parser("validate", help="validate an OKF bundle")
    validate.add_argument("bundle")
    validate.set_defaults(func=cmd_validate)

    import_draft = sub.add_parser("import-draft", help="import OKF bundle as OAG draft knowledge")
    import_draft.add_argument("bundle")
    import_draft.add_argument("--ip-dir", required=True)
    import_draft.add_argument("--stage", default="req")
    import_draft.add_argument("--title")
    import_draft.add_argument("--summary")
    import_draft.add_argument("--limit", type=int, default=200)
    import_draft.set_defaults(func=cmd_import_draft)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
