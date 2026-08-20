#!/usr/bin/env python3
"""Log ground-truth model poses from /model_states to CSV at ~4 Hz.
Runs inside the sar container:  python3 /tmp/traj_logger.py /tmp/traj.csv
"""
import sys
import time

import rclpy
from rclpy.node import Node
from gazebo_msgs.msg import ModelStates

TRACKED = ("iris", "waffle")


class TrajLogger(Node):
    def __init__(self, path):
        super().__init__("traj_logger")
        self.f = open(path, "w")
        self.f.write("t,model,x,y,z\n")
        self.t0 = time.time()
        self.last = 0.0
        self.create_subscription(ModelStates, "/model_states", self.cb, 10)

    def cb(self, msg):
        now = time.time()
        if now - self.last < 0.25:
            return
        self.last = now
        for name, pose in zip(msg.name, msg.pose):
            if name in TRACKED:
                p = pose.position
                self.f.write(f"{now - self.t0:.2f},{name},"
                             f"{p.x:.3f},{p.y:.3f},{p.z:.3f}\n")
        self.f.flush()


def main():
    rclpy.init()
    rclpy.spin(TrajLogger(sys.argv[1]))


if __name__ == "__main__":
    main()
