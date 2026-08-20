"""Background rclpy node bridging CrewAI tools to the SAR ROS 2 services.

A single rclpy node is spun up in a background thread. CrewAI tools call
the blocking helper functions below, which call the ROS 2 services
exposed by sar_robot_control (drone_controller_node / rover_controller_node)
and wait for the result.
"""
import math
import time
import threading

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Pose
from gazebo_msgs.srv import SetModelState
from gazebo_msgs.msg import ModelState

from sar_msgs.srv import Takeoff, FlyTo, SearchArea, Land, NavigateTo, Stop, PerceptionQuery


class _RosBridgeNode(Node):
    def __init__(self):
        super().__init__('sar_crew_bridge')
        self.takeoff_client          = self.create_client(Takeoff,          '/drone/takeoff')
        self.fly_to_client           = self.create_client(FlyTo,            '/drone/fly_to')
        self.search_area_client      = self.create_client(SearchArea,       '/drone/search_area')
        self.land_client             = self.create_client(Land,             '/drone/land')
        self.perception_query_client = self.create_client(PerceptionQuery,  '/drone/perception_query')
        self.navigate_to_client      = self.create_client(NavigateTo,       '/rover/navigate_to')
        self.stop_client             = self.create_client(Stop,             '/rover/stop')
        self.set_model_state_client  = self.create_client(SetModelState,    '/gazebo/set_model_state')

        # Track rover position for delivery-error metric
        self._rover_x = float('nan')
        self._rover_y = float('nan')
        self._odom_lock = threading.Lock()
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)

    def _odom_cb(self, msg: Odometry):
        with self._odom_lock:
            self._rover_x = msg.pose.pose.position.x
            self._rover_y = msg.pose.pose.position.y

    def rover_position(self):
        with self._odom_lock:
            return self._rover_x, self._rover_y

    def call(self, client, request, service_name, wait_timeout=10.0, call_timeout=600.0):
        if not client.wait_for_service(timeout_sec=wait_timeout):
            raise RuntimeError(
                f'Service {service_name} not available - is the simulation running?')
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=call_timeout)
        if not future.done() or future.result() is None:
            raise RuntimeError(f'Service call to {service_name} timed out')
        return future.result()


