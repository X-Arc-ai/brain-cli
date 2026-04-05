#!/bin/bash
# Stop hook: verify cognitive loop was executed

INPUT=$(cat)

PARSED=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('stop_hook_active', False))
print(data.get('transcript_path', ''))
" 2>/dev/null)

STOP_ACTIVE=$(echo "$PARSED" | head -1)
TRANSCRIPT=$(echo "$PARSED" | tail -1)

if [ "$STOP_ACTIVE" = "True" ]; then
  exit 0
fi

if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  exit 0
fi

LAST_USER_MSG=$(tac "$TRANSCRIPT" | grep -m1 '"role":"user"' | head -1)
MSG_LENGTH=${#LAST_USER_MSG}

if [ "$MSG_LENGTH" -lt 80 ]; then
  exit 0
fi

LAST_USER_LINE=$(grep -n '"role":"user"' "$TRANSCRIPT" 2>/dev/null | tail -1 | cut -d: -f1)
if [ -n "$LAST_USER_LINE" ]; then
  SKILL_THIS_TURN=$(tail -n +"$LAST_USER_LINE" "$TRANSCRIPT" 2>/dev/null | grep -c '"Skill"\|"skill":' || echo "0")
  if [ "$SKILL_THIS_TURN" -gt "0" ]; then
    exit 0
  fi
fi

BRAIN_CALLS=$(grep -c 'brain scan\|brain write\|brain context\|brain search\|brain signals\|brain verify\|brain get\|brain query\|brain dream' "$TRANSCRIPT" 2>/dev/null || echo "0")

if [ "$BRAIN_CALLS" -eq "0" ]; then
  echo '{"decision": "block", "reason": "Brain was never queried or updated. Run: (1) brain scan for topic, (2) dual-write if new info shared."}' >&2
  exit 2
fi

CONTEXT_EDITS=$(grep -c '"Edit"\|"Write"' "$TRANSCRIPT" 2>/dev/null || echo "0")
BRAIN_WRITES=$(grep -c 'brain write' "$TRANSCRIPT" 2>/dev/null || echo "0")

if [ "$CONTEXT_EDITS" -gt "0" ] && [ "$BRAIN_WRITES" -eq "0" ]; then
  echo '{"decision": "block", "reason": "Files were edited but brain was not written to. Complete the dual-write."}' >&2
  exit 2
fi

exit 0
