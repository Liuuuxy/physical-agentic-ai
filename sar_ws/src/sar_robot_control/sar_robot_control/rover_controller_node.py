#!/usr/bin/env python3
"""Rover controller node for the TurtleBot3 ground robot.

Provides a single blocking ROS 2 service for a higher-level coordinator
(CrewAI) to drive the rover to a goal point:

  /rover/navigate_to  (sar_msgs/NavigateTo)

Navigation strategy:
  1. A* path planner computes a collision-free route on a 0.5 m grid,
     inflating each known rubble obstacle by the robot footprint radius.
  2. The robot follows the planned waypoints in sequence using a
     proportional go-to-goal controller.
  3. Reactive LiDAR avoidance acts as a safety net for anything not
     in the static map (e.g. unexpected objects, the drone on the pad).
"""
import heapq
import json
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, QoSDurabilityPolicy

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan

from sar_msgs.srv import NavigateTo, Stop

# ---------------------------------------------------------------------------
# Default static world geometry — matches sar_world.world (Scenario A).
# Each entry: (cx, cy, half_len_x, half_len_y, yaw_rad)
# Overridden at runtime by the `rubble_json` ROS parameter so different
# scenarios (sar_crew/sar_crew/scenarios.py) can swap obstacle layouts
# without touching code — see sar_simulation.launch.py's `scenario` arg.
# ---------------------------------------------------------------------------
DEFAULT_RUBBLE = [
    (4.0,  3.0,  1.0,  0.75, 0.4),   # rubble_1  (2 x 1.5 m, 23°)
    (-3.0, 5.0,  0.75, 0.75, -0.3),  # rubble_2  (1.5 x 1.5 m, -17°)
    (2.0,  -4.0, 1.5,  0.5,  0.9),   # rubble_3  (3 x 1 m, 52°)
]

# A* grid parameters
GRID_RES   = 0.5          # metres per cell
GRID_X_MIN, GRID_X_MAX = -6.0, 10.0
GRID_Y_MIN, GRID_Y_MAX = -6.0, 10.0
ROBOT_INFL = 0.40         # inflation radius (robot half-width + safety margin)


def _point_in_box(px, py, cx, cy, hlx, hly, yaw, inflation):
    """Return True if (px,py) is inside an axis-aligned-inflated rotated box."""
    dx = px - cx
    dy = py - cy
    lx =  dx * math.cos(yaw) + dy * math.sin(yaw)
    ly = -dx * math.sin(yaw) + dy * math.cos(yaw)
    return abs(lx) < hlx + inflation and abs(ly) < hly + inflation


def _cell_blocked(wx, wy, rubble):
    for (cx, cy, hlx, hly, yaw) in rubble:
        if _point_in_box(wx, wy, cx, cy, hlx, hly, yaw, ROBOT_INFL):
            return True
    return False


def _astar(sx, sy, gx, gy, rubble):
    """Return a list of (x, y) world waypoints from start to goal, or [] on failure."""
    def to_cell(x, y):
        return (int(round((x - GRID_X_MIN) / GRID_RES)),
                int(round((y - GRID_Y_MIN) / GRID_RES)))

    def to_world(ci, cj):
        return (GRID_X_MIN + ci * GRID_RES, GRID_Y_MIN + cj * GRID_RES)

    cols = int((GRID_X_MAX - GRID_X_MIN) / GRID_RES) + 1
    rows = int((GRID_Y_MAX - GRID_Y_MIN) / GRID_RES) + 1

    start = to_cell(sx, sy)
    goal  = to_cell(gx, gy)

    open_heap = [(0.0, start)]
    came_from = {}
    g = {start: 0.0}

    MOVES = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]

    while open_heap:
        _, cur = heapq.heappop(open_heap)
        if cur == goal:
            # Reconstruct path (skip start cell, keep goal)
            path = []
            node = cur
            while node in came_from:
                path.append(to_world(*node))
                node = came_from[node]
            path.reverse()
            path.append((gx, gy))
            return _simplify(path, sx, sy, rubble)

        for di, dj in MOVES:
            nb = (cur[0] + di, cur[1] + dj)
            if not (0 <= nb[0] < cols and 0 <= nb[1] < rows):
                continue
            wx, wy = to_world(*nb)
            if _cell_blocked(wx, wy, rubble):
                continue
            step = 1.414 if di and dj else 1.0
            ng = g[cur] + step
            if ng < g.get(nb, float('inf')):
                came_from[nb] = cur
                g[nb] = ng
                h = math.hypot(nb[0] - goal[0], nb[1] - goal[1])
                heapq.heappush(open_heap, (ng + h, nb))

    return [(gx, gy)]   # fallback: straight line


