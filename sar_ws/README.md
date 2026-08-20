> **Reading this file.** The setup instructions below describe the original
> bare-metal host the system was developed on. Read `~/sar_ws` as *this*
> `sar_ws/` directory. Two things referenced here are **not** part of this
> release: the one-time provisioning script `~/sar_setup_sudo.sh`, and the
> pre-built `~/sar_ws/.venv`. The PX4 checkout under `~/px4_ws` must be
> obtained separately (PX4-Autopilot release/1.14).
>
> **The supported path is Docker** — see [`docker/README.md`](docker/README.md),
> image `sar-sim:humble`, which builds PX4, Gazebo, MAVROS and the `sar_ws`
> packages with no host setup. The RAO orchestration layer and its evaluation
> are in [`crew_sar/`](crew_sar/README.md) and need neither.

# Search & Rescue Sim: IRIS (PX4 SITL) + TurtleBot3 + CrewAI

> **RAO port (2026-08):** the orchestration layer has been restructured to the
> same RAO framework as `crew_g1_go2` — see [`crew_sar/`](crew_sar/README.md)
> for the planner/orchestrator split, workflow contracts, the four-condition
> mock evaluation (`SAR_SIM=1`, no Gazebo needed), and the live Gazebo runner.
> On machines without ROS 2 Humble, the full simulation runs in Docker — see
> [`docker/`](docker/README.md) (image `sar-sim:humble`). The original
> CrewAI-context implementation below is kept as the baseline that produced
> the paper's first recorded results.

A Gazebo Classic 11 / ROS 2 Humble test environment with:

- An **IRIS quadrotor** running **PX4 SITL**, controlled over **MAVROS**.
- A **TurtleBot3 (waffle)** ground rover.
- A static **"victim"** marker placed in the world.
- ROS 2 control nodes exposing simple services for both robots.
- A **CrewAI** crew with two agents (Aerial Recon Pilot / Ground Rescue
  Operator) that coordinate the mission: the drone searches the area and
  reports the victim's location, then the rover drives there.

## Quickstart (one command)

Once the one-time setup below is done, run everything - simulation +
CrewAI mission - with:

```bash
~/sar_ws/run_mission.sh
```

This launches the simulation, waits for the drone/rover services to come
up, runs the CrewAI mission, and shuts the simulation down when it's done.
Pass `headless:=1` to run Gazebo without the GUI:

```bash
~/sar_ws/run_mission.sh headless:=1
```

## 1. One-time setup

### 1.1 System packages

```bash
chmod +x ~/sar_setup_sudo.sh   # if not already
~/sar_setup_sudo.sh
```

This installs `ros-humble-mavros`, `ros-humble-mavros-extras`, the
GeographicLib datasets MAVROS needs, and PX4 SITL build tools
(`genromfs`, `ninja-build`, etc.) without touching the existing Gazebo
Classic 11 install.

### 1.2 PX4-Autopilot (release/1.14, gazebo-classic_iris)

Already cloned to `~/px4_ws/PX4-Autopilot` (release/1.14, shallow
submodules). Build it once (this compiles the firmware and the
`sitl_gazebo-classic` plugins - can take 20-40+ minutes the first time):

```bash
source /opt/ros/humble/setup.bash
cd ~/px4_ws/PX4-Autopilot
HEADLESS=1 make px4_sitl gazebo-classic_iris
```

The first run will build everything and then launch the SITL/Gazebo once;
press Ctrl+C once you see the PX4 shell prompt (`pxh>`) and Gazebo has
started - the build artifacts are cached for subsequent runs.

### 1.3 sar_ws workspace

```bash
source /opt/ros/humble/setup.bash
cd ~/sar_ws
colcon build --symlink-install
```

### 1.4 CrewAI Python environment

A venv with `--system-site-packages` (so `rclpy` is visible) was created at
`~/sar_ws/.venv` and already has `crewai` + `crewai-tools` installed.