class RosBridge:
    """Thread-safe singleton wrapper around the bridge node."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = _RosBridgeNode()
        self._executor = MultiThreadedExecutor(num_threads=2)
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = RosBridge()
            return cls._instance

    # ------------------------------------------------------------------
    # Drone — matches iris_* skill library from the paper
    # ------------------------------------------------------------------
    def drone_takeoff(self, altitude: float):
        req = Takeoff.Request(altitude=float(altitude))
        res = self._node.call(self._node.takeoff_client, req, '/drone/takeoff')
        return res.success, res.message

    def drone_fly_to(self, x: float, y: float, z: float, tolerance: float = 0.0):
        req = FlyTo.Request(x=float(x), y=float(y), z=float(z), tolerance=float(tolerance))
        res = self._node.call(self._node.fly_to_client, req, '/drone/fly_to')
        return res.success, res.message

    def drone_search_area(self, x_min, x_max, y_min, y_max, altitude):
        req = SearchArea.Request(
            x_min=float(x_min), x_max=float(x_max),
            y_min=float(y_min), y_max=float(y_max),
            altitude=float(altitude))
        res = self._node.call(
            self._node.search_area_client, req, '/drone/search_area', call_timeout=1800.0)
        return res.found, res.message, res.victim_x, res.victim_y, res.victim_z

    def drone_land(self):
        req = Land.Request()
        res = self._node.call(self._node.land_client, req, '/drone/land')
        return res.success, res.message

    def drone_perception_query(self, drone_x: float, drone_y: float):
        """
        Call the drone's perception bridge.
        Returns (detected: bool, semantic_text: str, victim_x: float, victim_y: float).
        """
        req = PerceptionQuery.Request(drone_x=float(drone_x), drone_y=float(drone_y))
        res = self._node.call(
            self._node.perception_query_client, req, '/drone/perception_query',
            call_timeout=30.0)
        return res.detected, res.semantic_text, res.victim_x, res.victim_y

    # ------------------------------------------------------------------
    # Rover — matches tb3_* skill library from the paper
    # ------------------------------------------------------------------
    def rover_navigate_to(self, x: float, y: float, tolerance: float = 0.0):
        req = NavigateTo.Request(x=float(x), y=float(y), tolerance=float(tolerance))
        res = self._node.call(
            self._node.navigate_to_client, req, '/rover/navigate_to', call_timeout=300.0)
        return res.success, res.message

    def rover_stop(self):
        """Immediately halt the rover mid-navigation."""
        req = Stop.Request()
        res = self._node.call(self._node.stop_client, req, '/rover/stop', call_timeout=5.0)
        return res.success, res.message

    def rover_final_position(self):
        """Return the rover's last known (x, y) from /odom (nan if not yet received)."""
        return self._node.rover_position()

    # ------------------------------------------------------------------
    # Reset between runs — makes repeated runs within one sim session
    # independent of each other.
    # ------------------------------------------------------------------
    def reset_for_next_run(self, rover_spawn_x: float = -2.0,
                           rover_spawn_y: float = -2.0,
                           drone_spawn_x: float = 1.01,
                           drone_spawn_y: float = 0.98,
                           drone_spawn_z: float = 5.0,
                           settle_secs: float = 5.0) -> None:
        """
        Reset the simulation state between runs without relaunching.

        Strategy (avoids landing complexity and PX4 re-arm issues):
          1. Stop the rover.
          2. Fly the drone back to its spawn hover position. The drone stays
             armed and in OFFBOARD — the next run's iris_takeoff confirms
             altitude is reached and the lawnmower sweep starts fresh from
             the spawn position, far from the victim.
          3. Teleport the rover back to spawn via /gazebo/set_model_state
             (instant). Falls back to rover_navigate_to if that fails.
          4. Settle.
        """
        print('  [reset] stopping rover...')
        try:
            self.rover_stop()
        except Exception:
            pass

        # Fly drone to spawn hover — blocks until arrived, drone stays armed.
        print(f'  [reset] flying drone to spawn hover ({drone_spawn_x},{drone_spawn_y},{drone_spawn_z})...')
        try:
            self.drone_fly_to(drone_spawn_x, drone_spawn_y, drone_spawn_z)
        except Exception as e:
            print(f'  [reset] drone fly-to-spawn failed: {e}')

        # Teleport rover via Gazebo set_model_state (fast, no path planning)
        print(f'  [reset] teleporting rover to spawn ({rover_spawn_x},{rover_spawn_y})...')
        teleport_ok = self._teleport_rover(rover_spawn_x, rover_spawn_y)
        if not teleport_ok:
            print('  [reset] teleport unavailable — navigating rover back to spawn...')
            try:
                self.rover_navigate_to(rover_spawn_x, rover_spawn_y)
            except Exception as e:
                print(f'  [reset] rover navigate-to-spawn failed: {e}')

        time.sleep(settle_secs)
        print(f'  [reset] complete — ready for next run.')

    def _teleport_rover(self, x: float, y: float) -> bool:
        """Teleport TurtleBot3 to (x,y) via /gazebo/set_model_state. Returns True on success."""
        try:
            pose = Pose()
            pose.position.x = float(x)
            pose.position.y = float(y)
            pose.position.z = 0.01
            pose.orientation.w = 1.0

            state = ModelState()
            state.model_name = 'waffle'
            state.pose = pose
            state.reference_frame = 'world'

            req = SetModelState.Request()
            req.model_state = state
            self._node.call(
                self._node.set_model_state_client, req,
                '/gazebo/set_model_state', wait_timeout=5.0, call_timeout=10.0)
            return True
        except Exception as e:
            print(f'  [reset] /gazebo/set_model_state failed: {e}')
            return False
