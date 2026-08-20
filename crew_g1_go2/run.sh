#!/usr/bin/env bash
# Convenience launcher: sources workspaces and starts the system.
# Usage:
#   ./run.sh                          # interactive REPL
#   ./run.sh "grab the box from table_a"  # single command

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source environment
source setup_env.sh

# Verify OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY is not set."
    echo "Export it first:  export OPENAI_API_KEY=sk-..."
    exit 1
fi

# Run
exec /usr/bin/python3 main.py "$@"
