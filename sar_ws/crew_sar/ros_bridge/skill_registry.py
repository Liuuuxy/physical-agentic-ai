# crew_sar/ros_bridge/skill_registry.py
"""Skill registries for the air--ground SAR crew.

Grounding (contracts), dispatch (orchestrator), retrieval (prompt), and the
mock adapters all read these tables, mirroring GO2_SKILL_REGISTRY in
crew_g1_go2. Each entry maps a skill name to (adapter method, ((arg, default),
...)); REQUIRED_ARGS lists the arguments the planner must supply explicitly
(the rest fall back to the registry default at dispatch)."""

# Rover A* grid extent in rover_controller_node.py -- the operational area.
OPERATIONAL_BOUNDS = (-6.0, 10.0, -6.0, 10.0)  # x_min, x_max, y_min, y_max

DEFAULT_ALTITUDE = 5.0

# Symbolic rover-goal binding: resolved against the state interface at
# dispatch time (the drone's search publishes the fix; the plan cannot
# contain coordinates that do not exist yet).
VICTIM_TARGET = "victim"

# Ground-truth victim position of Scenario A (sar_world.world); the mock
# adapters use it the same way the Gazebo oracle does.
TRUE_VICTIM = (5.0, 5.0)

IRIS_SKILL_REGISTRY: dict[str, tuple[str, tuple]] = {
    "takeoff":         ("takeoff",         (("altitude", DEFAULT_ALTITUDE),)),
    "search_target":   ("search_target",   (("x_min", -5.5), ("x_max", 5.5),
                                            ("y_min", -5.5), ("y_max", 5.5),
                                            ("altitude", DEFAULT_ALTITUDE))),
    "get_coordinates": ("get_coordinates", ()),
    "fly_to":          ("fly_to",          (("x", 0.0), ("y", 0.0),
                                            ("z", DEFAULT_ALTITUDE))),
    "land":            ("land",            ()),
}

TB3_SKILL_REGISTRY: dict[str, tuple[str, tuple]] = {
    # navigate_to is dispatched specially (victim binding OR literal x, y);
    # the empty argspec keeps it out of the generic positional dispatch.
    "navigate_to": ("navigate_to", ()),
    "stop":        ("stop",        ()),
}

# Arguments the planner must state explicitly (missing -> missing_arg).
REQUIRED_ARGS: dict[str, tuple[str, ...]] = {
    "search_target": ("x_min", "x_max", "y_min", "y_max"),
    "fly_to": ("x", "y"),
}

# Skills advertised to the planner; the rest stay dispatchable but are not
# suggested (mirrors GO2_PLANNER_SKILLS).
IRIS_PLANNER_SKILLS: tuple[str, ...] = ("takeoff", "search_target",
                                        "get_coordinates", "land")
TB3_PLANNER_SKILLS: tuple[str, ...] = ("navigate_to", "stop")
