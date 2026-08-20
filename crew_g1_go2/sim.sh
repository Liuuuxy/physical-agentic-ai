#!/usr/bin/env bash
# Run the CrewAI system in simulation mode (no ROS2, no robot hardware).
# Usage:
#   ./sim.sh                                   # interactive REPL
#   ./sim.sh "grab from table then go to room_b"  # single command

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY is not set."
    echo "Export it first:  export OPENAI_API_KEY=sk-..."
    exit 1
fi

export CREW_SIM=1
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Use whatever python3 is active (Conda base is fine for sim – no ROS2 needed)
exec python3 main.py "$@"
