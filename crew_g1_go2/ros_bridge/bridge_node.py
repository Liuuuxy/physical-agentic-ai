#!/usr/bin/env python3
"""
ROS2 bridge singleton.
Spins a single rclpy node in a daemon thread so CrewAI tools can call
G1/Go2 controllers from regular Python without managing the ROS executor.

Environment flags:
  CREW_SIM=1    – mock controllers, no ROS2 needed
  GO2_ONLY=1    – skip G1 init (no /user_lowcmd publisher, safe when G1 absent)
"""

import os
import threading

_SIM      = os.environ.get("CREW_SIM")   == "1"
_GO2_ONLY = os.environ.get("GO2_ONLY")   == "1"

if not _SIM:
    import rclpy
    from rclpy.node import Node
    from ros_bridge.go2_controller import Go2Controller

    if not _GO2_ONLY:
        from ros_bridge.g1_controller import G1Controller

    class RobotBridgeNode(Node):
        def __init__(self, g1, go2):
            super().__init__("robot_bridge")
            self._g1  = g1
            self._go2 = go2

            # --- Go2: goal publisher + pose subscriber ---
            from geometry_msgs.msg import PointStamped, PoseStamped

            # local_planner subscribes to /way_point (no far_planner in this stack)
            self._go2_goal_pub = self.create_publisher(PointStamped, "/way_point", 5)
            self._go2_pose_sub = self.create_subscription(
                PoseStamped, "/utlidar/robot_pose", self._go2_pose_cb, 10
            )
            go2.set_publish_fn(self._publish_go2_goal)

            # --- G1: 500 Hz publisher + state subscriber (skipped in GO2_ONLY) ---
            if g1 is not None:
                from unitree_hg.msg import LowCmd as HgLowCmd, LowState as HgLowState
                self._g1_cmd_pub   = self.create_publisher(HgLowCmd, "/user_lowcmd", 10)
                self._g1_state_sub = self.create_subscription(
                    HgLowState, "/lowstate", self._g1_state_cb, 10
                )
                self._g1_timer = self.create_timer(0.002, self._g1_tick)  # 500 Hz

            self.get_logger().info(
                f"RobotBridgeNode ready. GO2_ONLY={_GO2_ONLY}"
            )

        def _g1_tick(self):
            from unitree_hg.msg import LowCmd
            cmd = self._g1.get_next_cmd(LowCmd)
            self._g1_cmd_pub.publish(cmd)

        def _g1_state_cb(self, msg):
            self._g1.update_state(msg)

        def _go2_pose_cb(self, msg):
            self._go2.update_pose(msg)

        def _publish_go2_goal(self, x, y):
            from geometry_msgs.msg import PointStamped
            msg = PointStamped()
            msg.header.stamp    = self.get_clock().now().to_msg()
            msg.header.frame_id = "map"
            msg.point.x = x
            msg.point.y = y
            msg.point.z = 0.0
            self._go2_goal_pub.publish(msg)
            self.get_logger().info(f"Go2 goal → /way_point ({x:.2f}, {y:.2f})")


# ------------------------------------------------------------------
# Singleton management
# ------------------------------------------------------------------

_bridge_node = None
_g1_ctrl     = None
_go2_ctrl    = None
_spin_thread = None
_lock = threading.Lock()


def get_bridge():
    """
    Return (G1Controller or None, Go2Controller).
    Respects CREW_SIM and GO2_ONLY flags.
    Safe to call multiple times from any thread.
    """
    global _bridge_node, _g1_ctrl, _go2_ctrl, _spin_thread

    if _SIM:
        from ros_bridge.mock_bridge import MockG1Controller, MockGo2Controller
        g1 = None if _GO2_ONLY else MockG1Controller()
        return g1, MockGo2Controller()

    with _lock:
        if _bridge_node is not None:
            return _g1_ctrl, _go2_ctrl

        if not rclpy.ok():
            rclpy.init()

        _g1_ctrl  = None if _GO2_ONLY else G1Controller()
        _go2_ctrl = Go2Controller()
        _bridge_node = RobotBridgeNode(_g1_ctrl, _go2_ctrl)

        _spin_thread = threading.Thread(
            target=rclpy.spin,
            args=(_bridge_node,),
            daemon=True,
            name="ros2-bridge-spin",
        )
        _spin_thread.start()

    return _g1_ctrl, _go2_ctrl


def shutdown_bridge():
    global _bridge_node
    if _SIM:
        return
    with _lock:
        if _bridge_node is None:
            return
        _bridge_node.destroy_node()
        _bridge_node = None
    if rclpy.ok():
        rclpy.shutdown()
