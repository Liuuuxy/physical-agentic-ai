# sar-sim:humble — air-ground SAR simulation in Docker

ROS2 Humble + Gazebo Classic 11 + PX4 SITL (release/1.14, gazebo-classic_iris)
+ MAVROS + TurtleBot3 waffle, with the sar_ws packages (sar_msgs,
sar_robot_control, sar_gazebo) built into /sar_ws.

## Build

    docker build -t sar-sim:humble .

(sar_src/ is a copy of sar_ws/src minus sar_crew; refresh it with rsync from
the real workspace before rebuilding if sources changed.)

## Run the simulation (headless)

    docker run -d --name sar --shm-size=1g sar-sim:humble \
      bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && \
               ros2 launch sar_gazebo sar_simulation.launch.py headless:=1 px4_autopilot_dir:=/px4/PX4-Autopilot"

Wait ~40 s (PX4+Gazebo start immediately; TB3 spawns at t=15 s, MAVROS at
t=20 s, controllers at t=25 s).

## Check services

    docker exec sar bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && ros2 service list" \
      | grep -E '/drone/|/rover/'

Expected: /drone/takeoff /drone/fly_to /drone/search_area /drone/land
/drone/perception_query /rover/navigate_to /rover/stop

## Scripted smoke mission

    docker exec sar bash -c "source /opt/ros/humble/setup.bash && source /sar_ws/install/setup.bash && python3 /sar_ws/smoke_mission.py"

Takeoff to 5 m -> lawnmower search of [-5.5,5.5]^2 -> rover drives to the
reported victim -> prints one JSON line with per-stage results and timings.
Victim ground truth in sar_world.world is (5,5).

Or manually:

    ros2 service call /drone/takeoff sar_msgs/srv/Takeoff "{altitude: 5.0}"
    ros2 service call /drone/search_area sar_msgs/srv/SearchArea \
      "{x_min: -5.5, x_max: 5.5, y_min: -5.5, y_max: 5.5, altitude: 5.0}"
    ros2 service call /rover/navigate_to sar_msgs/srv/NavigateTo \
      "{x: <victim_x>, y: <victim_y>, tolerance: 0.0}"

## RAO live missions (crew_sar)

The RAO framework in `sar_ws/crew_sar` can drive this simulation for real:
copy the in-container skill helper in, then run the mission runner from the
host (needs the `physical_agent` conda env + `OPENAI_API_KEY`):

    docker cp rao_skill_call.py sar:/tmp/rao_skill_call.py
    cd ../crew_sar
    python run_gazebo_mission.py --baseline rao \
      --request "A hiker is missing in the search zone x from -5.5 to 5.5, y from -5.5 to 5.5. Fly the drone over the zone and send the ground rover to the victim once located."

`--fault nan_transmission|missed_detection` injects the perception faults on
the structured channel (host-side, in `ros_bridge/gazebo_bridge.py`); under
`--baseline rao` the dispatch gate refuses the rover step (`no_target_fix`).
Restart the container between missions for a clean robot state.

## Teardown

    docker rm -f sar

## One-shot verification (build must exist)

    ./run_verify.sh

Note: the Docker build context needs a `sar_src/` snapshot of `sar_ws/src`
(minus `sar_crew`); it is not committed here — regenerate with
`rsync -a --exclude sar_crew ../src/ sar_src/` before building.
