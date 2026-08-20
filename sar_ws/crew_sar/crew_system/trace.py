from dataclasses import dataclass, field, asdict


@dataclass
class PlanStep:
    robot: str
    skill: str
    args: dict = field(default_factory=dict)


@dataclass
class StepTrace:
    step: PlanStep
    dispatched: bool
    grounded: bool
    result: str
    violations: list[str] = field(default_factory=list)


@dataclass
class MissionTrace:
    request: str
    baseline: str
    declared_family: str | None
    plan: list[PlanStep]
    steps: list[StepTrace]
    refused: bool = False
    replanned: bool = False
    llm_calls: int = 0
    latency_s: float = 0.0
    # Fields below were appended after release so positional construction of
    # the original nine stays valid.
    replan_attempted: bool = False
    parse_problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
