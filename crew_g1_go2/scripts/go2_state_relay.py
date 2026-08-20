#!/usr/bin/env python3
"""
Relay /lowstate (unitree_go/msg/LowState) → /my_go2_lowstate
so the Go2 state stream is type-unambiguous and safe for consumption.

Run in a separate terminal BEFORE main.py:
  source <repo>/crew_g1_go2/setup_env.sh
  python3 scripts/go2_state_relay.py
"""

import rclpy
from rclpy.node import Node
from unitree_go.msg import LowState


class Go2StateRelay(Node):
    def __init__(self):
        super().__init__("go2_state_relay")
        self._pub = self.create_publisher(LowState, "/my_go2_lowstate", 10)
        self._sub = self.create_subscription(
            LowState, "/lowstate", self._cb, 10
        )
        self.get_logger().info(
            "Relaying /lowstate (unitree_go) → /my_go2_lowstate"
        )

    def _cb(self, msg: LowState) -> None:
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = Go2StateRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
