from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
    JsonObject = dict[str, JsonValue]
else:
    JsonValue = str
    JsonObject = dict


def json_strings(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def build_prompt_contract(dispatch: JsonObject) -> str:
    lines = [
        "OAG DISPATCH",
        f"- dispatch_id: {dispatch['dispatch_id']}",
        f"- dispatch_path: {dispatch['dispatch_path']}",
        f"- agent_type: {dispatch['agent_type']}",
        f"- ip_dir: {dispatch['ip_dir']}",
        f"- stage: {dispatch['stage']}",
        f"- receipt_path: {dispatch['receipt_path']}",
        f"- allowed_write_paths: {', '.join(json_strings(dispatch['allowed_write_paths'])) or '(none)'}",
        f"- allowed_tool_side_effects: {', '.join(json_strings(dispatch['allowed_tool_side_effects'])) or '(none)'}",
    ]
    if dispatch.get("wavefront_run_id"):
        lines.extend(
            [
                f"- wavefront_run_id: {dispatch['wavefront_run_id']}",
                f"- task_id: {dispatch.get('task_id') or '(none)'}",
                f"- ownership_mode: {dispatch.get('ownership_mode') or '(none)'}",
            ]
        )
    lines.extend(
        [
            "Receipt requirements:",
            "- include dispatch_id and dispatch_path exactly as above",
            "- include wavefront_run_id/task_id when this dispatch belongs to a wavefront task",
            "- list changed_paths and generated_side_effects separately",
            "- use HANDOFF_PASS, STATIC_HANDOFF_PASS, RTL_HANDOFF_PASS, FAIL, BLOCKED, or INCONCLUSIVE",
            "- set may_claim_complete=false",
            "- end with OAG_EVIDENCE_RECORDED: <relative-path>",
        ]
    )
    return "\n".join(lines)
