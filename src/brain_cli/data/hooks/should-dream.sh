#!/bin/bash
# Exit 0 = should dream, Exit 1 = skip

BRAIN_DIR="${1:-$HOME/.brain}"
LAST_DREAM_FILE="$BRAIN_DIR/.last-dream"
THRESHOLD_HOURS=24

if [ ! -f "$LAST_DREAM_FILE" ]; then
  exit 0
fi

LAST_DREAM=$(cat "$LAST_DREAM_FILE")
NOW=$(date +%s)
ELAPSED=$(( (NOW - LAST_DREAM) / 3600 ))

if [ "$ELAPSED" -ge "$THRESHOLD_HOURS" ]; then
  exit 0
fi

exit 1
