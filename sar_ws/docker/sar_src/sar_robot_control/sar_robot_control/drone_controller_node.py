#!/usr/bin/env python3
"""Drone controller node for the IRIS (PX4 SITL) quadrotor.

Wraps MAVROS topics/services to provide simple, blocking ROS 2 services
that a higher-level coordinator (CrewAI) can call:

  /drone/takeoff       (sar_msgs/Takeoff)     - arm, switch to OFFBOARD, climb to altitude
  /drone/fly_to        (sar_msgs/FlyTo)       - fly to a local-frame waypoint
  /drone/search_area   (sar_msgs/SearchArea)  - lawnmower search, reports victim pose if found
  /drone/land          (sar_msgs/Land)        - switch to AUTO.LAND

Assumes the IRIS is spawned at the Gazebo world origin, so MAVROS local
ENU coordinates (/mavros/local_position/pose) line up with Gazebo world
coordinates used by /gazebo/get_entity_state.
"""
import base64
import json
import math
import os
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, QoSDurabilityPolicy

from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
from gazebo_msgs.srv import GetEntityState
from sensor_msgs.msg import Image

from sar_msgs.srv import Takeoff, FlyTo, SearchArea, Land, PerceptionQuery

# Optional VLM / camera support — imported lazily so the node still starts
# if these packages are not installed.
try:
    import cv2
    import numpy as np
    # cv_bridge was compiled against NumPy 1.x; using it with NumPy 2.x causes
    # a segfault (_ARRAY_API not found).  Disable both when NumPy >= 2.
    if int(np.__version__.split('.')[0]) >= 2:
        raise ImportError('NumPy >= 2 is incompatible with this cv_bridge build')
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    from cv_bridge import CvBridge
    _CV_BRIDGE_AVAILABLE = _CV2_AVAILABLE   # only usable when NumPy < 2
except Exception:   # AttributeError from broken cv_bridge build, or ImportError
    _CV_BRIDGE_AVAILABLE = False

# Camera topics published by PX4 SITL IRIS (tried in order)
_IRIS_CAMERA_TOPICS = [
    '/iris/camera/image_raw',
    '/iris/usb_cam/image_raw',
    '/camera/image_raw',
    '/drone/camera/image_raw',
]

# Horizontal FOV half-width at 5 m altitude (tan(30°) × 5 m ≈ 2.9 m)
_CAM_FOV_HALF_M = 2.9


