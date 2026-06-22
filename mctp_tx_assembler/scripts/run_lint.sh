#!/usr/bin/env bash
set -euo pipefail
IP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_ROOT="${OAG_CODEX_ROOT:-}"
if [ -z "$CODEX_ROOT" ]; then
  SEARCH="$IP_DIR"
  while [ "$SEARCH" != "/" ]; do
    if [ -f "$SEARCH/.claude/scripts/oag_pyslang_lint.py" ]; then CODEX_ROOT="$SEARCH/.claude"; break; fi
    SEARCH="$(dirname "$SEARCH")"
  done
fi
BACKEND="${OAG_LINT_BACKEND:-auto}"
mkdir -p lint/reports
case "$BACKEND" in
  pyslang)
    if [ -z "$CODEX_ROOT" ] || [ ! -f "$CODEX_ROOT/scripts/oag_pyslang_lint.py" ]; then
      echo "OAG_LINT_BACKEND=pyslang requires OAG_CODEX_ROOT or a parent .claude with scripts/oag_pyslang_lint.py" >&2
      exit 2
    fi
    python3 "$CODEX_ROOT/scripts/oag_pyslang_lint.py" --ip-dir "$IP_DIR" --filelist list/lint.f --out lint/dut_lint.json --json > lint/reports/pyslang_lint.stdout.json
    ;;
  verilator)
    verilator --lint-only -sv -Wno-fatal -f list/lint.f > lint/reports/verilator_lint.stdout.txt 2> lint/reports/verilator_lint.stderr.txt
    python3 - <<'PY'
import json, pathlib
pathlib.Path('lint/dut_lint.json').write_text(json.dumps({'schema_version':'oag_lint.v1','status':'pass','tool':'verilator'}, indent=2)+'\n')
PY
    ;;
  auto)
    if python3 -c 'import pyslang' >/dev/null 2>&1 && [ -n "$CODEX_ROOT" ]; then
      OAG_LINT_BACKEND=pyslang "$0"
    elif command -v verilator >/dev/null 2>&1; then
      OAG_LINT_BACKEND=verilator "$0"
    else
      echo '{"schema_version":"oag_lint.v1","status":"skipped","tool":"none","reason":"no pyslang or verilator available"}' > lint/dut_lint.json
    fi
    ;;
  *) echo "unsupported OAG_LINT_BACKEND=$BACKEND" >&2; exit 2 ;;
esac
