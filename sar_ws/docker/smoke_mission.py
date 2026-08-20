#!/usr/bin/env python3
"""Scripted smoke mission for the SAR sim.

Sequence: wait for services -> /drone/takeoff (5 m) -> /drone/search_area
(whole arena) -> /rover/navigate_to (victim coords from search) -> report
final /odom pose and delivery error. Prints a single JSON blob on the last
line for machine parsing.
"""
import json
import math
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from nav_msgs.msg import Odometry

from sar_msgs.srv import Takeoff, SearchArea, NavigateTo, Land

EXPECTED_SERVICES = [
    '/drone/takeoff', '/drone/search_area', '/drone/fly_to', '/drone/land',
    '/drone/perception_query', '/rover/navigate_to', '/rover/stop',
]

VICTIM_TRUTH = (5.0, 5.0)


class Smoke(Node):
    def __init__(self):
        super().__init__('smoke_mission')
        self.last_odom = None
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST, depth=5)
        self.create_subscription(Odometry, '/odom', self._odom_cb, qos)

    def _odom_cb(self, msg):
        self.last_odom = msg


def call_service(node, client, request, timeout_s):
    t0 = time.monotonic()
    fut = client.call_async(request)
    while rclpy.ok() and not fut.done():
        rclpy.spin_once(node, timeout_sec=0.5)
        if time.monotonic() - t0 > timeout_s:
            return None, time.monotonic() - t0
    return fut.result(), time.monotonic() - t0


def main():
    rclpy.init()
    node = Smoke()
    result = {'ok': False, 'stages': {}}

    # -- 1. wait for all services -------------------------------------------
    t0 = time.monotonic()
    deadline = t0 + 300.0
    missing = list(EXPECTED_SERVICES)
    while missing and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.5)
        names = {n for n, _ in node.get_service_names_and_types()}
        missing = [s for s in EXPECTED_SERVICES if s not in names]
        if missing:
            time.sleep(2.0)
    result['stages']['services'] = {
        'all_present': not missing,
        'missing': missing,
        'wait_s': round(time.monotonic() - t0, 1),
    }
    if missing:
        print(json.dumps(result))
        return 1

    takeoff_cli = node.create_client(Takeoff, '/drone/takeoff')
    search_cli = node.create_client(SearchArea, '/drone/search_area')
    nav_cli = node.create_client(NavigateTo, '/rover/navigate_to')
    land_cli = node.create_client(Land, '/drone/land')
    for c in (takeoff_cli, search_cli, nav_cli, land_cli):
        c.wait_for_service(timeout_sec=30.0)

    # -- 2. takeoff (retry: EKF/arming may not be ready right after boot) ---
    attempts = []
    resp = None
    for attempt in range(3):
        req = Takeoff.Request(); req.altitude = 5.0
        resp, dt = call_service(node, takeoff_cli, req, 300.0)
        attempts.append({
            'success': bool(resp.success) if resp else False,
            'message': resp.message if resp else 'TIMEOUT',
            'wall_s': round(dt, 1),
        })
        if resp and resp.success:
            break
        time.sleep(20.0)
    result['stages']['takeoff'] = {'attempts': attempts,
                                   'success': bool(resp and resp.success)}
    if not resp or not resp.success:
        print(json.dumps(result))
        return 1

    # -- 3. search area -----------------------------------------------------
    req = SearchArea.Request()
    req.x_min, req.x_max = -5.5, 5.5
    req.y_min, req.y_max = -5.5, 5.5
    req.altitude = 5.0
    resp, dt = call_service(node, search_cli, req, 1200.0)
    found = bool(resp.found) if resp else False
    vx = float(resp.victim_x) if resp else float('nan')
    vy = float(resp.victim_y) if resp else float('nan')
    result['stages']['search'] = {
        'found': found,
        'victim_x': vx, 'victim_y': vy,
        'victim_z': float(resp.victim_z) if resp else float('nan'),
        'message': resp.message if resp else 'TIMEOUT',
        'wall_s': round(dt, 1),
        'err_vs_truth_m': round(math.hypot(vx - VICTIM_TRUTH[0],
                                           vy - VICTIM_TRUTH[1]), 3) if found else None,
    }
    if not found:
        print(json.dumps(result))
        return 1

    # -- 4. rover navigate to victim ---------------------------------------
    req = NavigateTo.Request()
    req.x, req.y = vx, vy
    req.tolerance = 0.0   # use node default (0.5 m)
    resp, dt = call_service(node, nav_cli, req, 600.0)
    nav_ok = bool(resp.success) if resp else False
    result['stages']['navigate'] = {
        'success': nav_ok,
        'message': resp.message if resp else 'TIMEOUT',
        'wall_s': round(dt, 1),
    }

    # -- 5. final odom pose -------------------------------------------------
    t0 = time.monotonic()
    while node.last_odom is None and time.monotonic() - t0 < 15.0:
        rclpy.spin_once(node, timeout_sec=0.5)
    if node.last_odom is not None:
        # TB3's gazebo diff-drive plugin publishes world-frame odometry
        # (odometry_source=world), and rover_controller_node treats /odom as
        # world coords directly - so no spawn offset is applied here.
        ox = node.last_odom.pose.pose.position.x
        oy = node.last_odom.pose.pose.position.y
        result['stages']['final_pose'] = {
            'odom_world_xy': [round(ox, 3), round(oy, 3)],
            'err_vs_victim_reported_m': round(math.hypot(ox - vx, oy - vy), 3),
            'err_vs_truth_5_5_m': round(math.hypot(ox - VICTIM_TRUTH[0],
                                                   oy - VICTIM_TRUTH[1]), 3),
        }
    else:
        result['stages']['final_pose'] = {'error': 'no /odom received'}

    # -- 6. land the drone (best effort) ------------------------------------
    resp, dt = call_service(node, land_cli, Land.Request(), 120.0)
    result['stages']['land'] = {
        'success': bool(resp.success) if resp else False,
        'wall_s': round(dt, 1),
    }

    result['ok'] = nav_ok
    print(json.dumps(result))
    return 0 if nav_ok else 1


if __name__ == '__main__':
    sys.exit(main())
