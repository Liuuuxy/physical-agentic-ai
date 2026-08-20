#!/usr/bin/env bash
# Launches the Gazebo simulation with the dual-capable demo world (single
# wall obstacle, no victim/search needed), then runs the platform-selection
# experiment. Self-contained — does not touch the main ablation pipeline.
#
# Usage:
#   ./run_dual_mission.sh --target rover_easy --runs 5 --csv dual_rover_easy.csv
#   ./run_dual_mission.sh --target drone_easy --runs 5 --csv dual_drone_easy.csv
#   ./run_dual_mission.sh --target ambiguous  --runs 5 --csv dual_ambiguous.csv
#   ./run_dual_mission.sh headless:=1 --target drone_easy --runs 5
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAR_WS="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

export PATH="/usr/bin:$PATH"
export DISPLAY="${DISPLAY:-:0}"

source /opt/ros/humble/setup.bash
source "$SAR_WS/install/setup.bash"

LAUNCH_ARGS=()
MISSION_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target|--runs|--csv)
            MISSION_ARGS+=("$1" "$2"); shift 2 ;;
        --target=*|--runs=*|--csv=*)
            MISSION_ARGS+=("$1"); shift ;;
        *)
            LAUNCH_ARGS+=("$1"); shift ;;
    esac
done

# Dual-capable world: single wall at (3,0), no victim model needed.
RUBBLE_JSON='[[3.0,0.0,4.0,0.3,1.5708]]'
LAUNCH_ARGS+=("world_file:=sar_world_dual.world" "rubble_json:=$RUBBLE_JSON")

cleanup() {
    echo "Shutting down simulation..."
    if [[ -n "$LAUNCH_PID" ]] && kill -0 "$LAUNCH_PID" 2>/dev/null; then
        kill -INT "$LAUNCH_PID" 2>/dev/null
        wait "$LAUNCH_PID" 2>/dev/null
    fi
    pkill -9 -f "gzserver|gzclient|px4_sitl_default/bin/px4|sitl_run.sh|make px4_sitl|mavros_node|drone_controller_node|rover_controller_node|robot_state_publisher|spawn_entity" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting simulation (ros2 launch sar_gazebo sar_simulation.launch.py ${LAUNCH_ARGS[*]})..."
ros2 launch sar_gazebo sar_simulation.launch.py "${LAUNCH_ARGS[@]}" &
LAUNCH_PID=$!

echo "Waiting for drone/rover services to come up..."
until ros2 service list 2>/dev/null | grep -q "^/drone/takeoff$" \
   && ros2 service list 2>/dev/null | grep -q "^/drone/fly_to$" \
   && ros2 service list 2>/dev/null | grep -q "^/rover/navigate_to$"; do
    if ! kill -0 "$LAUNCH_PID" 2>/dev/null; then
        echo "Simulation exited before services came up." >&2
        exit 1
    fi
    sleep 2
done
echo "Services detected - waiting 10s for full node initialization..."
sleep 10

source "$SAR_WS/.venv/bin/activate"
cd "$SAR_WS/src/sar_crew"
python3 -m sar_crew.experiments.dual_capable.run_mission "${MISSION_ARGS[@]}"
