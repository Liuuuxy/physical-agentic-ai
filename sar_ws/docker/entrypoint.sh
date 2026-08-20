#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
if [ -f /sar_ws/install/setup.bash ]; then
    source /sar_ws/install/setup.bash
fi
export TURTLEBOT3_MODEL=waffle
exec "$@"
