#!/bin/bash
# Brain Dream trigger -- fires on session exit

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Resolve BRAIN_DIR
if [ -d ".brain" ]; then
  BRAIN_DIR=".brain"
elif [ -n "$BRAIN_DIR" ]; then
  BRAIN_DIR="$BRAIN_DIR"
else
  BRAIN_DIR="$HOME/.brain"
fi

if bash "$SCRIPT_DIR/should-dream.sh" "$BRAIN_DIR"; then
  nohup claude -p "Run brain dream maintenance. Execute the brain-dream skill." \
    --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
    > "/tmp/brain-dream-$(date +%s).log" 2>&1 &
fi
