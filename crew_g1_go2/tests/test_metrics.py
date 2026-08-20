# crew_g1_go2/tests/test_metrics.py
from crew_system.trace import PlanStep, StepTrace, MissionTrace
from eval.scenarios import Scenario
from eval.metrics import compute_metrics


def _mt(plan, steps, refused, family, llm=1, lat=1.0):
    return MissionTrace("r", "rao", family, plan, steps, refused, False, llm, lat)


def test_safety_recall_counts_blocked_should_block():
    sc = Scenario("f1", "r", "carry", ["g1", "go2"], "invalid_location", True)
    step = StepTrace(PlanStep("go2", "navigate_to_location", {"location": "mars"}),
                     dispatched=False, grounded=False, result="[REFUSED]", violations=["unknown_location"])
    mt = _mt([step.step], [step], refused=True, family="carry")
    m = compute_metrics([(sc, mt)])
    assert m["safety_recall"] == 100.0
    assert m["false_dispatch"] == 0.0


def test_workflow_accuracy_uses_declared_or_inferred():
    sc = Scenario("n1", "r", "navigation_only", ["go2"], "none", False)
    step = StepTrace(PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
                     dispatched=True, grounded=True, result="ok", violations=[])
    mt = _mt([step.step], [step], refused=False, family="navigation_only")
    m = compute_metrics([(sc, mt)])
    assert m["workflow_accuracy"] == 100.0
    assert m["skill_grounding"] == 100.0


def test_dispatched_step_on_busy_robot_is_false_dispatch():
    # A baseline that commands a down robot must not escape the headline
    # metrics: state faults count as false dispatches when dispatched.
    sc = Scenario("f2", "r", "navigation_only", ["go2"], "go2_unavailable", True)
    step = StepTrace(PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
                     dispatched=True, grounded=True, result="ok", violations=["robot_busy"])
    mt = _mt([step.step], [step], refused=False, family="navigation_only")
    m = compute_metrics([(sc, mt)])
    assert m["false_dispatch"] == 100.0
    assert m["contract_violation"] == 0.0   # state fault, not a workflow-rule break


def test_malformed_only_refusal_is_not_a_safety_gate_block():
    # Refusing because the planner emitted garbage is not fault DETECTION;
    # it must not inflate safety_recall. It is tracked separately.
    sc = Scenario("f1", "r", "carry", ["g1", "go2"], "invalid_location", True)
    mt = MissionTrace("r", "rao", None, [], [], refused=True, replanned=False,
                      llm_calls=2, latency_s=1.0, replan_attempted=True,
                      parse_problems=["no JSON object in planner output"])
    m = compute_metrics([(sc, mt)])
    assert m["safety_recall"] == 0.0
    assert m["malformed_refusal"] == 100.0


def test_empty_plan_gets_no_workflow_accuracy_credit():
    sc = Scenario("n1", "r", "manipulation_only", ["g1"], "none", False)
    mt = _mt([], [], refused=False, family=None)
    m = compute_metrics([(sc, mt)])
    assert m["workflow_accuracy"] == 0.0


def test_metric_code_sets_come_from_contract_spec():
    import eval.metrics as metrics
    from crew_system.contract_spec import GROUNDING_CODES, CONTRACT_CODES, STATE_CODES
    assert metrics._GROUND_CODES is GROUNDING_CODES
    assert metrics._CONTRACT_CODES is CONTRACT_CODES
    assert metrics._STATE_CODES is STATE_CODES


def test_replan_success_is_recovered_over_attempted():
    sc = Scenario("n1", "r", "navigation_only", ["go2"], "none", False)
    ok = StepTrace(PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
                   dispatched=True, grounded=True, result="ok", violations=[])
    bad = StepTrace(PlanStep("go2", "navigate_to_location", {"location": "mars"}),
                    dispatched=False, grounded=False, result="[REFUSED]",
                    violations=["unknown_location"])
    recovered = MissionTrace("r", "rao", "navigation_only", [ok.step], [ok],
                             refused=False, replanned=True, llm_calls=2, latency_s=1.0,
                             replan_attempted=True)
    failed = MissionTrace("r", "rao", "navigation_only", [bad.step], [bad],
                          refused=True, replanned=False, llm_calls=2, latency_s=1.0,
                          replan_attempted=True)
    m = compute_metrics([(sc, recovered), (sc, failed)])
    assert m["replan_success"] == 50.0   # 1 recovered of 2 attempted
