#!/usr/bin/env python3
"""In-container skill-call helper for the RAO live path.

Runs INSIDE the sar-sim:humble container (docker cp'd to /tmp), where rclpy
and sar_msgs exist. One invocation = one skill: create a node, call the
matching ROS service, print a single JSON result line on stdout. The host-side
adapters (crew_sar/ros_bridge/gazebo_bridge.py) shell in via docker exec.

Usage: python3 rao_skill_call.py <skill> '<json args>'
"""
import json
import sys

import rclpy
from rclpy.node import Node
from sar_msgs.srv import (Takeoff, SearchArea, FlyTo, Land, PerceptionQuery,
                          NavigateTo, Stop)

# skill -> (service, type, request fields, call timeout s)
SPEC = {
    "takeoff":         ("/drone/takeoff", Takeoff, ("altitude",), 90.0),
    "search_target":   ("/drone/search_area", SearchArea,
                        ("x_min", "x_max", "y_min", "y_max", "altitude"), 1800.0),
    "get_coordinates": ("/drone/perception_query", PerceptionQuery,
                        ("drone_x", "drone_y"), 60.0),
    "fly_to":          ("/drone/fly_to", FlyTo, ("x", "y", "z", "tolerance"), 180.0),
    "land":            ("/drone/land", Land, (), 90.0),
    "navigate_to":     ("/rover/navigate_to", NavigateTo, ("x", "y", "tolerance"), 330.0),
    "stop":            ("/rover/stop", Stop, (), 15.0),
}


def _emit(payload):
    print(json.dumps(payload))
    sys.stdout.flush()


def _rover_pose(node):
    """One /odom sample -- used by the host for the delivery-error metric."""
    from nav_msgs.msg import Odometry
    pose = {}

    def cb(msg):
        pose["x"] = msg.pose.pose.position.x
        pose["y"] = msg.pose.pose.position.y

    from rclpy.qos import QoSProfile, ReliabilityPolicy
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(Odometry, "/odom", cb, qos)
    end = node.get_clock().now().nanoseconds + int(10e9)
    while "x" not in pose and node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.2)
    if "x" in pose:
        _emit({"ok": True, "x": pose["x"], "y": pose["y"]})
    else:
        _emit({"ok": False, "error": "no /odom sample within 10 s"})


def main():
    skill = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    rclpy.init()
    node = Node("rao_skill_call")
    try:
        if skill == "rover_pose":
            _rover_pose(node)
            return
        if skill not in SPEC:
            _emit({"ok": False, "error": f"unknown skill '{skill}'"})
            return
        srv_name, srv_type, fields, timeout = SPEC[skill]
        cli = node.create_client(srv_type, srv_name)
        if not cli.wait_for_service(timeout_sec=20.0):
            _emit({"ok": False, "error": f"service {srv_name} unavailable"})
            return
        req = srv_type.Request()
        for f in fields:
            if args.get(f) is not None:
                setattr(req, f, float(args[f]))
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=timeout)
        if not fut.done():
            _emit({"ok": False, "error": f"{srv_name} call timed out"})
            return
        res = fut.result()
        out = {"ok": True}
        for k in ("success", "message", "found", "victim_x", "victim_y",
                  "victim_z", "detected", "semantic_text"):
            if hasattr(res, k):
                out[k] = getattr(res, k)
        _emit(out)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
