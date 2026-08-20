#!/usr/bin/env bash
# One-command entry point: launches the Gazebo/PX4/TurtleBot3 simulation,
# waits for the drone/rover ROS 2 services to come up, runs the CrewAI
# search-and-rescue mission, then shuts the simulation down.
#
# Usage:
#   ./run_mission.sh                                        # single run, GUI
#   ./run_mission.sh headless:=1                            # single run, headless
#   ./run_mission.sh --runs 5                               # 5 repeated runs
#   ./run_mission.sh --runs 5 --csv out.csv                     # 5 runs + CSV
#
# --- Nominal run set (Run Set 1: grounding / assignment / task outcome) ---
#   ./run_mission.sh --scenario a --config full     --fault none --runs 40 --csv nominal_full_a.csv
#   ./run_mission.sh --scenario a --config no_gate  --fault none --runs 40 --csv nominal_no_gate_a.csv
#   ./run_mission.sh --scenario a --config llm_only --fault none --runs 40 --csv nominal_llm_only_a.csv
#
# --- Fault-injection run set (Run Set 2: coordination / safety) ---
#   ./run_mission.sh --scenario a --config full     --fault mixed --runs 40 --csv fault_full_a.csv
#   ./run_mission.sh --scenario a --config no_gate  --fault mixed --runs 40 --csv fault_no_gate_a.csv
#   ./run_mission.sh --scenario a --config llm_only --fault mixed --runs 40 --csv fault_llm_only_a.csv
#
# Arguments beginning with '--' (--runs, --csv, --config, --fault, --scenario) are
# forwarded to the Python mission script. --scenario ALSO resolves to a
# world_file:=/rubble_json:= pair forwarded to ros2 launch, so the Gazebo
# world and the rover's A* obstacle map match the chosen scenario
# (see sar_crew/sar_crew/scenarios.py). All other arguments go to ros2 launch.
# --fault mixed randomly cycles through all 4 non-none fault modes per run.
set -e

SAR_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Make sure `python3` resolves to the system interpreter (3.10) for ROS
# subprocesses like spawn_entity.py. If e.g. Anaconda's python3 (3.12)
# comes first on PATH, spawn_entity.py can't load rclpy's compiled
# extension and silently fails to spawn the TurtleBot3 - leaving the
# rover with no /odom and the mission unable to navigate it.
export PATH="/usr/bin:$PATH"
export DISPLAY="${DISPLAY:-:0}"

source /opt/ros/humble/setup.bash
source "$SAR_WS/install/setup.bash"

# Split arguments: --runs / --csv / --config / --fault / --scenario go to the
# Python mission script; everything else goes to ros2 launch.
LAUNCH_ARGS=()
MISSION_ARGS=()
SCENARIO="a"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --runs|--csv|--config|--fault|--fault-set)
            MISSION_ARGS+=("$1" "$2"); shift 2 ;;
        --runs=*|--csv=*|--config=*|--fault=*|--fault-set=*)
            MISSION_ARGS+=("$1"); shift ;;
        --scenario)
            SCENARIO="$2"; MISSION_ARGS+=("$1" "$2"); shift 2 ;;
        --scenario=*)
            SCENARIO="${1#*=}"; MISSION_ARGS+=("$1"); shift ;;
        *)
            LAUNCH_ARGS+=("$1"); shift ;;
    esac
done

# Resolve --scenario into world_file:=/rubble_json:= launch args.
# scenarios.py is pure stdlib (no rclpy/crewai deps), so plain python3 works.
SCENARIO_INFO=$(python3 -c "
import sys, json
sys.path.insert(0, '$SAR_WS/src/sar_crew')
from sar_crew.scenarios import get_scenario
sc = get_scenario('$SCENARIO')
print(sc['world_file'])
print(json.dumps(sc['rubble'], separators=(',', ':')))
")
WORLD_FILE=$(echo "$SCENARIO_INFO" | sed -n '1p')
RUBBLE_JSON=$(echo "$SCENARIO_INFO" | sed -n '2p')
LAUNCH_ARGS+=("world_file:=$WORLD_FILE" "rubble_json:=$RUBBLE_JSON")
echo "Scenario '$SCENARIO' -> world_file=$WORLD_FILE"

cleanup() {
    echo "Shutting down simulation..."
    if [[ -n "$LAUNCH_PID" ]] && kill -0 "$LAUNCH_PID" 2>/dev/null; then
        kill -INT "$LAUNCH_PID" 2>/dev/null
        wait "$LAUNCH_PID" 2>/dev/null
    fi
    # ros2 launch's SIGINT handling doesn't always reach every descendant of
    # the `make px4_sitl ...` process tree (gzserver/gzclient/px4/sitl_run.sh
    # nest several levels deep) - clean those up directly too.
    pkill -9 -f "gzserver|gzclient|px4_sitl_default/bin/px4|sitl_run.sh|make px4_sitl|mavros_node|drone_controller_node|rover_controller_node|robot_state_publisher|spawn_entity" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting simulation (ros2 launch sar_gazebo sar_simulation.launch.py ${LAUNCH_ARGS[*]})..."
ros2 launch sar_gazebo sar_simulation.launch.py "${LAUNCH_ARGS[@]}" &
LAUNCH_PID=$!

echo "Waiting for drone/rover services to come up (this can take a minute)..."
until ros2 service list 2>/dev/null | grep -q "^/drone/takeoff$" \
   && ros2 service list 2>/dev/null | grep -q "^/drone/search_area$" \
   && ros2 service list 2>/dev/null | grep -q "^/drone/fly_to$" \
   && ros2 service list 2>/dev/null | grep -q "^/rover/navigate_to$"; do
    if ! kill -0 "$LAUNCH_PID" 2>/dev/null; then
        echo "Simulation exited before services came up." >&2
        exit 1
    fi
    sleep 2
done
echo "Services detected - waiting 20s for full node initialization..."
sleep 20

# Extra check: wait until MAVROS reports FCU connected (PX4 SITL ready).
# Times out after 60 s — if it never connects, something is wrong with PX4.
echo "Waiting for MAVROS FCU connection..."
MAVROS_TIMEOUT=60
until ros2 topic echo /mavros/state --once 2>/dev/null | grep -q "connected: true"; do
    MAVROS_TIMEOUT=$((MAVROS_TIMEOUT - 2))
    if [[ $MAVROS_TIMEOUT -le 0 ]]; then
        echo "WARNING: MAVROS FCU did not connect in time — drone may not arm." >&2
        break
    fi
    sleep 2
done
echo "MAVROS FCU ready (or timeout reached). Starting mission..."

source "$SAR_WS/.venv/bin/activate"
cd "$SAR_WS/src/sar_crew"
python3 -m sar_crew.run_mission "${MISSION_ARGS[@]}"
