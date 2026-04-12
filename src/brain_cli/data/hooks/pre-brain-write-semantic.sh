#!/usr/bin/env bash
# Semantic pre-write validator for brain write operations.
# Ships DISABLED by default. To enable, add to settings.local.json:
#
#   {
#     "hooks": {
#       "PreToolUse": [
#         {
#           "type": "command",
#           "command": "bash /path/to/.brain/hooks/pre-brain-write-semantic.sh",
#           "timeout": 120000,
#           "matcher": "Bash"
#         }
#       ]
#     }
#   }
#
# Requires: claude CLI on PATH

set -euo pipefail

# Read tool input from stdin
INPUT=$(cat)

# Extract the command being run
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

# Only validate brain write commands
if [[ -z "$COMMAND" ]] || [[ "$COMMAND" != *"brain write"* ]]; then
    exit 0
fi

# Extract the JSON data from the command
JSON_DATA=$(echo "$COMMAND" | grep -oP "'(\{.*\}|\[.*\])'" | tr -d "'" || true)
if [[ -z "$JSON_DATA" ]]; then
    # Try double-quoted JSON
    JSON_DATA=$(echo "$COMMAND" | grep -oP '"(\{.*\}|\[.*\])"' | sed 's/^"//;s/"$//' || true)
fi

if [[ -z "$JSON_DATA" ]]; then
    # No parseable JSON data, allow the write
    exit 0
fi

# Load the prompt template
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/pre-brain-write.md"

if [[ ! -f "$PROMPT_FILE" ]]; then
    # Prompt template missing, allow the write
    exit 0
fi

PROMPT=$(cat "$PROMPT_FILE")

# Run the validator via claude -p
RESULT=$(echo "$PROMPT

## Proposed Operations

\`\`\`json
$JSON_DATA
\`\`\`" | claude -p --output-format json 2>/dev/null || echo '{"decision": "approve"}')

# Parse the decision
DECISION=$(echo "$RESULT" | jq -r '.decision // "approve"' 2>/dev/null || echo "approve")

if [[ "$DECISION" == "block" ]]; then
    REASON=$(echo "$RESULT" | jq -r '.reason // "Semantic validation failed"' 2>/dev/null || echo "Semantic validation failed")
    echo "BLOCKED by semantic validator: $REASON" >&2
    exit 2
fi

exit 0
