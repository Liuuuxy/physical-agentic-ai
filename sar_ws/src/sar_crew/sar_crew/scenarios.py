"""
Scenario definitions for the air-ground Search-and-Dispatch experiment.

Each scenario varies the victim position and obstacle layout while keeping
the rover spawn fixed, so results across scenarios are directly comparable.
This module is the single source of truth — the Gazebo world files
(sar_gazebo/worlds/sar_world_{a,b,c}.world) and the rover's A* obstacle map
(rover_controller_node's `rubble_json` parameter) must mirror these values
exactly. Keep them in sync if you edit a scenario here.

Each rubble entry is (cx, cy, half_len_x, half_len_y, yaw_rad) — matching the
RUBBLE format expected by rover_controller_node.py's A* planner.
"""

ROVER_SPAWN_X = -2.0
ROVER_SPAWN_Y = -2.0

SCENARIOS = {
    'a': {
        'label': 'Scenario A — baseline (NE victim, scattered obstacles)',
        'world_file': 'sar_world.world',
        'victim_x': 5.0,
        'victim_y': 5.0,
        'victim_z': 0.0,
        'rubble': [
            (4.0,  3.0,  1.0,  0.75, 0.4),    # rubble_1 (2 x 1.5 m, 23°)
            (-3.0, 5.0,  0.75, 0.75, -0.3),   # rubble_2 (1.5 x 1.5 m, -17°)
            (2.0,  -4.0, 1.5,  0.5,  0.9),    # rubble_3 (3 x 1 m, 52°)
        ],
        'search_bounds': {'x_min': -3.0, 'x_max': 8.0, 'y_min': -3.0, 'y_max': 8.0},
        'world_hint': (
            'Known static obstacles: a rubble pile at approx (4, 3), a wall '
            'section at (-3, 5), and debris at (2, -4).'
        ),
    },
    'b': {
        'label': 'Scenario B — near-field NW victim, single blocking wall',
        'world_file': 'sar_world_b.world',
        'victim_x': -3.0,
        'victim_y': 4.0,
        'victim_z': 0.0,
        'rubble': [
            (-2.5, 1.0,  1.6,  0.3,  1.4),    # long wall directly across the
                                               # straight-line path spawn→victim,
                                               # forces a genuine A* detour
            (1.0,  2.0,  0.5,  0.5,  0.0),    # scattered debris
            (-5.0, -1.0, 0.6,  0.6,  0.5),    # scattered debris
        ],
        'search_bounds': {'x_min': -8.0, 'x_max': 3.0, 'y_min': -3.0, 'y_max': 8.0},
        'world_hint': (
            'Known static obstacles: a long collapsed wall at approx (-2.5, 1) '
            'directly blocking the direct path from the rover staging area, '
            'plus scattered debris at (1, 2) and (-5, -1).'
        ),
    },
    'c': {
        'label': 'Scenario C — far-field SE victim, clustered obstacles',
        'world_file': 'sar_world_c.world',
        'victim_x': 8.0,
        'victim_y': -4.0,
        'victim_z': 0.0,
        'rubble': [
            (2.0, -1.0, 1.0, 1.0, 0.2),
            (4.0, -3.0, 1.3, 0.6, 1.0),
            (6.0, -1.0, 0.8, 0.8, -0.5),
            (3.0, -5.0, 1.5, 0.5, 0.3),
        ],
        'search_bounds': {'x_min': -2.0, 'x_max': 9.0, 'y_min': -9.0, 'y_max': 2.0},
        'world_hint': (
            'Known static obstacles: a dense cluster of four debris piles '
            'between (2,-1) and (6,-1), with additional rubble at (3,-5), '
            'lying directly between the rover staging area and the search zone.'
        ),
    },
}


def get_scenario(name: str) -> dict:
    name = name.lower()
    if name not in SCENARIOS:
        raise ValueError(f'Unknown scenario {name!r}. Choose from {list(SCENARIOS)}')
    return SCENARIOS[name]
