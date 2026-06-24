#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from oag_dispatch_support import JsonObject, create_dispatch, issue
from oag_dispatch_verify import verify_dispatch


def print_result(result: JsonObject, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print(f"PASS {result['schema_version']}")
    else:
        print(f"FAIL {result['schema_version']}", file=sys.stderr)
        for item in result.get("issues", []):
            if isinstance(item, dict):
                suffix = f" ({item['path']})" if item.get("path") else ""
                print(f"- {item['code']}: {item['message']}{suffix}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify OAG native-subagent dispatch records.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a dispatch record before native subagent spawn.")
    create.add_argument("--ip-dir", required=True)
    create.add_argument("--agent-type", required=True)
    create.add_argument("--role-kind", choices=["core", "custom"])
    create.add_argument("--role-name")
    create.add_argument("--registered-id")
    create.add_argument("--stage", required=True)
    create.add_argument("--owned-obligation", action="append")
    create.add_argument("--contract", action="append")
    create.add_argument("--allowed-write-path", action="append")
    create.add_argument("--allowed-tool-side-effect", action="append")
    create.add_argument("--receipt-path", required=True)
    create.add_argument("--wavefront-run-id")
    create.add_argument("--task-id")
    create.add_argument("--ownership-mode", choices=["none", "exclusive_file", "integration_owner"])
    create.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify", help="Verify a dispatch against a child receipt and actual path delta.")
    verify.add_argument("--dispatch", required=True)
    verify.add_argument("--receipt", required=True)
    verify.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        result = create_dispatch(args) if args.command == "create" else verify_dispatch(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": "oag_dispatch_error.v1",
            "status": "fail",
            "issues": [issue("EXCEPTION", str(exc))],
        }
    print_result(result, bool(getattr(args, "json", False)))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
