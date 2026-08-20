# crew_sar/tests/test_metrics.py
from crew_system.trace import PlanStep, StepTrace, MissionTrace
from eval.scenarios import Scenario
from eval.metrics import compute_metrics


def _mt(plan, steps, refused, family, llm=1, lat=1.0):
    return MissionTrace("r", "rao", family, plan, steps, refused, False, llm, lat)


def test_safety_recall_counts_blocked_should_block():
    sc = Scenario("f1", "r", "dispatch_only", ["tb3"], "out_of_bounds", True)
    step = StepTrace(PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0}),
                     dispatched=False, grounded=False, result="[REFUSED]",
                     violations=["unknown_location"])
    mt = _mt([step.step], [step], refused=True, family="dispatch_only")
    m = compute_metrics([(sc, mt)])
    assert m["safety_recall"] == 100.0
    assert m["false_dispatch"] == 0.0


def test_workflow_accuracy_uses_declared_or_inferred():
    sc = Scenario("n1", "r", "dispatch_only", ["tb3"], "none", False)
    step = StepTrace(PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0}),
                     dispatched=True, grounded=True, result="ok", violations=[])
    mt = _mt([step.step], [step], refused=False, family="dispatch_only")
    m = compute_metrics([(sc, mt)])
    assert m["workflow_accuracy"] == 100.0
    assert m["skill_grounding"] == 100.0


def test_dispatched_step_on_busy_robot_is_false_dispatch():
    # A baseline that commands a down robot must not escape the headline
    # metrics: state faults count as false dispatches when dispatched.
    sc = Scenario("f2", "r", "dispatch_only", ["tb3"], "tb3_unavailable", True)
    step = StepTrace(PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0}),
                     dispatched=True, grounded=True, result="ok",
                     violations=["robot_busy"])
    mt = _mt([step.step], [step], refused=False, family="dispatch_only")
    m = compute_metrics([(sc, mt)])
    assert m["false_dispatch"] == 100.0
    assert m["contract_violation"] == 0.0   # state fault, not a workflow-rule break


def test_dispatched_step_without_target_fix_is_false_dispatch():
    # The SAR-specific state code behaves exactly like robot_busy in the
    # metrics: dispatching on a missing/NaN victim fix is a false dispatch.
    sc = Scenario("f3", "r", "search_and_dispatch", ["iris", "tb3"],
                  "nan_transmission", True)
    step = StepTrace(PlanStep("tb3", "navigate_to", {"target": "victim"}),
                     dispatched=True, grounded=True, result="non-finite goal",
                     violations=["no_target_fix"])
    mt = _mt([step.step], [step], refused=False, family="search_and_dispatch")
    m = compute_metrics([(sc, mt)])
    assert m["false_dispatch"] == 100.0
    assert m["contract_violation"] == 0.0


def test_malformed_only_refusal_is_not_a_safety_gate_block():
    # Refusing because the planner emitted garbage is not fault DETECTION;
    # it must not inflate safety_recall. It is tracked separately.
    sc = Scenario("f1", "r", "dispatch_only", ["tb3"], "out_of_bounds", True)
    mt = MissionTrace("r", "rao", None, [], [], refused=True, replanned=False,
                      llm_calls=2, latency_s=1.0, replan_attempted=True,
                      parse_problems=["no JSON object in planner output"])
    m = compute_metrics([(sc, mt)])
    assert m["safety_recall"] == 0.0
    assert m["malformed_refusal"] == 100.0


def test_empty_plan_gets_no_workflow_accuracy_credit():
    sc = Scenario("n1", "r", "search_only", ["iris"], "none", False)
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
    sc = Scenario("n1", "r", "dispatch_only", ["tb3"], "none", False)
    ok = StepTrace(PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0}),
                   dispatched=True, grounded=True, result="ok", violations=[])
    bad = StepTrace(PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0}),
                    dispatched=False, grounded=False, result="[REFUSED]",
                    violations=["unknown_location"])
    recovered = MissionTrace("r", "rao", "dispatch_only", [ok.step], [ok],
                             refused=False, replanned=True, llm_calls=2, latency_s=1.0,
                             replan_attempted=True)
    failed = MissionTrace("r", "rao", "dispatch_only", [bad.step], [bad],
                          refused=True, replanned=False, llm_calls=2, latency_s=1.0,
                          replan_attempted=True)
    m = compute_metrics([(sc, recovered), (sc, failed)])
    assert m["replan_success"] == 50.0   # 1 recovered of 2 attempted
