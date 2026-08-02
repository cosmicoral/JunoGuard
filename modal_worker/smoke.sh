#!/usr/bin/env bash
# Smoke test for the deployed detonation worker.
#   ./modal_worker/smoke.sh https://<you>--junoguard-detonation-web.modal.run [package]
#
# Detonates one package and prints the queued call id. The report itself is
# delivered to the gateway's callback, not to this script.
set -euo pipefail

URL="${1:-}"
PKG="${2:-@ossprey/test-package}"
if [ -z "$URL" ]; then
  echo "usage: $0 <worker-url> [package]" >&2
  exit 2
fi
: "${MODAL_DETONATE_TOKEN:?set MODAL_DETONATE_TOKEN for the worker}"
: "${PUBLIC_BASE_URL:?set PUBLIC_BASE_URL so the report has somewhere to go}"

echo "health:"
curl -fsS "$URL/" | sed 's/^/  /'

echo
echo "detonating $PKG:"
curl -fsS -X POST "$URL/detonate" \
  -H "Authorization: Bearer $MODAL_DETONATE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"action_id\":\"smoke-$(date +%s)\",\"project_id\":\"smoke\",\"package\":\"$PKG\",\"ecosystem\":\"npm\",\"callback_url\":\"$PUBLIC_BASE_URL/v1/detonations/smoke\"}" \
  | sed 's/^/  /'
echo
echo "Expect 202 + a call id. Watch the run with: modal app logs junoguard-detonation"
