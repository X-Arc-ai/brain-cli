#!/bin/bash
# Pre-write structural validation (command hook)
# Exit 0 = pass, Exit 2 = block

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tool_input = data.get('tool_input', {})
cmd = tool_input.get('command', '')
print(cmd)
" 2>/dev/null)

if ! echo "$COMMAND" | grep -q "brain write"; then
  exit 0
fi

JSON_DATA=$(echo "$COMMAND" | python3 -c "
import sys, re, json
cmd = sys.stdin.read().strip()
match = re.search(r\"--json-data\s+'(.*?)'\", cmd, re.DOTALL)
if not match:
    match = re.search(r'--json-data\s+\"(.*?)\"', cmd, re.DOTALL)
if match:
    print(match.group(1))
else:
    match = re.search(r'--file\s+(\S+)', cmd)
    if match:
        try:
            with open(match.group(1)) as f:
                print(f.read())
        except:
            pass
" 2>/dev/null)

if [ -z "$JSON_DATA" ]; then
  exit 0
fi

VIOLATIONS=$(echo "$JSON_DATA" | python3 -c "
import sys, json

try:
    data = json.loads(sys.stdin.read())
except:
    sys.exit(0)

if isinstance(data, dict):
    data = [data]

violations = []
create_nodes = {}
create_edges = []

for op in data:
    op_type = op.get('op', '')
    if op_type == 'create_node':
        create_nodes[op.get('id', '')] = op.get('type', '')
    elif op_type == 'create_edge':
        create_edges.append({'from': op.get('from', ''), 'to': op.get('to', ''), 'verb': op.get('verb', '')})

PERSON_VERBS = {'assigned to', 'owned by', 'managed by'}
SCOPE_VERBS = {'goal for', 'task of', 'subtask of', 'part of'}
IMPACT_VERBS = {'affects', 'blocks', 'blocked by'}

for node_id, node_type in create_nodes.items():
    node_edges = [e for e in create_edges if e['from'] == node_id or e['to'] == node_id]
    edge_verbs = {e['verb'].lower() for e in node_edges}
    if node_type in ('goal', 'task'):
        if not (edge_verbs & PERSON_VERBS):
            violations.append(f'EDGE INCOMPLETE: {node_id} ({node_type}) missing person edge (assigned to / owned by)')
        if not (edge_verbs & SCOPE_VERBS):
            violations.append(f'EDGE INCOMPLETE: {node_id} ({node_type}) missing scope edge (goal for / task of)')
    elif node_type == 'blocker':
        if not (edge_verbs & IMPACT_VERBS):
            violations.append(f'EDGE INCOMPLETE: {node_id} (blocker) missing impact edge (affects / blocks)')

if violations:
    for v in violations:
        print(v)
" 2>/dev/null)

if [ -n "$VIOLATIONS" ]; then
  echo "BRAIN WRITE STRUCTURAL VALIDATION FAILED:" >&2
  echo "$VIOLATIONS" >&2
  echo "" >&2
  echo "Add the missing edges to the batch before writing." >&2
  exit 2
fi

exit 0
