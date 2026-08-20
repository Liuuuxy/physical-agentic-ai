"""
Target definitions for the dual-capable platform-selection demo.

Both the IRIS drone and the TurtleBot3 rover are physically capable of
reaching every target here — the question this experiment answers is
whether the Mission Commander agent dynamically picks the more efficient
platform per-target, rather than always defaulting to one robot.

Geometry must mirror sar_gazebo/worlds/sar_world_dual.world exactly:
a single long wall at (3, 0) forces a real A* detour for the rover on
anything behind it, while the drone always flies a direct, unobstructed
path.
"""

ROVER_SPAWN_X = -2.0
ROVER_SPAWN_Y = -2.0
DRONE_SPAWN_X = 1.01     # PX4 sitl_run.sh default IRIS spawn offset
DRONE_SPAWN_Y = 0.98
DRONE_ALTITUDE = 5.0

# Single wall obstacle: (cx, cy, half_len_x, half_len_y, yaw_rad)
WALL_RUBBLE = [
    (3.0, 0.0, 4.0, 0.3, 1.5708),
]

# expected_platform is the platform a rational efficiency-based policy
# should choose; used only for scoring agreement, not given to the LLM.
TARGETS = {
    'rover_easy': {
        'x': -1.0, 'y': -3.0,
        'description': 'Close to the rover staging area, no obstacles in the way.',
        'expected_platform': 'rover',
    },
    'drone_easy': {
        'x': 8.0, 'y': 0.0,
        'description': 'Directly behind the long collapsed wall — the rover must '
                       'detour around one end while the drone flies straight over.',
        'expected_platform': 'drone',
    },
    'ambiguous': {
        'x': 3.0, 'y': -5.5,
        'description': 'South of the wall\'s end — reachable by either platform '
                       'with only a modest rover detour.',
        'expected_platform': None,   # no strong prior; logged for analysis only
    },
}


def get_target(name: str) -> dict:
    if name not in TARGETS:
        raise ValueError(f'Unknown target {name!r}. Choose from {list(TARGETS)}')
    return TARGETS[name]
