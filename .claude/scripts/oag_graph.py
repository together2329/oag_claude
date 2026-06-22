#!/usr/bin/env python3
"""Build and render OAG ontology graphs.

The graph builder consumes the local OAG tool-call gateway and IP knowledge
records, then writes either JSON graph data or a self-contained HTML viewer.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import oag_cli  # noqa: E402

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional fallback
    yaml = None


GRAPH_SCHEMA = "oag_ontology_graph.v1"


TYPE_ORDER = [
    "ip",
    "policy",
    "protection",
    "structure",
    "structure_ref",
    "module",
    "requirement",
    "obligation",
    "rule",
    "rule_instance",
    "draft",
    "contract",
    "evidence",
    "validation",
    "decision",
    "run",
    "stage",
    "gate",
    "ticket",
    "receipt",
    "authoring_packet",
    "ledger",
    "actor",
    "design_fact_module",
    "design_fact_port",
    "design_fact_register",
    "design_fact_memory",
    "design_fact_instance",
    "record",
    "artifact",
    "gap",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_id(*parts: Any) -> str:
    raw = "::".join(str(part or "") for part in parts)
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")
    return text or "node"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def add_node(
        self,
        node_id: str,
        *,
        type: str,
        label: str,
        status: str = "",
        title: str = "",
        data: dict[str, Any] | None = None,
    ) -> str:
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node["label"] = node.get("label") or label
            node["status"] = node.get("status") or status
            node["title"] = node.get("title") or title
            if data:
                node.setdefault("data", {}).update(data)
            return node_id
        self.nodes[node_id] = {
            "id": node_id,
            "type": type,
            "label": label,
            "status": status,
            "title": title or label,
            "data": data or {},
        }
        return node_id

    def add_edge(self, source: str, target: str, *, label: str, type: str = "") -> None:
        if source == target:
            return
        edge_id = _safe_id(source, label, target)
        self.edges[edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": label,
            "type": type or label,
        }

    def to_dict(self) -> dict[str, Any]:
        nodes = list(self.nodes.values())
        edges = list(self.edges.values())
        nodes.sort(key=lambda item: (TYPE_ORDER.index(item["type"]) if item["type"] in TYPE_ORDER else 99, item["label"]))
        edges.sort(key=lambda item: (item["source"], item["target"], item["label"]))
        return {"nodes": nodes, "edges": edges}


def _read_record(path: Path) -> dict[str, Any] | None:
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix in {".yaml", ".yml"} and yaml is not None:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            return None
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data["_path"] = str(path)
    return data


def load_records(ip_dir: Path) -> list[dict[str, Any]]:
    records_dir = ip_dir / "knowledge" / "records"
    records: list[dict[str, Any]] = []
    if records_dir.is_dir():
        for path in sorted([*records_dir.glob("*.json"), *records_dir.glob("*.yaml"), *records_dir.glob("*.yml")]):
            record = _read_record(path)
            if record is not None:
                records.append(record)
    if records:
        return records
    index_path = ip_dir / "knowledge" / "_index.json"
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for item in index.get("records", []):
                if isinstance(item, dict):
                    records.append(_record_from_index_summary(item, ip_dir))
        except Exception:
            pass
    return records


def _record_from_index_summary(item: dict[str, Any], ip_dir: Path) -> dict[str, Any]:
    record_id = str(item.get("id") or item.get("claim") or "IKL_INDEX_SUMMARY")
    return {
        "id": record_id,
        "_path": str(ip_dir / str(item.get("path") or "knowledge/_index.json")),
        "scope": {"ip": item.get("ip") or ip_dir.name, "stage": item.get("stage") or ""},
        "type": item.get("type") or "record",
        "actor": {"kind": item.get("actor_kind") or "", "id": item.get("actor_id") or ""},
        "claim": item.get("claim") or record_id,
        "summary": item.get("summary") or "",
        "tags": item.get("tags") or [],
        "rocev": {
            "requirement": {"id": item.get("requirement_id") or "", "text": item.get("requirement_text") or ""},
            "obligation": {"id": item.get("obligation_id") or "", "text": item.get("obligation_text") or ""},
            "contract": {
                "id": item.get("contract_id") or "",
                "method": item.get("contract_method") or "",
                "pass_condition": item.get("contract_pass_condition") or "",
            },
            "evidence": {
                "files": item.get("evidence_files") or [],
                "tests": item.get("evidence_tests") or [],
                "commit": item.get("commit") or "",
            },
            "validation": {
                "status": item.get("validation_status") or "",
                "verdict": item.get("validation_verdict") or "",
            },
        },
        "validation": {"status": item.get("validation_status") or "", "verdict": item.get("validation_verdict") or ""},
    }


def _call_oag(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = oag_cli.dispatch_call({"tool": tool, "arguments": arguments})
    result = response.get("result") if isinstance(response, dict) else {}
    return result if isinstance(result, dict) else {}


def build_graph(ip_dir: Path, *, stage: str = "", intent: str = "") -> dict[str, Any]:
    ip_dir = ip_dir.expanduser().resolve()
    graph = Graph()
    inspect = _call_oag("oag.inspect", {"ip_dir": str(ip_dir), "stage": stage, "intent": intent})
    check = _call_oag("oag.check", {"ip_dir": str(ip_dir)})
    records = load_records(ip_dir)

    ip_id = graph.add_node(
        _safe_id("ip", ip_dir.name),
        type="ip",
        label=ip_dir.name,
        status=str(inspect.get("validation") or "unknown"),
        data={"path": str(ip_dir), "check": check, "inspect": inspect},
    )

    _add_inspect_nodes(graph, ip_id, inspect)
    _add_ontology_control_nodes(graph, ip_id, ip_dir)
    for record in records:
        _add_record(graph, ip_id, record, ip_dir)

    stats = _stats(graph, inspect, records)
    graph_data = graph.to_dict()
    return {
        "schema_version": GRAPH_SCHEMA,
        "generated_at": _now(),
        "ip": ip_dir.name,
        "ip_dir": str(ip_dir),
        "stage": stage,
        "intent": intent,
        "stats": stats,
        "inspect": inspect,
        "check": check,
        "graph": graph_data,
    }


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _yaml_id_items(path: Path, key: str) -> list[dict[str, Any]]:
    data = _read_yaml(path)
    if isinstance(data.get(key), list):
        return [item for item in data[key] if isinstance(item, dict)]
    if not path.is_file():
        return []
    items: list[dict[str, Any]] = []
    for match in re.finditer(r"(?m)^\s*-\s*id\s*:\s*([A-Za-z0-9_.:-]+)", path.read_text(encoding="utf-8", errors="ignore")):
        items.append({"id": match.group(1)})
    return items


def _add_ontology_control_nodes(graph: Graph, ip_id: str, ip_dir: Path) -> None:
    policies = _read_yaml(ip_dir / "ontology" / "policies.yaml")
    profile = str(policies.get("closure_profile") or "")
    if profile:
        policy_id = graph.add_node(
            _safe_id("policy", "closure_profile", profile),
            type="policy",
            label=profile,
            status="active",
            data={"path": str(ip_dir / "ontology" / "policies.yaml"), "closure_profile": profile},
        )
        graph.add_edge(ip_id, policy_id, label="uses_policy")

    structure_policy = policies.get("structure_policy") if isinstance(policies.get("structure_policy"), dict) else {}
    decomposition = _read_yaml(ip_dir / "ontology" / "decomposition.yaml")
    profile_doc = decomposition.get("profile") if isinstance(decomposition.get("profile"), dict) else {}
    structure_profile = str(profile_doc.get("mode") or structure_policy.get("default_profile") or "")
    if structure_profile:
        policy_id = graph.add_node(
            _safe_id("policy", "structure_profile", structure_profile),
            type="policy",
            label=structure_profile,
            status="active",
            data={"path": str(ip_dir / "ontology" / "decomposition.yaml"), "profile": profile_doc, "structure_policy": structure_policy},
        )
        graph.add_edge(ip_id, policy_id, label="uses_structure_profile")

    structure = _read_yaml(ip_dir / "ontology" / "structure.yaml")
    structure_ids: set[str] = set()
    if structure:
        structure_id = graph.add_node(
            _safe_id("structure", "namespace"),
            type="structure",
            label="structure namespace",
            status="declared",
            data={"path": str(ip_dir / "ontology" / "structure.yaml"), **structure},
        )
        graph.add_edge(ip_id, structure_id, label="has_structure")
        for key in ("signals", "interfaces", "registers", "state", "derived_signals", "clock_domains", "reset_domains"):
            for item in _as_list(structure.get(key)):
                if isinstance(item, dict):
                    sid = str(item.get("id") or item.get("name") or item.get("signal") or "").strip()
                    data = item
                else:
                    sid = str(item).strip()
                    data = {"id": sid}
                if not sid:
                    continue
                structure_ids.add(sid)
                ref_id = graph.add_node(
                    _safe_id("structure_ref", sid),
                    type="structure_ref",
                    label=sid,
                    status=key,
                    data={"path": str(ip_dir / "ontology" / "structure.yaml"), "section": key, **data},
                )
                graph.add_edge(structure_id, ref_id, label="declares")

    if decomposition:
        for module in _as_list(decomposition.get("modules")):
            if not isinstance(module, dict):
                continue
            mid = str(module.get("id") or module.get("name") or module.get("module") or "").strip()
            if not mid:
                continue
            module_id = graph.add_node(
                _safe_id("module", mid),
                type="module",
                label=mid,
                status=str(module.get("ownership") or "current_ip"),
                data={"path": str(ip_dir / "ontology" / "decomposition.yaml"), **module},
            )
            graph.add_edge(ip_id, module_id, label="has_module")
            for oid in _as_list(module.get("owned_obligations") or module.get("obligations")):
                if str(oid).strip():
                    graph.add_edge(module_id, _safe_id("obligation", oid), label="owns_obligation")
            for cid in _as_list(module.get("owned_contracts") or module.get("contracts")):
                if str(cid).strip():
                    graph.add_edge(module_id, _safe_id("contract", cid), label="owns_contract")
            for sid in _as_list(module.get("structure_refs")):
                if str(sid).strip():
                    graph.add_edge(module_id, _safe_id("structure_ref", sid), label="references_structure")

    design_spec = ip_dir / "ontology" / "generated" / "design_spec.json"
    if design_spec.is_file():
        data = _read_record(design_spec) or {}
        artifact_id = graph.add_node(
            _safe_id("artifact", "design_spec"),
            type="artifact",
            label="generated design spec",
            status=str(data.get("status") or "present"),
            data={"path": str(design_spec), "structure_profile": data.get("structure_profile"), "issues": data.get("issues") or []},
        )
        graph.add_edge(ip_id, artifact_id, label="has_artifact")

    design_facts = ip_dir / "ontology" / "generated" / "design_facts_graph.json"
    if design_facts.is_file():
        data = _read_record(design_facts) or {}
        artifact_id = graph.add_node(
            _safe_id("artifact", "design_facts_graph"),
            type="artifact",
            label="design facts graph",
            status=str(data.get("status") or "present"),
            data={"path": str(design_facts), "stats": data.get("stats") or {}, "extractor": data.get("extractor") or {}, "issues": data.get("issues") or []},
        )
        graph.add_edge(ip_id, artifact_id, label="has_artifact")
        for module in _as_list(data.get("modules")):
            if not isinstance(module, dict):
                continue
            name = str(module.get("name") or "").strip()
            if not name:
                continue
            fact_module_id = graph.add_node(
                _safe_id("design_fact_module", name),
                type="design_fact_module",
                label=name,
                status="extracted",
                data={"source": module.get("source") or {}, "path": str(design_facts)},
            )
            graph.add_edge(artifact_id, fact_module_id, label="contains_fact")
            graph.add_edge(fact_module_id, _safe_id("module", name), label="implements_module")
            for port in _as_list(module.get("ports")):
                if isinstance(port, dict) and str(port.get("name") or "").strip():
                    pid = graph.add_node(
                        _safe_id("design_fact_port", name, port.get("name")),
                        type="design_fact_port",
                        label=str(port.get("name")),
                        status=str(port.get("direction") or "port"),
                        data=port,
                    )
                    graph.add_edge(fact_module_id, pid, label="has_port")
            for reg in _as_list(module.get("registers")):
                if isinstance(reg, dict) and str(reg.get("name") or "").strip():
                    rid = graph.add_node(
                        _safe_id("design_fact_register", name, reg.get("name")),
                        type="design_fact_register",
                        label=str(reg.get("name")),
                        status="register",
                        data=reg,
                    )
                    graph.add_edge(fact_module_id, rid, label="has_register")
            for mem in _as_list(module.get("memories")):
                if isinstance(mem, dict) and str(mem.get("name") or "").strip():
                    mid = graph.add_node(
                        _safe_id("design_fact_memory", name, mem.get("name")),
                        type="design_fact_memory",
                        label=str(mem.get("name")),
                        status="memory",
                        data=mem,
                    )
                    graph.add_edge(fact_module_id, mid, label="has_memory")
            for inst in _as_list(module.get("instances")):
                if isinstance(inst, dict) and str(inst.get("name") or "").strip():
                    iid = graph.add_node(
                        _safe_id("design_fact_instance", name, inst.get("name")),
                        type="design_fact_instance",
                        label=str(inst.get("name")),
                        status=str(inst.get("module") or "instance"),
                        data=inst,
                    )
                    graph.add_edge(fact_module_id, iid, label="has_instance")
                    if str(inst.get("module") or "").strip():
                        graph.add_edge(iid, _safe_id("design_fact_module", inst.get("module")), label="instantiates")

    packets = ip_dir / "ontology" / "generated" / "authoring_packets"
    if packets.is_dir():
        for path in sorted(packets.glob("*.json")):
            data = _read_record(path) or {}
            module = data.get("module") if isinstance(data.get("module"), dict) else {}
            label = str(module.get("id") or path.stem)
            packet_id = graph.add_node(
                _safe_id("authoring_packet", label),
                type="authoring_packet",
                label=label,
                status="editable" if (data.get("execution_policy") or {}).get("draft_allowed") else "locked",
                data={"path": str(path), **{k: v for k, v in data.items() if k != "_path"}},
            )
            graph.add_edge(ip_id, packet_id, label="has_authoring_packet")
            if label:
                graph.add_edge(_safe_id("module", label), packet_id, label="authored_by_packet")

    protection = _read_yaml(ip_dir / "ontology" / "protection.yaml")
    if protection:
        protected_paths = protection.get("protected_paths") if isinstance(protection.get("protected_paths"), list) else []
        protection_id = graph.add_node(
            _safe_id("protection", "protected_fields"),
            type="protection",
            label="protected fields",
            status="declared",
            data={"path": str(ip_dir / "ontology" / "protection.yaml"), "protected_paths": protected_paths, "protected_fields": protection.get("protected_fields") or []},
        )
        graph.add_edge(ip_id, protection_id, label="uses_protection")

    ledger_path = ip_dir / "knowledge" / "ledger.jsonl"
    if ledger_path.is_file():
        event_count = sum(1 for line in ledger_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())
        ledger_id = graph.add_node(
            _safe_id("ledger", "append_only"),
            type="ledger",
            label="append-only ledger",
            status="present",
            data={"path": str(ledger_path), "events": event_count},
        )
        graph.add_edge(ip_id, ledger_id, label="has_ledger")

    runs = ip_dir / "ontology" / "runs"
    active_run = _read_record(runs / "active_run.json") if runs.is_dir() else None
    active_run_id = str((active_run or {}).get("run_id") or "")
    if runs.is_dir():
        for state_path in sorted(runs.glob("*/run_state.json")):
            data = _read_record(state_path) or {}
            run_id = str(data.get("run_id") or state_path.parent.name)
            status = str(data.get("status") or "unknown")
            run_node = graph.add_node(
                _safe_id("run", run_id),
                type="run",
                label=run_id,
                status=status,
                data={
                    "path": str(state_path),
                    "active": run_id == active_run_id,
                    **{k: v for k, v in data.items() if k != "_path"},
                },
            )
            graph.add_edge(ip_id, run_node, label="has_run")
            obligation = str(data.get("active_obligation") or "")
            if obligation:
                graph.add_edge(run_node, _safe_id("obligation", obligation), label="targets_obligation")
            for contract in _as_list(data.get("active_contracts")):
                if str(contract).strip():
                    graph.add_edge(run_node, _safe_id("contract", contract), label="targets_contract")
            owner = data.get("active_owner") if isinstance(data.get("active_owner"), dict) else {}
            module = str(owner.get("module") or "")
            if module:
                graph.add_edge(run_node, _safe_id("module", module), label="routed_to")
            checkpoint = data.get("last_checkpoint") if isinstance(data.get("last_checkpoint"), dict) else {}
            receipt = checkpoint.get("decision_receipt") if isinstance(checkpoint.get("decision_receipt"), dict) else {}
            if receipt.get("id"):
                graph.add_edge(run_node, _safe_id("decision", receipt.get("id")), label="checkpointed_by")

    compiled = ip_dir / "ontology" / "generated" / "design_truth_graph.json"
    if compiled.is_file():
        data = _read_record(compiled) or {}
        artifact_id = graph.add_node(
            _safe_id("artifact", "design_truth_graph"),
            type="artifact",
            label="design truth graph",
            status=str(data.get("status") or "present"),
            data={"path": str(compiled), "stats": data.get("stats") or {}, "issues": data.get("issues") or []},
        )
        graph.add_edge(ip_id, artifact_id, label="has_artifact")

    for stage in _yaml_id_items(ip_dir / "ontology" / "stages.yaml", "stages"):
        sid = str(stage.get("id") or "")
        if not sid:
            continue
        stage_id = graph.add_node(
            _safe_id("stage", sid),
            type="stage",
            label=sid,
            status="declared",
            data={"owner": stage.get("owner") or "", "gate": stage.get("gate") or "", "inputs": stage.get("inputs") or [], "outputs": stage.get("outputs") or []},
        )
        graph.add_edge(ip_id, stage_id, label="has_stage")
        gate = str(stage.get("gate") or "")
        if gate:
            gate_id = graph.add_node(_safe_id("gate", gate), type="gate", label=gate, status="declared", data={"source": "ontology/stages.yaml"})
            graph.add_edge(stage_id, gate_id, label="gated_by")

    for gate in _yaml_id_items(ip_dir / "ontology" / "gates" / "gate_self_test_registry.yaml", "gates"):
        gid = str(gate.get("id") or "")
        if not gid:
            continue
        gate_id = graph.add_node(
            _safe_id("gate", gid),
            type="gate",
            label=gid,
            status=str(gate.get("status") or "unknown"),
            data=gate,
        )
        graph.add_edge(ip_id, gate_id, label="has_gate")

    rules = _yaml_id_items(ip_dir / "ontology" / "design_rules.yaml", "rules")
    rule_by_id = {str(rule.get("id") or ""): rule for rule in rules if rule.get("id")}
    for rule in rules:
        rid = str(rule.get("id") or "")
        if not rid:
            continue
        rule_id = graph.add_node(
            _safe_id("rule", rid),
            type="rule",
            label=rid,
            status=str(rule.get("status") or "active"),
            data={"path": str(ip_dir / "ontology" / "design_rules.yaml"), **rule},
        )
        graph.add_edge(ip_id, rule_id, label="uses_rule")

    for instance in _yaml_id_items(ip_dir / "ontology" / "design_rules.yaml", "instances"):
        iid = str(instance.get("id") or "")
        if not iid:
            continue
        inst_id = graph.add_node(
            _safe_id("rule_instance", iid),
            type="rule_instance",
            label=iid,
            status=str(instance.get("status") or "open"),
            data={"path": str(ip_dir / "ontology" / "design_rules.yaml"), **instance},
        )
        graph.add_edge(ip_id, inst_id, label="has_rule_instance")
        rid = str(instance.get("rule") or instance.get("rule_id") or "")
        if rid and rid in rule_by_id:
            graph.add_edge(_safe_id("rule", rid), inst_id, label="instantiated_by")

    drafts = ip_dir / "ontology" / "drafts"
    if drafts.is_dir():
        for path in sorted(drafts.glob("*.json")):
            data = _read_record(path) or {}
            draft_id = graph.add_node(
                _safe_id("draft", data.get("id") or path.stem),
                type="draft",
                label=str(data.get("title") or path.stem),
                status=str(data.get("promotion_state") or "draft"),
                data={"path": str(path), **{k: v for k, v in data.items() if k != "_path"}},
            )
            graph.add_edge(ip_id, draft_id, label="has_draft")

    receipts = ip_dir / "ontology" / "evidence" / "stage_runs"
    if receipts.is_dir():
        for path in sorted(receipts.glob("*.json")):
            data = _read_record(path) or {}
            rid = graph.add_node(
                _safe_id("receipt", path.stem),
                type="receipt",
                label=path.stem,
                status=str(data.get("status") or "present"),
                data={"path": str(path), **{k: v for k, v in data.items() if k != "_path"}},
            )
            graph.add_edge(ip_id, rid, label="has_receipt")

    decisions = ip_dir / "ontology" / "validations"
    if decisions.is_dir():
        for path in sorted(decisions.glob("*.json")):
            data = _read_record(path) or {}
            did = graph.add_node(
                _safe_id("decision", data.get("id") or path.stem),
                type="decision",
                label=str(data.get("action") or data.get("id") or path.stem),
                status="allowed" if data.get("allowed") is True else str(data.get("reason") or "blocked"),
                data={"path": str(path), **{k: v for k, v in data.items() if k != "_path"}},
            )
            graph.add_edge(ip_id, did, label="has_decision")

    tickets = ip_dir / "handoff" / "failure_tickets"
    if tickets.is_dir():
        for path in sorted(tickets.glob("*.json")):
            data = _read_record(path) or {}
            tid = graph.add_node(
                _safe_id("ticket", data.get("id") or path.stem),
                type="ticket",
                label=str(data.get("id") or path.stem),
                status=str(data.get("status") or "open"),
                data={"path": str(path), **{k: v for k, v in data.items() if k != "_path"}},
            )
            graph.add_edge(ip_id, tid, label="has_ticket")


def _add_inspect_nodes(graph: Graph, ip_id: str, inspect: dict[str, Any]) -> None:
    evidence = inspect.get("evidence") if isinstance(inspect.get("evidence"), dict) else {}
    for key, value in evidence.items():
        if not isinstance(value, dict):
            continue
        present = bool(value.get("present"))
        status = str(value.get("status") or ("present" if present else "missing"))
        label = key.replace("_", " ")
        artifact_id = graph.add_node(
            _safe_id("artifact", key),
            type="artifact",
            label=label,
            status=status,
            data=value,
        )
        graph.add_edge(ip_id, artifact_id, label="has_artifact")
        if key == "requirement":
            for path in value.get("paths") or []:
                req_id = graph.add_node(
                    _safe_id("requirement", Path(str(path)).name),
                    type="requirement",
                    label=Path(str(path)).name,
                    status="present",
                    data={"path": path},
                )
                graph.add_edge(ip_id, req_id, label="has_requirement")
                graph.add_edge(req_id, artifact_id, label="materialized_by")
        if key == "obligation" and present:
            obligation_path = Path(str(value.get("path") or "obligations"))
            obligation_label = f"{obligation_path.name} ({value.get('count') or 0})"
            obl_id = graph.add_node(
                _safe_id("obligation", obligation_path.name),
                type="obligation",
                label=obligation_label,
                status="present",
                data=value,
            )
            graph.add_edge(ip_id, obl_id, label="has_obligation_set")
            graph.add_edge(obl_id, artifact_id, label="materialized_by")
        if key == "contract":
            for path in value.get("paths") or []:
                contract_id = graph.add_node(
                    _safe_id("contract", Path(str(path)).name),
                    type="contract",
                    label=Path(str(path)).name,
                    status="present",
                    data={"path": path},
                )
                graph.add_edge(ip_id, contract_id, label="has_contract")
                graph.add_edge(contract_id, artifact_id, label="materialized_by")

    for gap in inspect.get("gaps") or []:
        gap_id = graph.add_node(
            _safe_id("gap", gap),
            type="gap",
            label=str(gap),
            status="open",
            data={"gap": gap},
        )
        graph.add_edge(ip_id, gap_id, label="has_gap")


def _add_record(graph: Graph, ip_id: str, record: dict[str, Any], ip_dir: Path) -> None:
    record_id = str(record.get("id") or record.get("claim") or "record")
    validation = record.get("validation") if isinstance(record.get("validation"), dict) else {}
    rocev = record.get("rocev") if isinstance(record.get("rocev"), dict) else {}
    status = str(validation.get("status") or rocev.get("validation", {}).get("status") if isinstance(rocev.get("validation"), dict) else "")
    rec_node = graph.add_node(
        _safe_id("record", record_id),
        type="record",
        label=str(record.get("claim") or record_id),
        status=status or "unknown",
        data={
            "id": record_id,
            "path": _rel_path(str(record.get("_path") or ""), ip_dir),
            "summary": record.get("summary") or "",
            "stage": (record.get("scope") or {}).get("stage") if isinstance(record.get("scope"), dict) else "",
            "tags": record.get("tags") or [],
        },
    )
    graph.add_edge(ip_id, rec_node, label="has_record")

    actor = record.get("actor") if isinstance(record.get("actor"), dict) else {}
    actor_id = str(actor.get("id") or "")
    if actor_id:
        actor_node = graph.add_node(
            _safe_id("actor", actor.get("kind") or "actor", actor_id),
            type="actor",
            label=f"{actor.get('kind') or 'actor'}:{actor_id}",
            status=str(actor.get("surface") or ""),
            data=actor,
        )
        graph.add_edge(actor_node, rec_node, label="created")

    requirement = rocev.get("requirement") if isinstance(rocev.get("requirement"), dict) else {}
    obligation = rocev.get("obligation") if isinstance(rocev.get("obligation"), dict) else {}
    contract = rocev.get("contract") if isinstance(rocev.get("contract"), dict) else {}
    evidence = rocev.get("evidence") if isinstance(rocev.get("evidence"), dict) else record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    validation_obj = rocev.get("validation") if isinstance(rocev.get("validation"), dict) else validation

    req_node = _add_rocev_node(graph, "requirement", requirement, fallback=record_id, status="")
    obl_node = _add_rocev_node(graph, "obligation", obligation, fallback=record_id, status="")
    contract_node = _add_rocev_node(graph, "contract", contract, fallback=record_id, status=str(contract.get("method") or ""))
    validation_node = _add_rocev_node(
        graph,
        "validation",
        validation_obj,
        fallback=record_id,
        status=str(validation_obj.get("status") or validation_obj.get("verdict") or status),
    )

    if req_node:
        graph.add_edge(rec_node, req_node, label="references")
    if req_node and obl_node:
        graph.add_edge(req_node, obl_node, label="has_obligation")
    if obl_node:
        graph.add_edge(rec_node, obl_node, label="claims")
    if obl_node and contract_node:
        graph.add_edge(obl_node, contract_node, label="judged_by")
    if contract_node:
        graph.add_edge(rec_node, contract_node, label="uses_contract")

    evidence_nodes = _add_evidence_nodes(graph, evidence, ip_dir, record_id)
    for evidence_node in evidence_nodes:
        if contract_node:
            graph.add_edge(contract_node, evidence_node, label="collects")
        graph.add_edge(rec_node, evidence_node, label="attaches")
        if validation_node:
            graph.add_edge(evidence_node, validation_node, label="supports")
    if validation_node:
        if obl_node:
            graph.add_edge(validation_node, obl_node, label="validates")
        graph.add_edge(rec_node, validation_node, label="decides")


def _add_rocev_node(graph: Graph, type_name: str, obj: dict[str, Any], *, fallback: str, status: str = "") -> str:
    if not isinstance(obj, dict):
        obj = {}
    obj_id = str(obj.get("id") or "")
    text = str(obj.get("text") or obj.get("method") or obj.get("verdict") or obj.get("status") or "")
    if not obj_id and not text and type_name not in {"validation"}:
        return ""
    node_id = _safe_id(type_name, obj_id or fallback)
    label = obj_id or text or f"{type_name}:{fallback}"
    if type_name == "contract" and obj.get("method"):
        label = obj_id or str(obj.get("method"))
    if type_name == "validation":
        label = obj_id or str(obj.get("verdict") or obj.get("status") or "validation")
    return graph.add_node(node_id, type=type_name, label=label, status=status, data=obj)


def _add_evidence_nodes(graph: Graph, evidence: dict[str, Any], ip_dir: Path, record_id: str) -> list[str]:
    nodes: list[str] = []
    for path in _as_list(evidence.get("files")):
        if not str(path).strip():
            continue
        rel = _rel_path(str(path), ip_dir)
        node = graph.add_node(
            _safe_id("evidence", "file", rel),
            type="evidence",
            label=rel,
            status="file",
            data={"kind": "file", "path": rel},
        )
        nodes.append(node)
    for test in _as_list(evidence.get("tests")):
        if not str(test).strip():
            continue
        node = graph.add_node(
            _safe_id("evidence", "test", test),
            type="evidence",
            label=str(test),
            status="test",
            data={"kind": "test", "test": test},
        )
        nodes.append(node)
    commit = str(evidence.get("commit") or "").strip()
    if commit:
        node = graph.add_node(
            _safe_id("evidence", "commit", commit),
            type="evidence",
            label=commit,
            status="commit",
            data={"kind": "commit", "commit": commit},
        )
        nodes.append(node)
    if not nodes and evidence:
        node = graph.add_node(
            _safe_id("evidence", "empty", record_id),
            type="evidence",
            label="evidence pending",
            status="missing",
            data=evidence,
        )
        nodes.append(node)
    return nodes


def _rel_path(value: str, ip_dir: Path) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        try:
            return str(path.relative_to(ip_dir))
        except Exception:
            return str(path)
    return value


def _stats(graph: Graph, inspect: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    node_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        node_counts[node["type"]] = node_counts.get(node["type"], 0) + 1
        status = str(node.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "node_counts": node_counts,
        "status_counts": status_counts,
        "record_count": len(records),
        "gap_count": len(inspect.get("gaps") or []),
        "edge_count": len(graph.edges),
    }


def write_html(graph_data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(graph_data, ensure_ascii=False)
    html_text = HTML_TEMPLATE.replace("__OAG_GRAPH_JSON__", payload.replace("</", "<\\/"))
    output.write_text(html_text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="build graph JSON or a self-contained HTML viewer")
    build.add_argument("--ip-dir", required=True)
    build.add_argument("--stage", default="")
    build.add_argument("--intent", default="")
    build.add_argument("--json-out", default="")
    build.add_argument("--html-out", default="")
    build.set_defaults(func=cmd_build)

    return parser


def cmd_build(args: argparse.Namespace) -> int:
    data = build_graph(Path(args.ip_dir), stage=args.stage, intent=args.intent)
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.html_out:
        write_html(data, Path(args.html_out).expanduser())
    if not args.json_out and not args.html_out:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OAG Ontology Graph</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #5c6672;
      --border: #d9dee6;
      --accent: #2563eb;
      --danger: #dc2626;
      --warn: #d97706;
      --ok: #15803d;
      --node-ip: #1f2937;
      --node-policy: #9333ea;
      --node-protection: #c026d3;
      --node-requirement: #2563eb;
      --node-obligation: #7c3aed;
      --node-rule: #be123c;
      --node-rule-instance: #f43f5e;
      --node-draft: #a16207;
      --node-contract: #0891b2;
      --node-evidence: #16a34a;
      --node-validation: #ea580c;
      --node-decision: #db2777;
      --node-run: #4f46e5;
      --node-stage: #0369a1;
      --node-gate: #ca8a04;
      --node-ticket: #b45309;
      --node-receipt: #15803d;
      --node-ledger: #0d9488;
      --node-actor: #4b5563;
      --node-record: #0f766e;
      --node-artifact: #64748b;
      --node-gap: #dc2626;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .app {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 340px;
      min-height: 100vh;
    }
    aside, .details {
      background: var(--panel);
      border-color: var(--border);
      border-style: solid;
      overflow: auto;
      max-height: 100vh;
    }
    aside { border-width: 0 1px 0 0; padding: 18px; }
    .details { border-width: 0 0 0 1px; padding: 18px; }
    main { min-width: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); }
    header {
      padding: 14px 18px;
      background: rgba(255,255,255,.88);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    h1 { margin: 0; font-size: 18px; line-height: 1.25; }
    h2 { margin: 18px 0 10px; font-size: 13px; text-transform: uppercase; color: var(--muted); }
    .sub { color: var(--muted); font-size: 12px; margin-top: 4px; word-break: break-word; }
    .stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 14px; }
    .stat { border: 1px solid var(--border); border-radius: 8px; padding: 10px; background: #fbfcfe; }
    .stat strong { display: block; font-size: 18px; }
    .stat span { color: var(--muted); font-size: 12px; }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    input, select {
      width: 100%;
      height: 34px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      color: var(--text);
      font-size: 13px;
    }
    .control { margin: 12px 0; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      border: 1px solid var(--border);
      border-radius: 999px;
      background: #fff;
      padding: 5px 9px;
      font-size: 12px;
      cursor: pointer;
      user-select: none;
    }
    .chip.active { border-color: var(--accent); color: var(--accent); background: #eff6ff; }
    .canvas-wrap { position: relative; min-height: 0; overflow: hidden; }
    svg { width: 100%; height: 100%; display: block; background: radial-gradient(circle at 30% 20%, #ffffff 0, #f8fafc 36%, #eef2f7 100%); }
    .edge { stroke: #9aa4b2; stroke-width: 1.2; opacity: .72; }
    .edge-label { fill: #667085; font-size: 10px; paint-order: stroke; stroke: #fff; stroke-width: 3px; }
    .node circle { stroke: #fff; stroke-width: 2.2; cursor: pointer; }
    .node text { font-size: 11px; fill: #1f2937; paint-order: stroke; stroke: #fff; stroke-width: 4px; pointer-events: none; }
    .node.dim, .edge.dim, .edge-label.dim { opacity: .08; }
    .node.selected circle { stroke: #111827; stroke-width: 3.2; }
    .list { display: grid; gap: 8px; }
    .item {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      padding: 9px;
      cursor: pointer;
    }
    .item:hover { border-color: #aab4c0; }
    .item-title { font-size: 13px; font-weight: 650; }
    .item-meta { color: var(--muted); font-size: 11px; margin-top: 3px; }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 11px;
      border: 1px solid var(--border);
      margin: 0 4px 4px 0;
      background: #fff;
    }
    .badge.gap, .badge.fail, .badge.blocked, .badge.open, .badge.missing { color: var(--danger); border-color: #fecaca; background: #fef2f2; }
    .badge.pass, .badge.closed, .badge.promoted { color: var(--ok); border-color: #bbf7d0; background: #f0fdf4; }
    .badge.partial, .badge.pending, .badge.present { color: var(--warn); border-color: #fed7aa; background: #fff7ed; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #f8fafc;
      font-size: 11px;
      max-height: 360px;
      overflow: auto;
    }
    .legend { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-top: 8px; }
    .legend span { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; grid-template-rows: auto minmax(60vh, 1fr) auto; }
      aside, .details { max-height: none; border-width: 0 0 1px 0; }
      .details { border-width: 1px 0 0 0; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>OAG Ontology Graph</h1>
      <div class="sub" id="subtitle"></div>
      <div class="stats">
        <div class="stat"><strong id="nodeCount">0</strong><span>nodes</span></div>
        <div class="stat"><strong id="edgeCount">0</strong><span>edges</span></div>
        <div class="stat"><strong id="recordCount">0</strong><span>records</span></div>
        <div class="stat"><strong id="gapCount">0</strong><span>gaps</span></div>
      </div>
      <h2>Filter</h2>
      <div class="control">
        <label for="search">Search</label>
        <input id="search" placeholder="requirement, scoreboard, coverage..." />
      </div>
      <div class="control">
        <label for="typeFilter">Type</label>
        <select id="typeFilter"><option value="">All types</option></select>
      </div>
      <div class="control">
        <label for="statusFilter">Status</label>
        <select id="statusFilter"><option value="">All statuses</option></select>
      </div>
      <div class="control">
        <label>Quick types</label>
        <div class="chips" id="typeChips"></div>
      </div>
      <h2>Legend</h2>
      <div class="legend" id="legend"></div>
      <h2>Visible Nodes</h2>
      <div class="list" id="nodeList"></div>
    </aside>
    <main>
      <header>
        <div>
          <h1 id="graphTitle">Ontology Graph</h1>
          <div class="sub" id="graphMeta"></div>
        </div>
        <div class="sub" id="visibleCount"></div>
      </header>
      <div class="canvas-wrap"><svg id="graph"></svg></div>
    </main>
    <section class="details">
      <h1>Selection</h1>
      <div id="detailBody" class="sub">Select a node to inspect ROCEV data, artifact state, or gap details.</div>
    </section>
  </div>
  <script>
    const GRAPH = __OAG_GRAPH_JSON__;
    const colors = {
      ip: getCss('--node-ip'),
      policy: getCss('--node-policy'),
      protection: getCss('--node-protection'),
      requirement: getCss('--node-requirement'),
      obligation: getCss('--node-obligation'),
      rule: getCss('--node-rule'),
      rule_instance: getCss('--node-rule-instance'),
      draft: getCss('--node-draft'),
      contract: getCss('--node-contract'),
      evidence: getCss('--node-evidence'),
      validation: getCss('--node-validation'),
      decision: getCss('--node-decision'),
      run: getCss('--node-run'),
      stage: getCss('--node-stage'),
      gate: getCss('--node-gate'),
      ticket: getCss('--node-ticket'),
      receipt: getCss('--node-receipt'),
      ledger: getCss('--node-ledger'),
      actor: getCss('--node-actor'),
      record: getCss('--node-record'),
      artifact: getCss('--node-artifact'),
      gap: getCss('--node-gap')
    };
    let selectedId = null;
    let activeChip = '';
    const svg = document.getElementById('graph');
    const ns = 'http://www.w3.org/2000/svg';
    const data = GRAPH.graph || {nodes: [], edges: []};
    const nodes = data.nodes.map((node, i) => ({...node, x: 160 + (i % 8) * 95, y: 120 + Math.floor(i / 8) * 70, vx: 0, vy: 0}));
    const nodeById = new Map(nodes.map(n => [n.id, n]));
    const edges = data.edges.map(e => ({...e, sourceNode: nodeById.get(e.source), targetNode: nodeById.get(e.target)})).filter(e => e.sourceNode && e.targetNode);
    const search = document.getElementById('search');
    const typeFilter = document.getElementById('typeFilter');
    const statusFilter = document.getElementById('statusFilter');
    init();
    tickMany(220);
    render();
    search.addEventListener('input', render);
    typeFilter.addEventListener('change', () => { activeChip = typeFilter.value; syncChips(); render(); });
    statusFilter.addEventListener('change', render);
    window.addEventListener('resize', render);

    function init() {
      document.getElementById('subtitle').textContent = `${GRAPH.ip || ''} · ${GRAPH.stage || 'all stages'} · ${GRAPH.intent || 'all intents'}`;
      document.getElementById('graphTitle').textContent = GRAPH.ip || 'Ontology Graph';
      document.getElementById('graphMeta').textContent = `${GRAPH.generated_at || ''} · ${GRAPH.ip_dir || ''}`;
      document.getElementById('nodeCount').textContent = nodes.length;
      document.getElementById('edgeCount').textContent = edges.length;
      document.getElementById('recordCount').textContent = GRAPH.stats?.record_count ?? 0;
      document.getElementById('gapCount').textContent = GRAPH.stats?.gap_count ?? 0;
      const types = [...new Set(nodes.map(n => n.type))].sort();
      const statuses = [...new Set(nodes.map(n => n.status || 'unknown'))].sort();
      for (const type of types) typeFilter.append(new Option(type, type));
      for (const status of statuses) statusFilter.append(new Option(status, status));
      const chips = document.getElementById('typeChips');
      chips.innerHTML = '';
      for (const type of types) {
        const chip = document.createElement('button');
        chip.className = 'chip';
        chip.textContent = type;
        chip.onclick = () => {
          activeChip = activeChip === type ? '' : type;
          typeFilter.value = activeChip;
          syncChips();
          render();
        };
        chips.appendChild(chip);
      }
      syncChips();
      const legend = document.getElementById('legend');
      legend.innerHTML = '';
      for (const type of types) {
        const row = document.createElement('span');
        row.innerHTML = `<i class="dot" style="background:${colors[type] || '#94a3b8'}"></i>${escapeHtml(type)}`;
        legend.appendChild(row);
      }
    }

    function syncChips() {
      [...document.querySelectorAll('.chip')].forEach(chip => chip.classList.toggle('active', chip.textContent === activeChip));
    }

    function tickMany(iterations) {
      const width = Math.max(760, svg.clientWidth || 960);
      const height = Math.max(520, svg.clientHeight || 620);
      const centerX = width / 2;
      const centerY = height / 2;
      for (let step = 0; step < iterations; step++) {
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j];
            let dx = b.x - a.x, dy = b.y - a.y;
            let dist2 = dx * dx + dy * dy + 0.01;
            let force = Math.min(2200 / dist2, 2.8);
            let dist = Math.sqrt(dist2);
            let fx = (dx / dist) * force, fy = (dy / dist) * force;
            a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
          }
        }
        for (const edge of edges) {
          const a = edge.sourceNode, b = edge.targetNode;
          const dx = b.x - a.x, dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const desired = edge.label.includes('has_') ? 120 : 94;
          const force = (dist - desired) * 0.018;
          const fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
        }
        for (const node of nodes) {
          node.vx += (centerX - node.x) * 0.004;
          node.vy += (centerY - node.y) * 0.004;
          node.vx *= 0.82; node.vy *= 0.82;
          node.x = Math.max(36, Math.min(width - 36, node.x + node.vx));
          node.y = Math.max(36, Math.min(height - 36, node.y + node.vy));
        }
      }
    }

    function currentVisible() {
      const q = search.value.trim().toLowerCase();
      const t = typeFilter.value;
      const s = statusFilter.value;
      const visible = new Set();
      for (const node of nodes) {
        const hay = `${node.id} ${node.type} ${node.label} ${node.status} ${node.title} ${JSON.stringify(node.data || {})}`.toLowerCase();
        if (t && node.type !== t) continue;
        if (s && (node.status || 'unknown') !== s) continue;
        if (q && !hay.includes(q)) continue;
        visible.add(node.id);
      }
      if (q) {
        for (const edge of edges) {
          if (visible.has(edge.source) || visible.has(edge.target)) {
            visible.add(edge.source);
            visible.add(edge.target);
          }
        }
      }
      return visible;
    }

    function render() {
      tickMany(12);
      const visible = currentVisible();
      document.getElementById('visibleCount').textContent = `${visible.size}/${nodes.length} visible`;
      svg.innerHTML = '';
      const defs = document.createElementNS(ns, 'defs');
      defs.innerHTML = `<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa4b2"/></marker>`;
      svg.appendChild(defs);
      for (const edge of edges) {
        const show = visible.has(edge.source) && visible.has(edge.target);
        const line = document.createElementNS(ns, 'line');
        line.setAttribute('class', `edge ${show ? '' : 'dim'}`);
        line.setAttribute('x1', edge.sourceNode.x);
        line.setAttribute('y1', edge.sourceNode.y);
        line.setAttribute('x2', edge.targetNode.x);
        line.setAttribute('y2', edge.targetNode.y);
        line.setAttribute('marker-end', 'url(#arrow)');
        svg.appendChild(line);
        const label = document.createElementNS(ns, 'text');
        label.setAttribute('class', `edge-label ${show ? '' : 'dim'}`);
        label.setAttribute('x', (edge.sourceNode.x + edge.targetNode.x) / 2);
        label.setAttribute('y', (edge.sourceNode.y + edge.targetNode.y) / 2 - 4);
        label.textContent = edge.label;
        svg.appendChild(label);
      }
      for (const node of nodes) {
        const show = visible.has(node.id);
        const g = document.createElementNS(ns, 'g');
        g.setAttribute('class', `node ${show ? '' : 'dim'} ${selectedId === node.id ? 'selected' : ''}`);
        g.setAttribute('transform', `translate(${node.x},${node.y})`);
        g.onclick = () => selectNode(node.id);
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('r', radius(node));
        circle.setAttribute('fill', colors[node.type] || '#94a3b8');
        g.appendChild(circle);
        const text = document.createElementNS(ns, 'text');
        text.setAttribute('x', radius(node) + 5);
        text.setAttribute('y', 4);
        text.textContent = trim(node.label, 34);
        g.appendChild(text);
        svg.appendChild(g);
      }
      renderList(visible);
      if (selectedId) renderDetail(nodeById.get(selectedId));
    }

    function radius(node) {
      if (node.type === 'ip') return 17;
      if (node.type === 'gap') return 13;
      if (node.type === 'record') return 12;
      return 10;
    }

    function renderList(visible) {
      const list = document.getElementById('nodeList');
      list.innerHTML = '';
      nodes.filter(n => visible.has(n.id)).slice(0, 80).forEach(node => {
        const item = document.createElement('div');
        item.className = 'item';
        item.onclick = () => selectNode(node.id);
        item.innerHTML = `<div class="item-title">${escapeHtml(node.label)}</div><div class="item-meta">${escapeHtml(node.type)} · ${escapeHtml(node.status || 'unknown')}</div>`;
        list.appendChild(item);
      });
    }

    function selectNode(id) {
      selectedId = id;
      renderDetail(nodeById.get(id));
      render();
    }

    function renderDetail(node) {
      const body = document.getElementById('detailBody');
      if (!node) {
        body.textContent = 'Select a node to inspect ROCEV data, artifact state, or gap details.';
        return;
      }
      const related = edges.filter(e => e.source === node.id || e.target === node.id).map(e => {
        const other = e.source === node.id ? nodeById.get(e.target) : nodeById.get(e.source);
        return `${e.source === node.id ? '->' : '<-'} ${e.label} ${other ? other.label : ''}`;
      });
      body.innerHTML = `
        <div><span class="badge">${escapeHtml(node.type)}</span><span class="badge ${escapeHtml(node.status || '')}">${escapeHtml(node.status || 'unknown')}</span></div>
        <h2>${escapeHtml(node.label)}</h2>
        <div class="sub">${escapeHtml(node.id)}</div>
        <h2>Relations</h2>
        <pre>${escapeHtml(related.join('\n') || 'none')}</pre>
        <h2>Data</h2>
        <pre>${escapeHtml(JSON.stringify(node.data || {}, null, 2))}</pre>
      `;
    }

    function getCss(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
    function trim(text, max) { text = String(text || ''); return text.length > max ? text.slice(0, max - 1) + '…' : text; }
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
