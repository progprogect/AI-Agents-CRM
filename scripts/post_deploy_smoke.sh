#!/usr/bin/env bash
# post_deploy_smoke.sh — post-deploy smoke test runner
#
# Usage:
#   ./scripts/post_deploy_smoke.sh <BASE_URL> <ADMIN_TOKEN>
#
# Examples:
#   ./scripts/post_deploy_smoke.sh https://your-app.railway.app eyJhbGci...
#   BASE_URL=https://app.railway.app TOKEN=$ADMIN_TOKEN ./scripts/post_deploy_smoke.sh
#
# Environment variables (alternative to positional args):
#   BASE_URL     — app base URL (no trailing slash)
#   ADMIN_TOKEN  — JWT or static admin token
#   WAIT_SECONDS — seconds to wait after deploy before testing (default: 180)
#   SMOKE_TIMEOUT — curl max-time for the smoke request in seconds (default: 60)
#
# Exit codes:
#   0 — all smoke tests passed
#   1 — one or more tests failed or endpoint unreachable

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-}}"
ADMIN_TOKEN="${2:-${ADMIN_TOKEN:-}}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-60}"

# ---- Validate args ----
if [[ -z "$BASE_URL" ]]; then
  echo "ERROR: BASE_URL is required (positional arg 1 or env var BASE_URL)"
  exit 1
fi
if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "ERROR: ADMIN_TOKEN is required (positional arg 2 or env var ADMIN_TOKEN)"
  exit 1
fi

BASE_URL="${BASE_URL%/}"  # strip trailing slash

echo "=== Post-deploy smoke test ==="
echo "Target : $BASE_URL"
echo "Waiting: ${WAIT_SECONDS}s for deploy to stabilise..."
sleep "$WAIT_SECONDS"

echo ""
echo "Running smoke test (timeout=${SMOKE_TIMEOUT}s)..."
HTTP_CODE=$(curl -s -o /tmp/smoke_result.json -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/internal/smoke-test" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  --max-time "$SMOKE_TIMEOUT")

if [[ "$HTTP_CODE" -eq 000 ]]; then
  echo "ERROR: Could not reach $BASE_URL (connection refused or timeout)"
  exit 1
fi

if [[ "$HTTP_CODE" -ne 200 ]]; then
  echo "ERROR: Smoke endpoint returned HTTP $HTTP_CODE"
  cat /tmp/smoke_result.json
  echo ""
  exit 1
fi

echo ""
echo "--- Smoke test result ---"
python3 - <<'PYEOF'
import json, sys

with open("/tmp/smoke_result.json") as f:
    r = json.load(f)

overall = r.get("overall", "UNKNOWN")
print(f"Overall : {overall}")
print(f"Elapsed : {r.get('elapsed_ms', '?')} ms")
print(f"Run by  : {r.get('run_by', '?')}")
print()

all_passed = True
for key, val in r.items():
    if not isinstance(val, dict) or "passed" not in val:
        continue
    status = "PASS" if val["passed"] else "FAIL"
    print(f"  [{status}] {key}: {val.get('detail', '')} ({val.get('elapsed_ms', '?')} ms)")
    if not val["passed"]:
        all_passed = False

print()
if all_passed and overall == "PASS":
    print("✓ All smoke tests passed.")
    sys.exit(0)
else:
    print("✗ One or more smoke tests FAILED.")
    sys.exit(1)
PYEOF
