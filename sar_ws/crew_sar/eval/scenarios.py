import os
from dataclasses import dataclass

import yaml

_DEFAULT = os.path.join(os.path.dirname(__file__), "scenarios.yaml")


@dataclass
class Scenario:
    id: str
    request: str
    expected_family: str
    expected_robots: list
    fault: str
    should_block: bool


def load_scenarios(path=None):
    with open(path or _DEFAULT) as f:
        rows = yaml.safe_load(f)
    return [Scenario(**row) for row in rows]
