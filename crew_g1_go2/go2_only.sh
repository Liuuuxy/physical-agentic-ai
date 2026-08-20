#!/usr/bin/env bash
# Run CrewAI navigation controller for Go2 only.
# G1 publishers are fully disabled – safe when G1 is absent or powered off.
#
# Usage:
#   ./go2_only.sh                        # interactive REPL
#   ./go2_only.sh "go to room_b"         # single command
#
# Prerequisites (run in a separate terminal first):
#   conda deactivate
#   source /opt/ros/humble/setup.bash
#   source ~/unitree_ros2/cyclonedds_ws/install/setup.bash
#   source ~/unitree_ros2/example/install/setup.bash
#   source ~/ros2_ws/install/setup.bash
#   source ~/autonomy_stack_go2/install/setup.bash
#   cd ~/autonomy_stack_go2 && ./system_real_robot.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source setup_env.sh

if [ -z "$OPENAI_API_KEY" ]; then
    echo "ERROR: OPENAI_API_KEY is not set."
    echo "Export it first:  export OPENAI_API_KEY=sk-..."
    exit 1
fi

export GO2_ONLY=1
exec /usr/bin/python3 main.py "$@"
