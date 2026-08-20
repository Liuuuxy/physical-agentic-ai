# crew_g1_go2/crew_system/routers.py
"""Live CrewAI router adapters for each baseline. Imported lazily so tests
that inject a fake router never import crewai or touch the network."""

from crew_system.contract_spec import families_json_list

PLAN_SCHEMA = (
    'Return ONLY JSON: {"workflow_family": one of '
    f'{families_json_list()}, '
    '"steps": [{"robot":"g1"|"go2","skill":str,"args":{}}]}.'
)


def router_config(baseline):
    """Return (with_tools, schema) for a baseline. All baselines emit the
    structured plan; only tool retrieval differs."""
    with_tools = baseline in ("skill-list", "rao-prompt", "rao")
    return with_tools, PLAN_SCHEMA


def build_instructions(baseline, feedback=None):
    """Pure builder for the planner's extra instructions: schema + format
    example + push-based retrieval context (+ replan feedback). Hermetically
    testable without crewai."""
    from crew_system.retrieval import retrieval_context, FORMAT_EXAMPLE

    parts = [PLAN_SCHEMA, FORMAT_EXAMPLE]
    ctx = retrieval_context(baseline)
    if ctx:
        parts.append(ctx)
    if feedback:
        parts.append(
            "Your previous plan was REJECTED (" + feedback + "). Produce a "
            "corrected plan using ONLY valid skill/location names and the "
            "correct workflow family and ordering."
        )
    return "\n\n".join(parts)


def live_router(request, baseline, feedback=None):
    from crewai import Crew, Process
    from crew_system.agents import make_task_router
    from crew_system.tasks import make_routing_task

    with_tools, _ = router_config(baseline)
    extra = build_instructions(baseline, feedback)
    router = make_task_router(with_tools=with_tools)
    task = make_routing_task(router, request, extra_instructions=extra)
    crew = Crew(agents=[router], tasks=[task], process=Process.sequential, verbose=False)
    result = crew.kickoff()
    return str(result), 1
