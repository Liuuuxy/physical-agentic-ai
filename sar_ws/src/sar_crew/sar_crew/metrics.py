"""
Per-run metrics collection for the ablation study.

Metrics
-------
grounding_ok       : LLM successfully extracted valid victim coordinates
assignment_ok      : extracted/navigated-to coords within ASSIGNMENT_THRESHOLD of truth
false_dispatch     : rover dispatched before victim was confirmed by perception
localization_error : Euclidean distance (reported victim - true victim), metres
delivery_error     : Euclidean distance (rover final position - true victim), metres
llm_call_count     : number of agent-step LLM calls during the run
"""
import math
import re
import threading

TRUE_VICTIM_X = 5.0
TRUE_VICTIM_Y = 5.0
ASSIGNMENT_THRESHOLD = 2.0    # metres — coords are "accurate" if within this

# Canonical tool names in the real skill registry.
# llm_only post-processing checks LLM output against this set to detect hallucinations.
REAL_TOOL_NAMES: frozenset = frozenset({
    'iris_takeoff', 'iris_search_target', 'iris_get_coordinates',
    'iris_fly_to', 'iris_land', 'tb3_navigate_to', 'tb3_stop',
})


def set_true_victim(x: float, y: float) -> None:
    """Override the ground-truth victim position (call before each run when
    switching scenarios — see scenarios.py)."""
    global TRUE_VICTIM_X, TRUE_VICTIM_Y
    TRUE_VICTIM_X = float(x)
    TRUE_VICTIM_Y = float(y)

_COORD_PATTERNS = [
    # "VICTIM_COORDINATES: x=5.00, y=5.01" (our tool format)
    r'VICTIM_COORDINATES:\s*x\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*y\s*=\s*(-?\d+(?:\.\d+)?)',
    # "x = 5.0, y = 5.0" or "x=5, y=5"
    r'\bx\s*=\s*(-?\d+(?:\.\d+)?)\s*,?\s*y\s*=\s*(-?\d+(?:\.\d+)?)',
    # "coordinates (5.0, 5.0)" or "location 5.0, 5.0"
    r'(?:coordinates?|location|position)\s*[:\(]?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)',
    # "at (5.0, 5.0)"
    r'\bat\s+\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?',
    # "5.0, 5.0" bare pair (last resort, greedy)
    r'\b(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\b',
]


class MetricsCollector:
    """Thread-safe singleton metrics store, reset before each run."""
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.reset()

    @classmethod
    def instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = MetricsCollector()
            return cls._instance

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            inst = MetricsCollector()
            cls._instance = inst
        return inst

    # ------------------------------------------------------------------
    def reset(self):
        self.grounding_ok = False
        self.assignment_ok = False
        self.false_dispatch = False
        self.localization_error = float('nan')
        self.delivery_error = float('nan')
        self.llm_call_count = 0
        self._reported_vx = float('nan')
        self._reported_vy = float('nan')
        self._victim_confirmed = False
        # tool hallucination tracking (llm_only config only)
        self.tool_ref_count = 0
        self.tool_hallucination_count = 0

    # ------------------------------------------------------------------
    # Called by IrisSearchTargetTool / IrisGetCoordinatesTool (after fault injection)
    def record_localization(self, reported_vx: float, reported_vy: float,
                            detected: bool) -> None:
        if detected and not math.isnan(reported_vx) and not math.isnan(reported_vy):
            self._reported_vx = reported_vx
            self._reported_vy = reported_vy
            self._victim_confirmed = True
            self.grounding_ok = True
            err = math.hypot(reported_vx - TRUE_VICTIM_X,
                             reported_vy - TRUE_VICTIM_Y)
            self.localization_error = err
            self.assignment_ok = err <= ASSIGNMENT_THRESHOLD
        else:
            self.grounding_ok = False
            self.assignment_ok = False

    # Called by Tb3NavigateToTool before sending to RosBridge
    def record_navigate(self, x: float, y: float) -> None:
        if not self._victim_confirmed:
            self.false_dispatch = True
        if not math.isnan(x) and not math.isnan(y):
            err = math.hypot(x - TRUE_VICTIM_X, y - TRUE_VICTIM_Y)
            self.assignment_ok = err <= ASSIGNMENT_THRESHOLD

    # Called after crew finishes (all configs), from run_mission.py
    def record_delivery(self, rover_x: float, rover_y: float) -> None:
        if not math.isnan(rover_x) and not math.isnan(rover_y):
            self.delivery_error = math.hypot(
                rover_x - TRUE_VICTIM_X, rover_y - TRUE_VICTIM_Y)

    def increment_llm_calls(self) -> None:
        self.llm_call_count += 1

    # ------------------------------------------------------------------
    # Used by llm_only baseline: scan output for tool-call references and
    # classify them as real (in REAL_TOOL_NAMES) or hallucinated.
    @staticmethod
    def detect_tool_refs(text: str):
        """Return (total_refs, hallucinated_count, hallucinated_names).

        Detects snake_case identifiers used as function calls or backtick-
        quoted names in the LLM output.  Anything not in REAL_TOOL_NAMES is
        counted as a hallucination.
        """
        # func_name( call syntax
        p1 = re.findall(
            r'\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\s*\(',
            text, re.IGNORECASE)
        # `func_name` backtick-quoted references
        p2 = re.findall(
            r'`([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)`',
            text, re.IGNORECASE)
        # de-duplicate, lower-case
        unique_refs = {m.lower() for m in p1 + p2
                       if '_' in m}           # skip single-word identifiers
        hallucinated = [r for r in unique_refs if r not in REAL_TOOL_NAMES]
        return len(unique_refs), len(hallucinated), hallucinated

    # ------------------------------------------------------------------
    # Used by llm_only baseline: parse (vx, vy) from raw crew text output
    @staticmethod
    def parse_coords_from_text(text: str):
        """Return (vx, vy) tuple or (nan, nan) if parsing fails."""
        for pat in _COORD_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    vx, vy = float(m.group(1)), float(m.group(2))
                    if -50 < vx < 50 and -50 < vy < 50:
                        return vx, vy
                except (ValueError, IndexError):
                    pass
        return float('nan'), float('nan')

    # ------------------------------------------------------------------
    def summary(self) -> dict:
        plan_exec = int(self.grounding_ok and self.assignment_ok)
        hallu_rate = (self.tool_hallucination_count / self.tool_ref_count
                      if self.tool_ref_count > 0 else float('nan'))
        return {
            'grounding_ok':            int(self.grounding_ok),
            'assignment_ok':           int(self.assignment_ok),
            'plan_executability':      plan_exec,
            'false_dispatch':          int(self.false_dispatch),
            'localization_error':      self.localization_error,
            'delivery_error':          self.delivery_error,
            'llm_call_count':          self.llm_call_count,
            'tool_ref_count':          self.tool_ref_count,
            'tool_hallucination_count': self.tool_hallucination_count,
            'tool_hallucination_rate': hallu_rate,
        }
