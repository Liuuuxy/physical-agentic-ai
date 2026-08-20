#!/usr/bin/env python3
"""Bring up the IRIS (PX4 SITL) + TurtleBot3 search-and-rescue test world.

This launch file:
  1. Starts PX4 SITL with the IRIS vehicle inside Gazebo Classic, loading
     our custom `sar_world.world` (set via the PX4_SITL_WORLD env var).
  2. Spawns a TurtleBot3 (waffle) into the same Gazebo instance.
  3. Starts robot_state_publisher for the TurtleBot3.
  4. Starts MAVROS, bridging ROS 2 <-> the PX4 SITL MAVLink stream.
  5. Starts the drone and rover controller nodes (sar_robot_control).

Notes / assumptions:
  - PX4-Autopilot (release/1.14) must already be built for
    gazebo-classic_iris (see sar_ws/README.md). Set its location with the
    `px4_autopilot_dir` launch argument or the PX4_AUTOPILOT_DIR env var.
  - The IRIS is spawned by PX4's sitl_run.sh at Gazebo pose
    (x=1.01, y=0.98, z=0.83) - this matches the default
    `spawn_offset_x`/`spawn_offset_y` parameters of drone_controller_node.
  - The TurtleBot3 is spawned at (spawn_x, spawn_y) below - keep this in
    sync with rover_controller_node's `spawn_x`/`spawn_y` parameters.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    sar_gazebo_share = get_package_share_directory('sar_gazebo')
    turtlebot3_gazebo_share = get_package_share_directory('turtlebot3_gazebo')

    default_px4_dir = os.path.expanduser('~/px4_ws/PX4-Autopilot')

    px4_autopilot_dir = LaunchConfiguration('px4_autopilot_dir')
    headless = LaunchConfiguration('headless')
    rover_spawn_x = LaunchConfiguration('rover_spawn_x')
    rover_spawn_y = LaunchConfiguration('rover_spawn_y')
    fcu_url = LaunchConfiguration('fcu_url')
    world_file = LaunchConfiguration('world_file')
    rubble_json = LaunchConfiguration('rubble_json')

    # world_file is a filename inside sar_gazebo/worlds/, resolved at launch
    # time so the `scenario` selection done by run_mission.sh (see
    # sar_crew/sar_crew/scenarios.py) can swap in a different obstacle/victim
    # layout without touching this launch file.
    world_path = PathJoinSubstitution([sar_gazebo_share, 'worlds', world_file])

    declare_args = [
        DeclareLaunchArgument(
            'px4_autopilot_dir', default_value=default_px4_dir,
            description='Path to the built PX4-Autopilot (release/1.14) checkout'),
        DeclareLaunchArgument(
            'headless', default_value='0',
            description='Set to 1 to run Gazebo without the GUI client'),
        DeclareLaunchArgument(
            'rover_spawn_x', default_value='-2.0',
            description='TurtleBot3 spawn X (Gazebo world frame)'),
        DeclareLaunchArgument(
            'rover_spawn_y', default_value='-2.0',
            description='TurtleBot3 spawn Y (Gazebo world frame)'),
        DeclareLaunchArgument(
            'fcu_url', default_value='udp://:14540@127.0.0.1:14557',
            description='MAVROS FCU connection URL for the PX4 SITL MAVLink stream'),
        DeclareLaunchArgument(
            'world_file', default_value='sar_world.world',
            description='Gazebo world filename inside sar_gazebo/worlds/ '
                        '(selects victim/obstacle scenario)'),
        DeclareLaunchArgument(
            'rubble_json', default_value='',
            description='JSON list of [cx,cy,half_x,half_y,yaw] obstacle '
                        'boxes for the rover A* planner; empty = Scenario A defaults'),
    ]

    # ---- environment for PX4 + Gazebo + TurtleBot3 ----
    set_env = [
        SetEnvironmentVariable('TURTLEBOT3_MODEL', 'waffle'),
        SetEnvironmentVariable('PX4_SITL_WORLD', world_path),
        SetEnvironmentVariable('ROS_VERSION', '2'),
        # Append our victim model and the TurtleBot3 models to GAZEBO_MODEL_PATH.
        SetEnvironmentVariable(
            'GAZEBO_MODEL_PATH',
            os.pathsep.join([
                os.path.join(sar_gazebo_share, 'models'),
                os.path.join(turtlebot3_gazebo_share, 'models'),
                os.environ.get('GAZEBO_MODEL_PATH', ''),
            ])
        ),
    ]

    # ---- PX4 SITL + Gazebo (IRIS) ----
    # sitl_run.sh checks `[[ -n "$HEADLESS" ]]`, which is true for *any*
    # non-empty value (including "0") - so HEADLESS must only be present
    # in the environment at all when we actually want headless mode.
    px4_sitl_headless = ExecuteProcess(
        cmd=['make', 'px4_sitl', 'gazebo-classic_iris'],
        cwd=px4_autopilot_dir,
        output='screen',
        additional_env={'HEADLESS': '1'},
        condition=IfCondition(headless),
    )

    px4_sitl_gui = ExecuteProcess(
        cmd=['make', 'px4_sitl', 'gazebo-classic_iris'],
        cwd=px4_autopilot_dir,
        output='screen',
        condition=UnlessCondition(headless),
    )

    # ---- TurtleBot3 spawn (after Gazebo has had time to come up) ----
    urdf_path = os.path.join(
        turtlebot3_gazebo_share, 'models', 'turtlebot3_waffle', 'model.sdf')

    spawn_turtlebot3 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'waffle',
            '-file', urdf_path,
            '-x', rover_spawn_x,
            '-y', rover_spawn_y,
            '-z', '0.01',
        ],
        output='screen',
    )

    urdf_file_path = os.path.join(turtlebot3_gazebo_share, 'urdf', 'turtlebot3_waffle.urdf')
    with open(urdf_file_path, 'r') as f:
        robot_description = f.read()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_description,
        }],
    )

    # ---- MAVROS (after PX4 SITL has had time to start its MAVLink stream) ----
    mavros_node = Node(
        package='mavros',
        executable='mavros_node',
        output='screen',
        parameters=[{
            'fcu_url': fcu_url,
            'gcs_url': '',
            'target_system_id': 1,
            'target_component_id': 1,
            'fcu_protocol': 'v2.0',
        }],
    )

    # ---- our control nodes ----
    drone_controller = Node(
        package='sar_robot_control',
        executable='drone_controller_node',
        output='screen',
    )

    rover_controller = Node(
        package='sar_robot_control',
        executable='rover_controller_node',
        output='screen',
        parameters=[{
            'spawn_x': rover_spawn_x,
            'spawn_y': rover_spawn_y,
            # ParameterValue forces this to be treated as a plain string -
            # without it, launch_ros YAML-parses the bracketed JSON text
            # and tries to send it as a nested array, which ROS 2
            # parameters reject ("Expected a non-empty sequence, with
            # items of uniform type").
            'rubble_json': ParameterValue(rubble_json, value_type=str),
        }],
    )

    return LaunchDescription(declare_args + set_env + [
        px4_sitl_headless,
        px4_sitl_gui,
        # give gzserver time to come up before spawning the rover and
        # connecting MAVROS.
        TimerAction(period=15.0, actions=[spawn_turtlebot3, robot_state_publisher]),
        TimerAction(period=20.0, actions=[mavros_node]),
        TimerAction(period=25.0, actions=[drone_controller, rover_controller]),
    ])
