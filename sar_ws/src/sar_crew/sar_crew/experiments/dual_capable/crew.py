"""Single-task crew for the dual-capable platform-selection demo."""
from typing import Callable, Optional

from crewai import Crew, Process, Task

from sar_crew.experiments.dual_capable.agents import build_llm, build_mission_commander_agent


def build_crew(target_x: float, target_y: float, target_description: str,
               step_callback: Optional[Callable] = None):
    llm = build_llm()
    commander = build_mission_commander_agent(llm)

    task = Task(
        description=(
            f'A target has been located at world-frame coordinates '
            f'(x={target_x}, y={target_y}). Context: {target_description}\n'
            f'1. Call assess_reachability({target_x}, {target_y}) to compare '
            f'the drone\'s direct flight distance against the rover\'s '
            f'obstacle-aware ground path distance.\n'
            f'2. Based on those numbers, dispatch the platform that reaches '
            f'the target with less total distance/time — call EITHER '
            f'dispatch_drone({target_x}, {target_y}) OR '
            f'dispatch_rover({target_x}, {target_y}), not both.\n'
            f'3. Report which platform you chose and why.'
        ),
        expected_output=(
            'A clear statement of which platform (drone or rover) was dispatched, '
            'the reachability numbers that justified the choice, and confirmation '
            'of arrival.'
        ),
        agent=commander,
    )

    crew_kwargs = dict(
        agents=[commander],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    if step_callback is not None:
        crew_kwargs['step_callback'] = step_callback

    return Crew(**crew_kwargs)
