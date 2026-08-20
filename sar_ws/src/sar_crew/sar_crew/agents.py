"""CrewAI agent definitions for the search-and-rescue crew.

Three planner configurations for ablation study:

  full     — Full system: typed skill libraries + workflow contract.
  no_gate  — Skill list present but NO workflow contract
              (no context= dependency between search and rescue tasks).
  llm_only — No tools executed. LLM reasons in natural language; run_mission.py
              parses coordinates from crew output and dispatches rover manually.
              Post-run tool-reference scanning measures hallucination rate
              (tool names mentioned that do not exist in the real registry).
"""
from crewai import Agent, LLM

from sar_crew.tools import (
    IrisTakeoffTool,
    IrisSearchTargetTool,
    IrisGetCoordinatesTool,
    IrisFlyToTool,
    IrisLandTool,
    Tb3NavigateToTool,
    Tb3StopTool,
)

CONFIGS = ('full', 'no_gate', 'llm_only')

CONFIG_LABELS = {
    'full':     'Full System (Ours)',
    'no_gate':  'Skill-List (No Gate)',
    'llm_only': 'LLM-Only',
}

# Real tool names exposed to agents in full/no_gate configs.
# Repeated here so llm_only backstory can list them for hallucination testing.
_DRONE_TOOLS = 'iris_takeoff, iris_search_target, iris_get_coordinates, iris_fly_to, iris_land'
_ROVER_TOOLS = 'tb3_navigate_to, tb3_stop'


def build_llm(model: str = 'openrouter/openai/gpt-4o-mini') -> LLM:
    return LLM(model=model, temperature=0.2)


def build_aerial_recon_agent(llm: LLM, config: str = 'full') -> Agent:
    if config == 'llm_only':
        tools = []
        backstory = (
            'You are an experienced UAV operator supporting search-and-rescue missions. '
            'You do NOT have live robotic tool access in this configuration. '
            f'In a complete system your drone toolkit would be: {_DRONE_TOOLS}. '
            f'The ground toolkit would be: {_ROVER_TOOLS}. '
            'Reason from the provided zone description, describe your intended plan '
            'referencing these tool names where appropriate, and output explicit '
            'victim world-frame coordinates (x, y) based on your analysis.'
        )
        goal = (
            'Search the disaster area and output the victim\'s world-frame coordinates '
            '(x, y) as clearly as possible so the ground team can navigate to them.'
        )
    else:
        tools = [
            IrisTakeoffTool(),
            IrisSearchTargetTool(),
            IrisGetCoordinatesTool(),
            IrisFlyToTool(),
            IrisLandTool(),
        ]
        backstory = (
            'You are an experienced UAV operator supporting search-and-rescue missions. '
            'You operate the IRIS quadrotor equipped with a downward perception sensor. '
            'Your onboard perception bridge evaluates the camera feed through a '
            'Vision-Language Model and returns structured semantic scene descriptions. '
            'You are methodical: take off safely, sweep the area systematically, '
            'confirm any detection with iris_get_coordinates, then relay precise '
            'world-frame coordinates to the ground team before repositioning overhead.'
        )
        goal = (
            'Operate the IRIS drone to search the disaster area from the air. '
            'Use iris_takeoff to reach altitude, iris_search_target to sweep the '
            'search zone, and iris_get_coordinates to query the perception bridge '
            'and confirm victim localisation. Once the victim is found, fly to '
            'hover overhead with iris_fly_to to provide air support and mark the '
            'location for the ground rescue team.'
        )

    return Agent(
        role='Aerial Recon Pilot',
        goal=goal,
        backstory=backstory,
        tools=tools,
        llm=llm,
        verbose=True,
    )


def build_ground_rescue_agent(llm: LLM, config: str = 'full') -> Agent:
    if config == 'llm_only':
        tools = []
        backstory = (
            'You pilot a TurtleBot3 ground rover. In this configuration you have no '
            'live robotic tool access. '
            f'In a complete system your toolkit would be: {_ROVER_TOOLS}. '
            'Describe how you would navigate to the victim coordinates provided by '
            'the aerial recon pilot and confirm the plan.'
        )
        goal = 'Confirm you will navigate to the victim coordinates provided by the pilot.'
    else:
        tools = [Tb3NavigateToTool(), Tb3StopTool()]
        goal = (
            'Operate the TurtleBot3 ground rover to reach the victim. '
            'Wait in a staging phase until the aerial recon pilot publishes confirmed '
            'victim coordinates, then use tb3_navigate_to to drive to that location. '
            'Use tb3_stop only if navigation must be aborted to update coordinates.'
        )
        if config == 'no_gate':  # Skill-list baseline
            backstory = (
                'You pilot a TurtleBot3 ground rover equipped with LiDAR for obstacle '
                'avoidance and an A* path planner. You have access to tb3_navigate_to '
                'and tb3_stop. Navigate to wherever the victim is located.'
            )
        else:  # 'full'
            backstory = (
                'You pilot a TurtleBot3 ground rover equipped with LiDAR for obstacle '
                'avoidance and an A* path planner. You remain idle during the aerial '
                'search phase — the spatial and temporal workflow contract prevents you '
                'from moving until the Iris drone has completed its search and published '
                'confirmed world-frame victim coordinates through the RAO state interface. '
                'Once released, you navigate directly and efficiently to the victim.'
            )

    return Agent(
        role='Ground Rescue Operator',
        goal=goal,
        backstory=backstory,
        tools=tools,
        llm=llm,
        verbose=True,
        max_iter=5,
    )
