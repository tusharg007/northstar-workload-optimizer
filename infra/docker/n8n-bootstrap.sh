#!/bin/sh
set -eu

SOURCE_DIR=/workflows-source
IMPORT_DIR=/tmp/northstar-workflows
EXPECTED=10

rm -rf "$IMPORT_DIR"
mkdir -p "$IMPORT_DIR"

found=0
for source in "$SOURCE_DIR"/*.json; do
  [ -f "$source" ] || continue
  target="$IMPORT_DIR/$(basename "$source")"
  sed \
    -e 's#http://127\.0\.0\.1:8000#http://api:8000#g' \
    -e 's#http://127\.0\.0\.1:9010#http://notification-sink:9010#g' \
    "$source" > "$target"
  found=$((found + 1))
done

if [ "$found" -ne "$EXPECTED" ]; then
  echo "FAIL: expected $EXPECTED workflow files, found $found" >&2
  exit 1
fi

n8n import:workflow --separate --input="$IMPORT_DIR"

for workflow_id in \
  northstarGlobalErrorHandler \
  northstarApprovalNotificationService \
  northstarReliabilityDispatcher \
  northstarDeadLetterReplay \
  northstarProcessExpenseService \
  northstarRecordDecisionService \
  northstarApprovalOrchestrator \
  northstarApprovalSLAMonitor \
  northstarExpenseIntake \
  northstarApprovalDecision
do
  n8n publish:workflow --id="$workflow_id"
done

actual="$(n8n list:workflow --onlyId | grep -c '^northstar')"
if [ "$actual" -ne "$EXPECTED" ]; then
  echo "FAIL: expected $EXPECTED North Star workflows after import, found $actual" >&2
  exit 1
fi

echo "PASS: imported and published exactly $EXPECTED North Star workflows"