class DroneControllerNode(Node):

    def __init__(self):
        super().__init__('drone_controller_node')

        # ---- parameters ----
        self.declare_parameter('position_tolerance', 0.5)   # meters
        self.declare_parameter('detection_radius', 1.5)      # meters (horizontal)
        self.declare_parameter('search_row_spacing', 2.0)    # meters
        self.declare_parameter('timeout', 60.0)              # seconds for waypoint waits
        self.declare_parameter('victim_entity_name', 'victim')
        # PX4's sitl_run.sh spawns the IRIS in Gazebo at a fixed offset from
        # the world origin (-x 1.01 -y 0.98 -z 0.83 for gazebo-classic_iris).
        # MAVROS local-frame (0,0,0) corresponds to that spawn pose, so all
        # x/y coordinates exchanged with the outside world (CrewAI tools,
        # the victim's Gazebo pose, the rover's goal) use Gazebo *world*
        # frame, and are converted to/from MAVROS local frame using this
        # offset. Altitude (z) is treated as height-above-ground directly.
        self.declare_parameter('spawn_offset_x', 1.01)
        self.declare_parameter('spawn_offset_y', 0.98)

        self.position_tolerance = self.get_parameter('position_tolerance').value
        self.detection_radius = self.get_parameter('detection_radius').value
        self.search_row_spacing = self.get_parameter('search_row_spacing').value
        self.timeout = self.get_parameter('timeout').value
        self.victim_entity_name = self.get_parameter('victim_entity_name').value
        self.spawn_offset_x = self.get_parameter('spawn_offset_x').value
        self.spawn_offset_y = self.get_parameter('spawn_offset_y').value

        cb_group = ReentrantCallbackGroup()

        # ---- state ----
        self.current_state = State()
        self.current_pose = None  # PoseStamped, set once first message arrives
        self.target_pose = PoseStamped()
        self.target_pose.header.frame_id = 'map'
        self.target_yaw = 0.0

        # ---- perception bridge camera state ----
        self._latest_frame = None          # numpy uint8 BGR, guarded by _frame_lock
        self._frame_lock = threading.Lock()
        self._cv_bridge = CvBridge() if _CV_BRIDGE_AVAILABLE else None
        self._camera_ready = False
        self._openrouter_key = os.environ.get('OPENROUTER_API_KEY', '')

        qos_be = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=10,
        )

        # ---- subscriptions ----
        self.create_subscription(State, '/mavros/state', self._state_cb, qos_be,
                                  callback_group=cb_group)
        self.create_subscription(PoseStamped, '/mavros/local_position/pose',
                                  self._pose_cb, qos_be, callback_group=cb_group)

        # ---- publishers ----
        self.setpoint_pub = self.create_publisher(
            PoseStamped, '/mavros/setpoint_position/local', 10)

        # ---- service clients ----
        self.arming_client = self.create_client(CommandBool, '/mavros/cmd/arming',
                                                  callback_group=cb_group)
        self.set_mode_client = self.create_client(SetMode, '/mavros/set_mode',
                                                    callback_group=cb_group)
        self.get_entity_state_client = self.create_client(
            GetEntityState, '/get_entity_state', callback_group=cb_group)

        # ---- setpoint streaming timer (required for PX4 OFFBOARD mode) ----
        self.create_timer(0.05, self._publish_setpoint, callback_group=cb_group)  # 20 Hz

        # ---- try to subscribe to the drone camera (non-fatal if absent) ----
        if _CV2_AVAILABLE and _CV_BRIDGE_AVAILABLE:
            for topic in _IRIS_CAMERA_TOPICS:
                self.create_subscription(Image, topic, self._camera_cb,
                                         10, callback_group=cb_group)
            self.get_logger().info(
                f'PerceptionBridge: watching camera topics {_IRIS_CAMERA_TOPICS}')
        else:
            self.get_logger().warn(
                'PerceptionBridge: cv2/cv_bridge not available — will use simulation oracle')

        # ---- services exposed to CrewAI / higher-level coordinator ----
        self.create_service(Takeoff,          '/drone/takeoff',           self._handle_takeoff,
                             callback_group=cb_group)
        self.create_service(FlyTo,            '/drone/fly_to',            self._handle_fly_to,
                             callback_group=cb_group)
        self.create_service(SearchArea,       '/drone/search_area',       self._handle_search_area,
                             callback_group=cb_group)
        self.create_service(Land,             '/drone/land',              self._handle_land,
                             callback_group=cb_group)
        self.create_service(PerceptionQuery,  '/drone/perception_query',  self._handle_perception_query,
                             callback_group=cb_group)

        self.get_logger().info('Drone controller node ready.')

    # ------------------------------------------------------------------
    # subscription callbacks
    # ------------------------------------------------------------------
    def _state_cb(self, msg: State):
        self.current_state = msg

    def _pose_cb(self, msg: PoseStamped):
        if self.current_pose is None:
            # initialize target to current pose so the setpoint stream
            # doesn't command a jump as soon as it starts.
            self.target_pose = msg
        self.current_pose = msg

    def _camera_cb(self, msg: Image):
        if self._cv_bridge is None:
            return
        try:
            frame = self._cv_bridge.imgmsg_to_cv2(msg, 'bgr8')
            with self._frame_lock:
                self._latest_frame = frame
                self._camera_ready = True
        except Exception as e:
            self.get_logger().error(f'Camera decode error: {e}')

    def _publish_setpoint(self):
        self.target_pose.header.stamp = self.get_clock().now().to_msg()
        self.setpoint_pub.publish(self.target_pose)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _world_to_local(self, x, y):
        return x - self.spawn_offset_x, y - self.spawn_offset_y

    def _local_to_world(self, x, y):
        return x + self.spawn_offset_x, y + self.spawn_offset_y

    def _set_target_world(self, x, y, z, yaw=None):
        """Set target waypoint given world-frame x, y and an altitude z."""
        lx, ly = self._world_to_local(x, y)
        if yaw is None:
            yaw = self.target_yaw
        self.target_yaw = yaw
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.pose.position.x = lx
        pose.pose.position.y = ly
        pose.pose.position.z = z
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.target_pose = pose

    def _distance_to_target(self):
        if self.current_pose is None:
            return float('inf')
        dx = self.current_pose.pose.position.x - self.target_pose.pose.position.x
        dy = self.current_pose.pose.position.y - self.target_pose.pose.position.y
        dz = self.current_pose.pose.position.z - self.target_pose.pose.position.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _wait_until_reached(self, tolerance, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self._distance_to_target() <= tolerance:
                return True
            time.sleep(0.2)
        return False

    def _ensure_offboard_and_armed(self):
        """Stream a few setpoints, then arm and switch to OFFBOARD."""
        # Make sure we've received at least one position before streaming.
        start = time.time()
        while self.current_pose is None and time.time() - start < 10.0:
            time.sleep(0.1)
        if self.current_pose is None:
            return False, 'No /mavros/local_position/pose received - is MAVROS connected?'

        # Stream current setpoint for ~1s before requesting OFFBOARD (PX4 requirement).
        time.sleep(1.0)

        if self.current_state.mode != 'OFFBOARD':
            req = SetMode.Request()
            req.custom_mode = 'OFFBOARD'
            future = self.set_mode_client.call_async(req)
            self._spin_until_future(future, 10.0)
            if not (future.done() and future.result() and future.result().mode_sent):
                return False, 'Failed to switch to OFFBOARD mode'

        if not self.current_state.armed:
            req = CommandBool.Request()
            req.value = True
            future = self.arming_client.call_async(req)
            self._spin_until_future(future, 10.0)
            if not (future.done() and future.result() and future.result().success):
                return False, 'Failed to arm vehicle'

        return True, 'OK'

    def _spin_until_future(self, future, timeout):
        start = time.time()
        while not future.done() and time.time() - start < timeout:
            time.sleep(0.05)

    def _get_victim_pose(self):
        if not self.get_entity_state_client.wait_for_service(timeout_sec=2.0):
            return None
        req = GetEntityState.Request()
        req.name = self.victim_entity_name
        future = self.get_entity_state_client.call_async(req)
        self._spin_until_future(future, 5.0)
        if not future.done() or future.result() is None or not future.result().success:
            return None
        return future.result().state.pose

    # ------------------------------------------------------------------
    # service handlers
    # ------------------------------------------------------------------
    def _handle_takeoff(self, request, response):
        ok, msg = self._ensure_offboard_and_armed()
        if not ok:
            response.success = False
            response.message = msg
            return response

        wx, wy = self._local_to_world(self.current_pose.pose.position.x,
                                       self.current_pose.pose.position.y)
        self._set_target_world(wx, wy, request.altitude)

        reached = self._wait_until_reached(self.position_tolerance, self.timeout)
        response.success = reached
        response.message = 'Reached altitude' if reached else 'Timed out reaching altitude'
        return response

    def _handle_fly_to(self, request, response):
        tol = request.tolerance if request.tolerance > 0.0 else self.position_tolerance
        self._set_target_world(request.x, request.y, request.z)
        reached = self._wait_until_reached(tol, self.timeout)
        response.success = reached
        response.message = 'Reached waypoint' if reached else 'Timed out reaching waypoint'
        return response

    def _check_victim_nearby(self, response):
        """If the victim is within detection_radius of the drone, fill in
        response and return True."""
        victim_pose = self._get_victim_pose()
        if victim_pose is None or self.current_pose is None:
            return False
        drone_wx, drone_wy = self._local_to_world(
            self.current_pose.pose.position.x,
            self.current_pose.pose.position.y)
        dx = drone_wx - victim_pose.position.x
        dy = drone_wy - victim_pose.position.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > self.detection_radius:
            return False
        response.found = True
        response.message = (
            f'Victim located near ({victim_pose.position.x:.2f}, '
            f'{victim_pose.position.y:.2f}) while drone at '
            f'({drone_wx:.2f}, {drone_wy:.2f})'
        )
        response.victim_x = victim_pose.position.x
        response.victim_y = victim_pose.position.y
        response.victim_z = victim_pose.position.z
        return True

    def _handle_search_area(self, request, response):
        waypoints = self._lawnmower_pattern(
            request.x_min, request.x_max, request.y_min, request.y_max,
            request.altitude, self.search_row_spacing)

        for (wx, wy, wz) in waypoints:
            self._set_target_world(wx, wy, wz)

            # Poll for the victim continuously while flying to the next
            # waypoint, not just on arrival - the victim may be along the
            # route rather than exactly at a lawnmower turn point.
            start = time.time()
            while time.time() - start < self.timeout:
                if self._check_victim_nearby(response):
                    return response
                if self._distance_to_target() <= self.position_tolerance:
                    break
                time.sleep(0.2)

            if self._check_victim_nearby(response):
                return response

        response.found = False
        response.message = 'Search area covered, victim not detected'
        response.victim_x = 0.0
        response.victim_y = 0.0
        response.victim_z = 0.0
        return response

    # ------------------------------------------------------------------
    # Perception bridge
    # ------------------------------------------------------------------
    def _handle_perception_query(self, request, response):
        """
        Perception bridge service: evaluates the drone's current camera feed
        (or falls back to the Gazebo simulation oracle) and returns a
        structured semantic scene description to the CrewAI layer.

        When a real camera frame is available AND an OpenRouter API key is
        configured, the frame is sent to a vision-capable LLM which returns
        human-readable detection text with estimated world coordinates.
        The oracle fallback produces the same interface using ground-truth
        Gazebo entity state, allowing full system testing without a camera.
        """
        with self._frame_lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None

        if self._camera_ready and frame is not None and self._openrouter_key:
            detected, text, vx, vy = self._vlm_query(
                frame, request.drone_x, request.drone_y)
        else:
            if not self._camera_ready:
                self.get_logger().info(
                    'PerceptionBridge: no camera frame yet — using simulation oracle')
            detected, text, vx, vy = self._oracle_query(
                request.drone_x, request.drone_y)

        response.detected = detected
        response.semantic_text = text
        response.victim_x = vx
        response.victim_y = vy
        return response

    def _vlm_query(self, frame, drone_x: float, drone_y: float):
        """Encode the camera frame and query a vision-capable LLM via OpenRouter."""
        try:
            import openai
        except ImportError:
            self.get_logger().warn('openai package not installed; falling back to oracle')
            return self._oracle_query(drone_x, drone_y)

        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

        prompt = (
            'You are the perception system of a search-and-rescue drone flying at ~5 m altitude. '
            'Analyse this downward-facing camera frame and determine whether a human victim is visible. '
            'If a human is detected, estimate their pixel-normalised offset from the image centre: '
            'x_offset ∈ [-1, 1] (left/right), y_offset ∈ [-1, 1] (near/far from drone). '
            'Reply with valid JSON only — no markdown, no extra text:\n'
            '{"detected": true|false, "confidence": 0.0-1.0, '
            '"x_offset": float, "y_offset": float, "occlusion": "low|medium|high", '
            '"description": "one sentence"}'
        )

        try:
            import openai as _openai
            client = _openai.OpenAI(
                api_key=self._openrouter_key,
                base_url='https://openrouter.ai/api/v1',
            )
            resp = client.chat.completions.create(
                model='openai/gpt-4o-mini',
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url',
                         'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
                    ],
                }],
                max_tokens=200,
                temperature=0.1,
            )
            result = json.loads(resp.choices[0].message.content)
        except Exception as e:
            self.get_logger().error(f'VLM API call failed: {e}; falling back to oracle')
            return self._oracle_query(drone_x, drone_y)

        detected = bool(result.get('detected', False))
        x_off    = float(result.get('x_offset', 0.0))
        y_off    = float(result.get('y_offset', 0.0))
        conf     = float(result.get('confidence', 0.0))
        occ      = result.get('occlusion', 'unknown')
        desc     = result.get('description', '')

        if detected:
            # Convert image-frame offsets to world-frame estimate:
            # y_off > 0 → victim farther away → ahead of drone (+drone_x direction is arbitrary;
            # we use offset directly as a displacement in the world x/y plane).
            vx = drone_x + y_off * _CAM_FOV_HALF_M
            vy = drone_y + x_off * _CAM_FOV_HALF_M
            text = (
                f'Target human detected at relative coordinates [{x_off:.2f}, {y_off:.2f}], '
                f'environmental occlusion {occ}. '
                f'Estimated world position: x={vx:.2f}, y={vy:.2f}. '
                f'Confidence: {conf:.2f}. {desc}'
            )
            return True, text, vx, vy
        else:
            return False, f'No human visible in current frame. Environmental occlusion {occ}. {desc}', 0.0, 0.0

    def _oracle_query(self, drone_x: float, drone_y: float):
        """
        Simulation oracle fallback: queries Gazebo ground truth and formats
        the result as if it came from the VLM perception bridge, so the
        CrewAI layer receives the same interface regardless of mode.
        """
        victim_pose = self._get_victim_pose()
        if victim_pose is None or self.current_pose is None:
            return False, 'Perception query failed: victim entity not found in scene', 0.0, 0.0

        vx = victim_pose.position.x
        vy = victim_pose.position.y
        dist = math.hypot(drone_x - vx, drone_y - vy)

        if dist > self.detection_radius:
            return (False,
                    f'[Sim perception] No human visible in current frame — '
                    f'nearest entity {dist:.1f} m away. Area clear.',
                    0.0, 0.0)

        x_off = (vx - drone_x) / max(dist, 0.01)
        y_off = (vy - drone_y) / max(dist, 0.01)
        text = (
            f'[Sim perception] Target human detected at relative coordinates '
            f'[{x_off:.2f}, {y_off:.2f}], environmental occlusion low. '
            f'Estimated world position: x={vx:.2f}, y={vy:.2f}. Confidence: 0.95'
        )
        return True, text, vx, vy

    def _handle_land(self, request, response):
        req = SetMode.Request()
        req.custom_mode = 'AUTO.LAND'
        future = self.set_mode_client.call_async(req)
        self._spin_until_future(future, 10.0)
        ok = future.done() and future.result() and future.result().mode_sent
        response.success = bool(ok)
        response.message = 'Landing' if ok else 'Failed to switch to AUTO.LAND'
        return response

    # ------------------------------------------------------------------
    @staticmethod
    def _lawnmower_pattern(x_min, x_max, y_min, y_max, altitude, row_spacing):
        """Generate a back-and-forth ('lawnmower') sweep over a rectangle."""
        waypoints = []
        y = y_min
        going_right = True
        if row_spacing <= 0:
            row_spacing = 2.0
        while y <= y_max + 1e-6:
            if going_right:
                waypoints.append((x_min, y, altitude))
                waypoints.append((x_max, y, altitude))
            else:
                waypoints.append((x_max, y, altitude))
                waypoints.append((x_min, y, altitude))
            going_right = not going_right
            y += row_spacing
        return waypoints


def main(args=None):
    rclpy.init(args=args)
    node = DroneControllerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
