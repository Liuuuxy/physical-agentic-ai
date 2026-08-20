"""
Fault injection for ablation / baseline experiments.

Wraps RosBridge calls to simulate failure scenarios that distinguish the
workflow contract (ours) from the skill-list baseline (no gate).

Fault modes
-----------
none              : no injection (nominal runs)
corrupted_coords  : victim XY perturbed by Gaussian noise (sigma = 5 m, clipped to scenario bounds)
nan_transmission  : victim XY replaced with NaN (simulates dropped packet)
missed_detection  : iris_search_target forced to return found=False
blocked_corridor  : rover navigation forced to return success=False

Usage
-----
    fi = FaultInjector('corrupted_coords')
    found, msg, vx, vy, vz = fi.inject_search(found, msg, vx, vy, vz)
"""
import math
import random
import threading
from dataclasses import dataclass, field

FAULT_MODES = [
    'none',
    'corrupted_coords',
    'nan_transmission',
    'missed_detection',
    'blocked_corridor',
]

TRUE_VICTIM_X = 5.0
TRUE_VICTIM_Y = 5.0
COORD_NOISE_SIGMA = 5.0   # metres — large enough to cause mis-delivery


def set_true_victim(x: float, y: float) -> None:
    """Override the ground-truth victim position (call before each run when
    switching scenarios — see scenarios.py)."""
    global TRUE_VICTIM_X, TRUE_VICTIM_Y
    TRUE_VICTIM_X = float(x)
    TRUE_VICTIM_Y = float(y)


@dataclass
class FaultInjector:
    fault: str = 'none'
    # Scenario search bounds for clipping corrupted coordinates.
    # Tuple (x_min, x_max, y_min, y_max). None = no clipping.
    bounds: object = None

    # internal bookkeeping
    _reported_vx: float = field(default=float('nan'), repr=False, init=False)
    _reported_vy: float = field(default=float('nan'), repr=False, init=False)
    false_dispatches: int = field(default=0, repr=False, init=False)

    def __post_init__(self):
        if self.fault not in FAULT_MODES:
            raise ValueError(f'Unknown fault mode {self.fault!r}. '
                             f'Choose from {FAULT_MODES}')

    def _clip(self, cx: float, cy: float):
        """Clip coords to bounds so corrupted coords stay within the world."""
        if self.bounds is not None:
            x_min, x_max, y_min, y_max = self.bounds
            cx = max(x_min, min(x_max, cx))
            cy = max(y_min, min(y_max, cy))
        return cx, cy

    # ------------------------------------------------------------------
    def inject_search(self, found, message, vx, vy, vz):
        """Inject fault into iris_search_target result."""
        if self.fault == 'missed_detection':
            self._reported_vx = float('nan')
            self._reported_vy = float('nan')
            return (False,
                    '[FAULT:missed_detection] Search complete — victim not detected',
                    0.0, 0.0, 0.0)

        if found and self.fault == 'nan_transmission':
            self._reported_vx = float('nan')
            self._reported_vy = float('nan')
            return (True,
                    '[FAULT:nan_transmission] ' + message,
                    float('nan'), float('nan'), vz)

        if found and self.fault == 'corrupted_coords':
            cx, cy = self._clip(vx + random.gauss(0, COORD_NOISE_SIGMA),
                                vy + random.gauss(0, COORD_NOISE_SIGMA))
            self._reported_vx = cx
            self._reported_vy = cy
            return (True,
                    f'[FAULT:corrupted_coords] ' + message,
                    cx, cy, vz)

        # no fault / fault does not apply here
        self._reported_vx = vx
        self._reported_vy = vy
        return found, message, vx, vy, vz

    def inject_perception(self, detected, text, vx, vy):
        """Inject fault into iris_get_coordinates / perception_query result."""
        if self.fault == 'missed_detection':
            return False, '[FAULT:missed_detection] No human visible in frame', 0.0, 0.0
        if detected and self.fault == 'nan_transmission':
            return True, '[FAULT:nan_transmission] ' + text, float('nan'), float('nan')
        if detected and self.fault == 'corrupted_coords':
            cx, cy = self._clip(vx + random.gauss(0, COORD_NOISE_SIGMA),
                                vy + random.gauss(0, COORD_NOISE_SIGMA))
            return True, '[FAULT:corrupted_coords] ' + text, cx, cy
        return detected, text, vx, vy

    def check_navigate_dispatch(self, x, y) -> bool:
        """
        Return True and increment counter if this tb3_navigate_to call
        constitutes a false dispatch (called with invalid or absent coords).
        """
        is_false = (math.isnan(x) or math.isnan(y)
                    or math.isnan(self._reported_vx)
                    or math.isnan(self._reported_vy))
        if is_false:
            self.false_dispatches += 1
        return is_false

    def inject_navigate(self, success, message):
        """Inject fault into tb3_navigate_to result."""
        if self.fault == 'blocked_corridor':
            return (False,
                    '[FAULT:blocked_corridor] Navigation failed: '
                    'corridor blocked by debris — rover cannot reach goal')
        return success, message

    # ------------------------------------------------------------------
    def localization_error(self, reported_vx: float, reported_vy: float) -> float:
        """Euclidean error between reported and true victim position (metres)."""
        if math.isnan(reported_vx) or math.isnan(reported_vy):
            return float('nan')
        return math.hypot(reported_vx - TRUE_VICTIM_X,
                          reported_vy - TRUE_VICTIM_Y)


# ---------------------------------------------------------------------------
# Module-level singleton — run_mission.py sets this before each run
# ---------------------------------------------------------------------------
_active_injector: 'FaultInjector | None' = None
_injector_lock = threading.Lock()


def set_active_injector(fi: 'FaultInjector') -> None:
    global _active_injector
    with _injector_lock:
        _active_injector = fi


def get_active_injector() -> 'FaultInjector':
    global _active_injector
    with _injector_lock:
        if _active_injector is None:
            _active_injector = FaultInjector('none')
        return _active_injector