def _simplify(waypoints, sx, sy, rubble):
    """Remove collinear intermediate waypoints to reduce steering corrections."""
    if len(waypoints) <= 1:
        return waypoints
    pts = [(sx, sy)] + list(waypoints)
    keep = []
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1:
            # Check if the straight segment pts[i]→pts[j] is obstacle-free
            clear = True
            steps = max(2, int(math.hypot(pts[j][0]-pts[i][0], pts[j][1]-pts[i][1]) / (GRID_RES * 0.5)))
            for k in range(1, steps):
                t = k / steps
                mx = pts[i][0] + t * (pts[j][0] - pts[i][0])
                my = pts[i][1] + t * (pts[j][1] - pts[i][1])
                if _cell_blocked(mx, my, rubble):
                    clear = False
                    break
            if clear:
                break
            j -= 1
        if j > 0:
            keep.append(pts[j])
        i = j
    return keep if keep else waypoints


class RoverControllerNode(Node):

    def __init__(self):
        super().__init__('rover_controller_node')

        self.declare_parameter('position_tolerance', 0.5)
        self.declare_parameter('waypoint_tolerance', 0.6)
        self.declare_parameter('linear_speed', 0.15)
        self.declare_parameter('angular_speed', 0.5)
        self.declare_parameter('angular_gain', 0.3)
        self.declare_parameter('angle_threshold', 0.4)  # unused - kept for param compat
        self.declare_parameter('safe_distance', 0.55)
        self.declare_parameter('front_sector_deg', 30.0)
        self.declare_parameter('timeout', 300.0)
        self.declare_parameter('spawn_x', -2.0)
        self.declare_parameter('spawn_y', -2.0)
        self.declare_parameter('rubble_json', '')   # JSON list of [cx,cy,hlx,hly,yaw];
                                                       # empty -> DEFAULT_RUBBLE (Scenario A)

        self.position_tolerance = self.get_parameter('position_tolerance').value
        self.waypoint_tolerance = self.get_parameter('waypoint_tolerance').value
        self.linear_speed       = self.get_parameter('linear_speed').value
        self.angular_speed      = self.get_parameter('angular_speed').value
        self.angular_gain       = self.get_parameter('angular_gain').value
        self.angle_threshold    = self.get_parameter('angle_threshold').value
        self.safe_distance      = self.get_parameter('safe_distance').value
        self.front_sector_deg   = self.get_parameter('front_sector_deg').value
        self.timeout            = self.get_parameter('timeout').value

        rubble_json = self.get_parameter('rubble_json').value
        if rubble_json:
            self.rubble = [tuple(entry) for entry in json.loads(rubble_json)]
        else:
            self.rubble = DEFAULT_RUBBLE
        self.get_logger().info(f'Obstacle map: {len(self.rubble)} rubble entries loaded.')

        cb = ReentrantCallbackGroup()

        self.current_x   = None
        self.current_y   = None
        self.current_yaw = 0.0
        self.front_clearance = float('inf')
        self.left_clearance  = float('inf')
        self.right_clearance = float('inf')
        self.avoiding = False
        self._stop_event = threading.Event()   # set by tb3_stop to interrupt navigation

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=10,
        )
        self.create_subscription(Odometry,  '/odom', self._odom_cb, qos, callback_group=cb)
        self.create_subscription(LaserScan, '/scan', self._scan_cb, qos, callback_group=cb)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_service(NavigateTo, '/rover/navigate_to', self._handle_navigate_to,
                            callback_group=cb)
        self.create_service(Stop, '/rover/stop', self._handle_stop,
                            callback_group=cb)
        self.get_logger().info('Rover controller node ready.')

    # ------------------------------------------------------------------
    def _odom_cb(self, msg: Odometry):
        self.current_x = msg.pose.pose.position.x
        self.current_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        self.current_yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def _scan_cb(self, msg: LaserScan):
        n = len(msg.ranges)
        if n == 0:
            return
        sector = max(1, int(self.front_sector_deg))

        def sector_min(ci):
            best = float('inf')
            for off in range(-sector, sector + 1):
                r = msg.ranges[(ci + off) % n]
                if msg.range_min < r < msg.range_max:
                    best = min(best, r)
            return best

        self.front_clearance = sector_min(0)
        self.left_clearance  = sector_min(n // 8)   # 45° left
        self.right_clearance = sector_min(-n // 8)  # 45° right

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(a):
        while a >  math.pi: a -= 2 * math.pi
        while a < -math.pi: a += 2 * math.pi
        return a

    def _stop(self):
        self.cmd_vel_pub.publish(Twist())

    # ------------------------------------------------------------------
    def _drive_to_waypoint(self, wx, wy, tol, deadline, near_final_goal):
        """
        Drive to a single (wx, wy) waypoint.
        Returns True when within tol, False on timeout or launch failure.
        """
        rate_dt = 0.05   # 20 Hz for smoother steering
        clear_dist = self.safe_distance * 4.0

        while time.time() < deadline:
            if self._stop_event.is_set():
                return False   # interrupted by tb3_stop

            dx = wx - self.current_x
            dy = wy - self.current_y
            dist = math.hypot(dx, dy)

            if dist <= tol:
                return True

            heading_to_wp  = math.atan2(dy, dx)
            heading_error  = self._normalize(heading_to_wp - self.current_yaw)

            cmd = Twist()

            if self.avoiding:
                if self.front_clearance > clear_dist or near_final_goal:
                    self.avoiding = False
                else:
                    cmd.linear.x  = 0.0
                    cmd.angular.z = (self.angular_speed
                                     if self.left_clearance >= self.right_clearance
                                     else -self.angular_speed)

            if not self.avoiding:
                if not near_final_goal and self.front_clearance < self.safe_distance:
                    self.avoiding = True
                    cmd.linear.x  = 0.0
                    cmd.angular.z = (self.angular_speed
                                     if self.left_clearance >= self.right_clearance
                                     else -self.angular_speed)
                else:
                    # Smooth unicycle controller — no binary threshold.
                    # angular.z is proportional to heading error (clamped).
                    # linear.x scales with cos(heading_error): full speed when
                    # aligned, zero at 90°, so the robot naturally slows its
                    # forward motion while correcting heading.  This eliminates
                    # the bang-bang oscillation caused by switching between
                    # "rotate in place" and "drive forward" modes.
                    cmd.angular.z = max(-self.angular_speed,
                                        min(self.angular_speed,
                                            self.angular_gain * heading_error))
                    cmd.linear.x = self.linear_speed * max(0.0, math.cos(heading_error))

            self.cmd_vel_pub.publish(cmd)
            time.sleep(rate_dt)

        return False

    # ------------------------------------------------------------------
    def _handle_stop(self, request, response):
        self._stop_event.set()
        self._stop()
        response.success = True
        response.message = 'Stop command received; navigation interrupted'
        return response

    def _handle_navigate_to(self, request, response):
        self._stop_event.clear()   # reset before every new navigation
        tol = request.tolerance if request.tolerance > 0.0 else self.position_tolerance

        # Wait for first odom
        t0 = time.time()
        while self.current_x is None and time.time() - t0 < 10.0:
            time.sleep(0.1)
        if self.current_x is None:
            response.success = False
            response.message = 'No /odom received - is the rover spawned and running?'
            return response

        goal_x, goal_y = request.x, request.y
        deadline = t0 + self.timeout

        # Plan a collision-free path around known rubble
        waypoints = _astar(self.current_x, self.current_y, goal_x, goal_y, self.rubble)
        self.get_logger().info(
            f'A* planned {len(waypoints)} waypoints to ({goal_x:.1f},{goal_y:.1f}): '
            + ' → '.join(f'({x:.1f},{y:.1f})' for x, y in waypoints))

        # Follow each waypoint in sequence
        for i, (wx, wy) in enumerate(waypoints):
            is_last = (i == len(waypoints) - 1)
            wp_tol  = tol if is_last else self.waypoint_tolerance
            near_final = is_last  # suppress avoidance near victim marker

            self.get_logger().info(f'  → waypoint {i+1}/{len(waypoints)}: ({wx:.1f},{wy:.1f})')
            reached = self._drive_to_waypoint(wx, wy, wp_tol, deadline, near_final)
            if not reached:
                self._stop()
                response.success = False
                response.message = 'Timed out before reaching goal'
                return response

        self._stop()
        response.success = True
        response.message = f'Reached goal world=({goal_x:.2f}, {goal_y:.2f})'
        return response


def main(args=None):
    rclpy.init(args=args)
    node = RoverControllerNode()
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
