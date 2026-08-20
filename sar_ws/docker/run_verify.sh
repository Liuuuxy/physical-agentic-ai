#!/bin/bash
# Host-side verification: start the sim container, wait for bringup, check
# services, run the smoke mission, then tear down.
set -u
NAME=sar-verify
LOGDIR="$(cd "$(dirname "$0")" && pwd)"

docker rm -f $NAME >/dev/null 2>&1

echo "[verify] starting container..."
docker run -d --name $NAME --shm-size=1g sar-sim:humble \
  bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && ros2 launch sar_gazebo sar_simulation.launch.py headless:=1 px4_autopilot_dir:=/px4/PX4-Autopilot" \
  || exit 1

echo "[verify] waiting 45 s for bringup..."
sleep 45

echo "[verify] --- service list ---"
docker exec $NAME bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && timeout 30 ros2 service list" \
  | tee "$LOGDIR/service_list.txt" | grep -E '/drone/|/rover/'

echo "[verify] --- smoke mission ---"
T0=$(date +%s)
docker exec $NAME bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && python3 /sar_ws/smoke_mission.py" \
  | tee "$LOGDIR/smoke_result.txt"
RC=${PIPESTATUS[0]}
T1=$(date +%s)
echo "[verify] smoke mission rc=$RC wall=$((T1-T0))s"

echo "[verify] --- container log tail ---"
docker logs --tail 60 $NAME > "$LOGDIR/container.log" 2>&1

docker rm -f $NAME >/dev/null 2>&1
exit $RC
