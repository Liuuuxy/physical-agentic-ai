# Air-ground SAR simulation: ROS2 Humble + Gazebo Classic 11 + PX4 SITL 1.14 + MAVROS + TurtleBot3
# Build:  docker build -t sar-sim:humble .
FROM ros:humble

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

# ---------------------------------------------------------------------------
# Layer 1: apt dependencies (ROS pkgs, Gazebo classic 11, MAVROS, TB3, build tools)
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo git wget curl ca-certificates gnupg2 lsb-release rsync \
    build-essential cmake ninja-build ccache \
    python3-pip python3-dev python3-colcon-common-extensions \
    python3-jinja2 python3-empy python3-numpy python3-yaml \
    gazebo libgazebo-dev \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-turtlebot3-gazebo \
    ros-humble-robot-state-publisher \
    ros-humble-mavros ros-humble-mavros-extras \
    geographiclib-tools \
    protobuf-compiler libprotobuf-dev \
    libeigen3-dev libopencv-dev libxml2-utils \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-good \
 && rm -rf /var/lib/apt/lists/*

# MAVROS needs the GeographicLib datasets (geoid model) or it dies on startup
RUN /opt/ros/humble/lib/mavros/install_geographiclib_datasets.sh

# ---------------------------------------------------------------------------
# Layer 2: PX4-Autopilot release/1.14 (shallow clone + submodules)
# ---------------------------------------------------------------------------
RUN git clone --branch release/1.14 --depth 1 \
        https://github.com/PX4/PX4-Autopilot.git /px4/PX4-Autopilot \
 && cd /px4/PX4-Autopilot \
 && (git submodule update --init --recursive --depth 1 \
     || git submodule update --init --recursive)

# ---------------------------------------------------------------------------
# Layer 3: PX4 toolchain deps (pip requirements etc.); tolerate partial failure
# of the apt section since layer 1 already installs the sim build deps.
# ---------------------------------------------------------------------------
RUN cd /px4/PX4-Autopilot \
 && (bash Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools \
     || pip3 install -r Tools/setup/requirements.txt) \
 && pip3 install -r Tools/setup/requirements.txt

# ---------------------------------------------------------------------------
# Layer 4: build PX4 SITL + gazebo-classic plugins (DONT_RUN prevents launching)
# ---------------------------------------------------------------------------
# NuttX is not needed for SITL, and px_update_git_header.py crashes on the
# shallow-cloned NuttX submodule (no nuttx-* tags fetched) - deinit it so the
# script's `platforms/nuttx/NuttX/nuttx/.git` existence check turns false.
RUN cd /px4/PX4-Autopilot \
 && (git submodule deinit -f platforms/nuttx/NuttX/nuttx platforms/nuttx/NuttX/apps || true) \
 && DONT_RUN=1 make px4_sitl gazebo-classic_iris

# ---------------------------------------------------------------------------
# Layer 5: SAR workspace (sar_msgs, sar_robot_control, sar_gazebo)
# ---------------------------------------------------------------------------
COPY sar_src/ /sar_ws/src/
RUN source /opt/ros/humble/setup.bash \
 && cd /sar_ws \
 && colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release

# ---------------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------------
ENV TURTLEBOT3_MODEL=waffle \
    PX4_AUTOPILOT_DIR=/px4/PX4-Autopilot

COPY entrypoint.sh /entrypoint.sh
COPY smoke_mission.py /sar_ws/smoke_mission.py
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
