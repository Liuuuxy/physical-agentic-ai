#!/usr/bin/env python3
"""
Hard-coded G1 manipulation task sequences.

Each sequence is a list of keyframe dicts:
  label     – human-readable step name (for logging)
  duration  – seconds to interpolate to this position from the previous
  positions – {joint_index: target_angle_rad}

Only joints listed in 'positions' are actively driven; all others hold
their current angles.  Leg joints are never listed here so the standing
controller keeps them stable.

NOTE: These angles are initial reference values tuned for a tabletop
      grab at roughly 0.8 m height, 0.5 m in front of the robot.
      Fine-tune on the actual hardware before deploying.
"""

from g1_tasks.joint_configs import G1Joint

# ---------------------------------------------------------------------------
# GRAB_FROM_TABLE  – right arm picks up an object from a table in front
# ---------------------------------------------------------------------------
GRAB_FROM_TABLE: list[dict] = [
    dict(
        label="approach",
        duration=2.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.5,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.15,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           0.4,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
    dict(
        label="reach_forward",
        duration=1.5,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 1.1,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           0.9,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
    dict(
        label="lower_to_object",
        duration=1.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 1.3,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.2,
            G1Joint.RIGHT_WRIST_ROLL:     -0.4,
        },
    ),
    dict(
        label="grasp_pause",      # dwell at grasp position (no gripper on G1)
        duration=0.8,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 1.3,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.2,
            G1Joint.RIGHT_WRIST_ROLL:     -0.4,
        },
    ),
    dict(
        label="lift",
        duration=1.5,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.5,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.5,
            G1Joint.RIGHT_WRIST_ROLL:     -0.4,
        },
    ),
    dict(
        label="carry_hold",
        duration=1.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.3,
            G1Joint.RIGHT_SHOULDER_ROLL:   0.0,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.5,
            G1Joint.RIGHT_WRIST_ROLL:     -0.4,
        },
    ),
]

# ---------------------------------------------------------------------------
# PLACE_ON_TABLE  – right arm places the object back on a table
# ---------------------------------------------------------------------------
PLACE_ON_TABLE: list[dict] = [
    dict(
        label="extend_to_table",
        duration=1.5,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.9,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.0,
            G1Joint.RIGHT_WRIST_ROLL:     -0.4,
        },
    ),
    dict(
        label="lower_to_surface",
        duration=1.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 1.2,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           1.1,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,   # release orientation
        },
    ),
    dict(
        label="release_pause",
        duration=0.8,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 1.2,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_ELBOW:           1.1,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
    dict(
        label="retract",
        duration=2.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.0,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_SHOULDER_YAW:    0.0,
            G1Joint.RIGHT_ELBOW:           0.3,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
    dict(
        label="return_neutral",
        duration=1.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.0,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_ELBOW:           0.3,
        },
    ),
]

# ---------------------------------------------------------------------------
# WAVE  – right-arm wave (good for testing without risk of self-collision)
# ---------------------------------------------------------------------------
WAVE: list[dict] = [
    dict(
        label="raise_arm",
        duration=1.5,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: -0.3,
            G1Joint.RIGHT_SHOULDER_ROLL:  -1.0,
            G1Joint.RIGHT_ELBOW:           0.5,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
    *[
        dict(
            label=f"wave_{n}",
            duration=0.5,
            positions={
                G1Joint.RIGHT_SHOULDER_PITCH: -0.3,
                G1Joint.RIGHT_SHOULDER_ROLL:  -1.0,
                G1Joint.RIGHT_ELBOW:           1.2,
                G1Joint.RIGHT_WRIST_ROLL:      0.6 if n % 2 == 0 else -0.6,
            },
        )
        for n in range(4)
    ],
    dict(
        label="lower_arm",
        duration=1.5,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.0,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_ELBOW:           0.3,
            G1Joint.RIGHT_WRIST_ROLL:      0.0,
        },
    ),
]

# ---------------------------------------------------------------------------
# HAND_OVER  – both arms move to a front-centre hand-over position
# ---------------------------------------------------------------------------
HAND_OVER: list[dict] = [
    dict(
        label="extend_both",
        duration=2.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.8,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.1,
            G1Joint.RIGHT_ELBOW:           1.0,
            G1Joint.LEFT_SHOULDER_PITCH:   0.8,
            G1Joint.LEFT_SHOULDER_ROLL:    0.1,
            G1Joint.LEFT_ELBOW:            1.0,
        },
    ),
    dict(
        label="hold_2s",
        duration=2.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.8,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.1,
            G1Joint.RIGHT_ELBOW:           1.0,
            G1Joint.LEFT_SHOULDER_PITCH:   0.8,
            G1Joint.LEFT_SHOULDER_ROLL:    0.1,
            G1Joint.LEFT_ELBOW:            1.0,
        },
    ),
    dict(
        label="retract_both",
        duration=2.0,
        positions={
            G1Joint.RIGHT_SHOULDER_PITCH: 0.0,
            G1Joint.RIGHT_SHOULDER_ROLL:  -0.2,
            G1Joint.RIGHT_ELBOW:           0.3,
            G1Joint.LEFT_SHOULDER_PITCH:   0.0,
            G1Joint.LEFT_SHOULDER_ROLL:    0.2,
            G1Joint.LEFT_ELBOW:            0.3,
        },
    ),
]

# ---------------------------------------------------------------------------
# Registry – maps task names to sequences
# ---------------------------------------------------------------------------
TASK_REGISTRY: dict[str, list[dict]] = {
    "grab_from_table": GRAB_FROM_TABLE,
    "place_on_table":  PLACE_ON_TABLE,
    "wave":            WAVE,
    "hand_over":       HAND_OVER,
}
