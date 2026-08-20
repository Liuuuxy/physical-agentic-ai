"""Crew + task definitions for the search-and-rescue mission.

Three planner configurations for the ablation study:

  full      — Full system: iris_*/tb3_* typed tools + workflow contract
               (context=[search_task] enforces idle staging).
  no_gate   — Skill list present but NO workflow contract (no context= dependency).
               Rover agent may be dispatched without confirmed victim coordinates.
  llm_only  — No tools executed. Agents reason from natural language context.
               run_mission.py parses crew output and dispatches rover manually.
               Post-run tool-reference scan measures hallucination rate.
"""
from typing import Callable, Optional

from crewai import Crew, Process, Task

from sar_crew.agents import build_llm, build_aerial_recon_agent, build_ground_rescue_agent, CONFIGS
from sar_crew.scenarios import SCENARIOS, ROVER_SPAWN_X, ROVER_SPAWN_Y


def build_crew(search_bounds: dict, search_altitude: float = 5.0, config: str = 'full',
               scenario: str = 'a', step_callback: Optional[Callable] = None):
    """Build the SAR crew for the given planner configuration.

    config: 'full' | 'no_gate' | 'llm_only'
    scenario: 'a' | 'b' | 'c' — selects the victim/obstacle world hint used
        by the llm_only baseline (see scenarios.py).
    """
    if config not in CONFIGS:
        raise ValueError(f'Unknown config {config!r}. Choose from {CONFIGS}')
    if scenario not in SCENARIOS:
        raise ValueError(f'Unknown scenario {scenario!r}. Choose from {list(SCENARIOS)}')

    world_hint = (
        'The disaster zone is a partially collapsed urban structure. '
        f'{SCENARIOS[scenario]["world_hint"]} '
        'The victim is a person somewhere in the search zone. '
        f'Rover spawn position: ({ROVER_SPAWN_X}, {ROVER_SPAWN_Y}). True north is +Y axis.'
    )

    llm = build_llm()
    drone_agent = build_aerial_recon_agent(llm, config)
    rover_agent = build_ground_rescue_agent(llm, config)

    # Shared task inputs
    x_min, x_max = search_bounds['x_min'], search_bounds['x_max']
    y_min, y_max = search_bounds['y_min'], search_bounds['y_max']
    alt = search_altitude

    # ------------------------------------------------------------------
    # Task 1: Aerial search
    # ------------------------------------------------------------------
    if config == 'llm_only':
        search_desc = (
            f'You are the Aerial Recon Pilot conducting a search-and-rescue mission.\n'
            f'{world_hint}\n'
            f'Search zone: x∈[{x_min},{x_max}], y∈[{y_min},{y_max}] at altitude {alt}m.\n'
            f'You do NOT have robotic tools in this configuration. Based on the zone '
            f'description and typical victim positions in this disaster scenario, '
            f'reason about where the victim is most likely to be located and output '
            f'your best estimate of their world-frame coordinates in the form:\n'
            f'  VICTIM_COORDINATES: x=<float>, y=<float>\n'
            f'Explain your reasoning briefly.'
        )
        search_expected = (
            'A natural language assessment of the search zone and an explicit '
            'VICTIM_COORDINATES: x=<float>, y=<float> statement.'
        )
    else:
        search_desc = (
            'Execute the aerial search-and-dispatch phase:\n'
            '1. Call iris_takeoff with altitude={altitude} to arm and climb.\n'
            '2. Call iris_search_target to sweep x∈[{x_min},{x_max}], '
            'y∈[{y_min},{y_max}] at altitude={altitude}. The tool queries the '
            'onboard perception bridge at each waypoint.\n'
            '3. When a victim is reported, call iris_get_coordinates with the '
            "drone's current position to get the VLM-verified semantic description "
            'and precise world-frame coordinates.\n'
            '4. Call iris_fly_to (victim_x, victim_y, {altitude}) to hover overhead '
            'and mark the location for the ground team.\n'
            'Report the confirmed victim world-frame coordinates (x, y) clearly '
            'so the Ground Rescue Operator can use them.'
        )
        search_expected = (
            'Confirmed victim world-frame coordinates (x, y) extracted from the '
            'perception bridge semantic output, plus confirmation that the drone '
            'is hovering overhead.'
        )

    search_task = Task(
        description=search_desc,
        expected_output=search_expected,
        agent=drone_agent,
    )

    # ------------------------------------------------------------------
    # Task 2: Ground dispatch
    # ------------------------------------------------------------------
    if config == 'llm_only':
        rescue_desc = (
            'You are the Ground Rescue Operator. The aerial recon pilot has '
            'reported victim coordinates in the task above. Read those coordinates '
            'and confirm your navigation plan to reach the victim. State clearly '
            'what path you would take and confirm the destination coordinates.'
        )
        rescue_expected = 'Confirmation of the navigation plan to the victim.'
        rescue_context = []   # no structured context — part of the baseline test
    elif config == 'no_gate':
        rescue_desc = (
            'Ground rescue dispatch — navigate the rover to the victim:\n'
            '1. Determine the victim\'s location (coordinates may be in prior context '
            'or you may need to reason from available information).\n'
            '2. Call tb3_navigate_to(x, y) to drive the TurtleBot3 rover to the victim.\n'
            '3. Confirm arrival.\n'
            'Use tb3_stop only if navigation must be aborted.'
        )
        rescue_expected = 'Confirmation that the TurtleBot3 rover has reached the victim.'
        rescue_context = []   # no workflow gate — tests effect of missing contract
    else:  # 'full'
        rescue_desc = (
            'Ground rescue dispatch — IDLE STAGING until victim coordinates are received:\n'
            '1. Wait for the Aerial Recon Pilot to publish confirmed victim coordinates '
            'through the context interface (this is enforced by the workflow contract).\n'
            '2. Extract the victim x, y coordinates from the aerial recon output.\n'
            '3. Call tb3_navigate_to(x, y) to drive the TurtleBot3 rover directly '
            'to the victim, avoiding obstacles via A* planning and reactive LiDAR.\n'
            '4. Confirm arrival.\n'
            'Only call tb3_stop if navigation must be aborted to update coordinates.'
        )
        rescue_expected = 'Confirmation that the TurtleBot3 rover has reached the victim\'s location.'
        rescue_context = [search_task]   # enforces idle staging constraint

    rescue_task = Task(
        description=rescue_desc,
        expected_output=rescue_expected,
        agent=rover_agent,
        context=rescue_context,
    )

    crew_kwargs = dict(
        agents=[drone_agent, rover_agent],
        tasks=[search_task, rescue_task],
        process=Process.sequential,
        verbose=True,
    )
    if step_callback is not None:
        crew_kwargs['step_callback'] = step_callback

    crew = Crew(**crew_kwargs)

    inputs = {
        'altitude': search_altitude,
        'x_min': x_min,
        'x_max': x_max,
        'y_min': y_min,
        'y_max': y_max,
    }
    return crew, inputs
