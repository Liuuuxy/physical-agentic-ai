#!/usr/bin/env python3
"""G1 joint indices, control gains, and reference poses."""

G1_NUM_MOTOR = 29


class G1Joint:
    # Leg joints (indices 0-11)
    LEFT_HIP_PITCH   = 0
    LEFT_HIP_ROLL    = 1
    LEFT_HIP_YAW     = 2
    LEFT_KNEE        = 3
    LEFT_ANKLE_PITCH = 4   # also LeftAnkleB
    LEFT_ANKLE_ROLL  = 5   # also LeftAnkleA

    RIGHT_HIP_PITCH   = 6
    RIGHT_HIP_ROLL    = 7
    RIGHT_HIP_YAW     = 8
    RIGHT_KNEE        = 9
    RIGHT_ANKLE_PITCH = 10  # also RightAnkleB
    RIGHT_ANKLE_ROLL  = 11  # also RightAnkleA

    # Waist (12-14, some may be locked on 23/29-dof versions)
    WAIST_YAW   = 12
    WAIST_ROLL  = 13  # INVALID on 23/29-dof waist-locked
    WAIST_PITCH = 14  # INVALID on 23/29-dof waist-locked

    # Left arm (15-21)
    LEFT_SHOULDER_PITCH = 15
    LEFT_SHOULDER_ROLL  = 16
    LEFT_SHOULDER_YAW   = 17
    LEFT_ELBOW          = 18
    LEFT_WRIST_ROLL     = 19
    LEFT_WRIST_PITCH    = 20  # INVALID on 23-dof
    LEFT_WRIST_YAW      = 21  # INVALID on 23-dof

    # Right arm (22-28)
    RIGHT_SHOULDER_PITCH = 22
    RIGHT_SHOULDER_ROLL  = 23
    RIGHT_SHOULDER_YAW   = 24
    RIGHT_ELBOW          = 25
    RIGHT_WRIST_ROLL     = 26
    RIGHT_WRIST_PITCH    = 27  # INVALID on 23-dof
    RIGHT_WRIST_YAW      = 28  # INVALID on 23-dof


# PD gains ---------------------------------------------------------------
# Legs need higher stiffness to support body weight.
# Arms need lower stiffness to avoid self-collision damage.
LEG_KP  = 100.0
LEG_KD  = 1.0
ARM_KP  = 50.0
ARM_KD  = 1.0
WRIST_KP = 30.0
WRIST_KD = 0.8


# Reference poses --------------------------------------------------------
# All values in radians.  Joints not listed default to 0.0.
# The robot should be standing upright before any manipulation task.

STANDING_POSE: dict[int, float] = {
    # Legs: slight knee bend for balance
    G1Joint.LEFT_HIP_PITCH:    -0.1,
    G1Joint.LEFT_KNEE:          0.2,
    G1Joint.LEFT_ANKLE_PITCH:  -0.1,
    G1Joint.RIGHT_HIP_PITCH:   -0.1,
    G1Joint.RIGHT_KNEE:         0.2,
    G1Joint.RIGHT_ANKLE_PITCH: -0.1,
    # Arms: neutral alongside body
    G1Joint.LEFT_SHOULDER_PITCH:  0.0,
    G1Joint.LEFT_SHOULDER_ROLL:   0.2,   # slightly out
    G1Joint.LEFT_ELBOW:           0.3,
    G1Joint.RIGHT_SHOULDER_PITCH: 0.0,
    G1Joint.RIGHT_SHOULDER_ROLL: -0.2,   # slightly out (mirror)
    G1Joint.RIGHT_ELBOW:          0.3,
}

# Fill unspecified joints with 0.0
for _i in range(G1_NUM_MOTOR):
    STANDING_POSE.setdefault(_i, 0.0)
