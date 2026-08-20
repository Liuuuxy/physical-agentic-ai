"""Single decision-making agent for the dual-capable platform-selection demo."""
from crewai import Agent, LLM

from sar_crew.experiments.dual_capable.tools import (
    AssessReachabilityTool,
    DispatchDroneTool,
    DispatchRoverTool,
)


def build_llm(model: str = 'openrouter/openai/gpt-4o-mini') -> LLM:
    return LLM(model=model, temperature=0.2)


def build_mission_commander_agent(llm: LLM) -> Agent:
    return Agent(
        role='Mission Commander',
        goal=(
            'Reach the given target location using whichever platform — the '
            'IRIS drone or the TurtleBot3 rover — gets there more efficiently. '
            'Always call assess_reachability first to compare the two options, '
            'then dispatch exactly ONE platform (never both) using dispatch_drone '
            'or dispatch_rover.'
        ),
        backstory=(
            'You command a mixed air-ground robot team. Unlike a fixed '
            'recon-then-dispatch pipeline, you have direct command of both '
            'platforms and must choose the most efficient one for each mission '
            'based on real distance and obstacle data, not a default preference. '
            'Short, obstacle-free targets close to the rover staging area are '
            'usually faster for the rover to reach directly. Targets blocked by '
            'walls or requiring long ground detours are usually faster for the '
            'drone, which always flies a direct, unobstructed path.'
        ),
        tools=[
            AssessReachabilityTool(),
            DispatchDroneTool(),
            DispatchRoverTool(),
        ],
        llm=llm,
        verbose=True,
    )
