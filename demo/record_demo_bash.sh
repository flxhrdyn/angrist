#!/usr/bin/env bash
# demo/record_demo_bash.sh
# Records a real terminal demo using VHS + local mock LLM server.
#
# Run from Git Bash (from repo root):
#   bash demo/record_demo_bash.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "Starting mock LLM server on port 8765..."
python demo/mock_server.py 8765 &
MOCK_PID=$!
sleep 2

cleanup() {
    echo "Stopping mock server (PID $MOCK_PID)..."
    kill "$MOCK_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "Mock server up. Recording with VHS..."

ANGRIST_LLM_BASE_URL=http://127.0.0.1:8765/v1 \
ANGRIST_LLM_API_KEY=mock-key \
ANGRIST_LLM_MODEL=gpt-oss-mock \
vhs demo/demo.tape

echo "Demo saved to demo/demo.gif"
