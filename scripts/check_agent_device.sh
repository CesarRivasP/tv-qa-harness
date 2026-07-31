#!/usr/bin/env bash
# scripts/check_agent_device.sh — verify the interaction layer is operational.
set -euo pipefail

node_ver=$(node --version | sed 's/^v//')
node_major=${node_ver%%.*}
node_minor=$(echo "$node_ver" | cut -d. -f2)
if [ "$node_major" -lt 22 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; }; then
  echo "Node >= 22.12 required, found v$node_ver" >&2
  exit 1
fi
if ! command -v agent-device >/dev/null; then
  echo "agent-device not found. Install: npm install -g agent-device@latest" >&2
  exit 1
fi
agent-device doctor