An `.env` file at `~/sar_ws/.env` is loaded automatically by
`run_mission.py`. Edit it and replace the placeholder with an
[OpenRouter](https://openrouter.ai/) API key:

```bash
echo 'OPENROUTER_API_KEY=sk-...' > ~/sar_ws/.env
```

## 2. Running the simulation

Always source ROS 2 and the workspace overlay first, in this order:

```bash
source /opt/ros/humble/setup.bash
source ~/sar_ws/install/setup.bash
```

Then launch everything (PX4 SITL + IRIS in Gazebo, TurtleBot3, MAVROS,
and the drone/rover controller nodes):

```bash
ros2 launch sar_gazebo sar_simulation.launch.py
```

Useful arguments:
- `headless:=1` - run Gazebo without the GUI client.
- `px4_autopilot_dir:=/path/to/PX4-Autopilot` - if PX4 isn't at `~/px4_ws/PX4-Autopilot`.
- `rover_spawn_x` / `rover_spawn_y` - TurtleBot3 spawn pose (default `-2.0, -2.0`).
  Keep this in sync if you change `rover_controller_node`'s `spawn_x`/`spawn_y`
  parameters (it's passed through automatically by the launch file).

It takes ~20-25s after `gzserver` starts for MAVROS to connect and the
controller nodes to come up. Check with:

```bash
ros2 topic hz /mavros/state
```

### World layout (Gazebo world frame, meters)

- IRIS spawns near `(1.01, 0.98, 0.83)` (PX4's default offset) - this is the
  drone controller's local-frame origin.
- TurtleBot3 spawns at `(-2, -2)` (configurable).
- The "victim" marker (red post with a flag) is at `(5, 5)`.
- A few static "rubble" boxes are scattered around as obstacles.

All coordinates exchanged with the outside world (CrewAI tools, service
calls) are in **Gazebo world frame**; the controller nodes handle conversion
to/from each robot's local frame internally.

## 3. Manual smoke test (before involving CrewAI)

In separate terminals (each sourced as in step 2):

```bash
# Take off to 5m
ros2 service call /drone/takeoff sar_msgs/srv/Takeoff "{altitude: 5.0}"

# Search the area around the victim
ros2 service call /drone/search_area sar_msgs/srv/SearchArea \
  "{x_min: -3.0, x_max: 8.0, y_min: -3.0, y_max: 8.0, altitude: 5.0}"

# Drive the rover to a point
ros2 service call /rover/navigate_to sar_msgs/srv/NavigateTo "{x: 5.0, y: 5.0, tolerance: 0.0}"

# Land
ros2 service call /drone/land sar_msgs/srv/Land "{}"
```

Watch the Gazebo GUI to confirm the IRIS takes off/flies and the TurtleBot3
drives toward the victim marker.

## 4. Running the CrewAI mission

With the simulation from step 2 already running in another terminal:

```bash
source /opt/ros/humble/setup.bash
source ~/sar_ws/install/setup.bash
source ~/sar_ws/.venv/bin/activate
cd ~/sar_ws/src/sar_crew
python3 -m sar_crew.run_mission
```

Or use `~/sar_ws/run_mission.sh` (see Quickstart above) to launch the
simulation and run the mission with a single command.

This kicks off a sequential CrewAI process:
1. **Aerial Recon Pilot** takes off, searches the area, and once it finds the
   victim, flies over and hovers (air support).
2. **Ground Rescue Operator** receives the victim's coordinates from the
   first agent's output and drives the rover there.

## Package layout

- `sar_msgs` - service definitions (`Takeoff`, `FlyTo`, `SearchArea`, `Land`, `NavigateTo`).
- `sar_gazebo` - world (`sar_world.world`), victim model, bringup launch file.
- `sar_robot_control` - `drone_controller_node` (MAVROS-based) and
  `rover_controller_node` (go-to-goal + obstacle avoidance).
- `sar_crew` - CrewAI tools/agents/crew + `run_mission.py` entry point.

## Known limitations / possible follow-ups

- The rover uses a simple proportional go-to-goal + reactive obstacle
  avoidance controller rather than full Nav2/SLAM - fine for an open test
  world, but won't handle complex maze-like environments.
- "Victim detection" is simulated via `/gazebo/get_entity_state` proximity
  rather than real computer vision on a camera feed.
- Coordinate-frame offsets (IRIS spawn offset, rover spawn pose) are handled
  via launch/node parameters; if you change spawn poses, update both the
  launch file arguments and the corresponding node parameters.
