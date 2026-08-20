#!/usr/bin/env bash
# Source all required workspaces for the crew_g1_go2 system.
# Run:  source setup_env.sh

# Deactivate Conda if active – ROS 2 Humble requires system Python 3.10
if [ -n "$CONDA_DEFAULT_ENV" ] && [ "$CONDA_DEFAULT_ENV" != "base" ]; then
    conda deactivate
fi
if command -v conda &>/dev/null && [ "${CONDA_SHLVL:-0}" -gt 0 ]; then
    conda deactivate 2>/dev/null || true
fi

# Where unitree_ros2 / ros2_ws / autonomy_stack_go2 are installed.
# Override if they do not live directly under $HOME:
#   export ROS_WS_ROOT=/opt/robot
# Core Unitree ROS2 workspaces
source "${ROS_WS_ROOT:-$HOME}"/unitree_ros2/cyclonedds_ws/install/setup.bash
source "${ROS_WS_ROOT:-$HOME}"/unitree_ros2/example/install/setup.bash
source "${ROS_WS_ROOT:-$HOME}"/ros2_ws/install/setup.bash

# Go2 autonomy stack
source "${ROS_WS_ROOT:-$HOME}"/autonomy_stack_go2/install/setup.bash

# Add project root to PYTHONPATH so local packages resolve
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

echo "✓ ROS2 workspaces sourced."
echo "✓ PYTHONPATH includes ${SCRIPT_DIR}"
echo ""
echo "Next steps:"
echo "  export OPENAI_API_KEY=<your-key>"
echo "  python3 main.py"
