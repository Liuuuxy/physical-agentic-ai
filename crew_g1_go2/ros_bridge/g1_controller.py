#!/usr/bin/env python3
"""G1 humanoid task state machine and CRC computation."""

import ctypes
import struct
import threading
import time
from enum import Enum, auto
from typing import Optional

from g1_tasks.joint_configs import (
    G1_NUM_MOTOR, G1Joint,
    ARM_KP, ARM_KD, LEG_KP, LEG_KD,
    STANDING_POSE,
)
from g1_tasks.sequences import TASK_REGISTRY


class TaskState(Enum):
    IDLE = auto()
    EXECUTING = auto()


# --- CRC structs matching C LowCmd memory layout ---

class _MotorCmdRaw(ctypes.Structure):
    _fields_ = [
        ("mode",    ctypes.c_uint8),
        ("_pad",    ctypes.c_uint8 * 3),
        ("q",       ctypes.c_float),
        ("dq",      ctypes.c_float),
        ("tau",     ctypes.c_float),
        ("Kp",      ctypes.c_float),
        ("Kd",      ctypes.c_float),
        ("reserve", ctypes.c_uint32),
    ]


class _LowCmdRaw(ctypes.Structure):
    _fields_ = [
        ("modePr",      ctypes.c_uint8),
        ("modeMachine", ctypes.c_uint8),
        ("_pad",        ctypes.c_uint8 * 2),
        ("motorCmd",    _MotorCmdRaw * 35),
        ("reserve",     ctypes.c_uint32 * 4),
        ("crc",         ctypes.c_uint32),
    ]


def _compute_crc(msg) -> int:
    """Port of Unitree's crc32_core / get_crc from motor_crc_hg.cpp."""
    raw = _LowCmdRaw()
    raw.modePr      = msg.mode_pr
    raw.modeMachine = msg.mode_machine
    for i in range(35):
        raw.motorCmd[i].mode    = msg.motor_cmd[i].mode
        raw.motorCmd[i].q       = msg.motor_cmd[i].q
        raw.motorCmd[i].dq      = msg.motor_cmd[i].dq
        raw.motorCmd[i].tau     = msg.motor_cmd[i].tau
        raw.motorCmd[i].Kp      = msg.motor_cmd[i].kp
        raw.motorCmd[i].Kd      = msg.motor_cmd[i].kd
        raw.motorCmd[i].reserve = msg.motor_cmd[i].reserve
    for i in range(4):
        raw.reserve[i] = msg.reserve[i]

    # CRC over all bytes except the final crc field (last 4 bytes)
    n_bytes = ctypes.sizeof(_LowCmdRaw) - 4
    buf = bytes(raw)[:n_bytes]
    words = struct.unpack(f"{len(buf) // 4}I", buf)

    crc = 0xFFFFFFFF
    poly = 0x04C11DB7
    for word in words:
        xbit = 1 << 31
        data = word
        for _ in range(32):
            if crc & 0x80000000:
                crc = ((crc << 1) & 0xFFFFFFFF) ^ poly
            else:
                crc = (crc << 1) & 0xFFFFFFFF
            if data & xbit:
                crc ^= poly
            xbit >>= 1
    return crc


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


class G1Controller:
    """
    Manages G1 manipulation task execution.
    Call execute_task(name) from a CrewAI tool – it blocks until done.
    The ROS bridge node calls get_next_cmd() at 500 Hz.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._done = threading.Event()

        self._state = TaskState.IDLE
        self._sequence: list = []
        self._frame_idx: int = 0
        self._frame_elapsed: float = 0.0

        # Joint positions at the start of the current frame (for interpolation)
        self._frame_start: dict[int, float] = dict(STANDING_POSE)
        # Live joint positions from robot state
        self._current_q: dict[int, float] = dict(STANDING_POSE)
        self._mode_machine: int = 0

        self._task_result: str = ""

    # ------------------------------------------------------------------
    # Called by the ROS state subscriber (background thread)
    # ------------------------------------------------------------------
    def update_state(self, msg) -> None:
        with self._lock:
            self._mode_machine = int(msg.mode_machine)
            for i in range(G1_NUM_MOTOR):
                self._current_q[i] = float(msg.motor_state[i].q)

    # ------------------------------------------------------------------
    # Called by the ROS 500 Hz timer (background thread)
    # ------------------------------------------------------------------
    def get_next_cmd(self, msg_factory):
        """Return a populated unitree_hg/msg/LowCmd ready to publish."""
        from unitree_hg.msg import LowCmd, MotorCmd  # imported lazily

        cmd = msg_factory()
        cmd.mode_pr = 0
        with self._lock:
            cmd.mode_machine = self._mode_machine
            target = self._compute_target()

        for i in range(G1_NUM_MOTOR):
            mc = MotorCmd()
            mc.mode = 1  # position control enabled
            mc.q    = target.get(i, 0.0)
            mc.dq   = 0.0
            mc.tau  = 0.0
            mc.kp   = LEG_KP if i < 15 else ARM_KP
            mc.kd   = LEG_KD if i < 15 else ARM_KD
            cmd.motor_cmd[i] = mc

        cmd.crc = _compute_crc(cmd)
        return cmd

    def _compute_target(self) -> dict[int, float]:
        """Interpolate within the current keyframe; advance frames as needed."""
        if self._state == TaskState.IDLE or not self._sequence:
            return dict(self._current_q)

        frame = self._sequence[self._frame_idx]
        duration = frame["duration"]
        t = self._frame_elapsed / duration if duration > 0 else 1.0
        self._frame_elapsed += 0.002  # 2 ms tick

        positions = {}
        for idx, q_target in frame["positions"].items():
            q_start = self._frame_start.get(idx, self._current_q.get(idx, 0.0))
            positions[idx] = _lerp(q_start, q_target, t)

        # Fill non-specified joints from current state
        for i in range(G1_NUM_MOTOR):
            if i not in positions:
                positions[i] = self._current_q.get(i, 0.0)

        if self._frame_elapsed >= duration:
            # Snapshot the reached position as start for the next frame
            for idx, q in frame["positions"].items():
                self._frame_start[idx] = q
            self._frame_idx += 1
            self._frame_elapsed = 0.0

            if self._frame_idx >= len(self._sequence):
                self._state = TaskState.IDLE
                self._sequence = []
                self._task_result = "Task completed successfully."
                self._done.set()

        return positions

    # ------------------------------------------------------------------
    # Public API for CrewAI tools (caller thread)
    # ------------------------------------------------------------------
    def execute_task(self, task_name: str, timeout: float = 60.0) -> str:
        """
        Block until the named task sequence finishes or timeout expires.
        Returns a status string.
        """
        if task_name not in TASK_REGISTRY:
            return f"Unknown task '{task_name}'. Available: {list(TASK_REGISTRY)}"

        with self._lock:
            if self._state == TaskState.EXECUTING:
                return "G1 is already executing a task. Wait for it to finish."
            self._sequence = TASK_REGISTRY[task_name]
            self._frame_idx = 0
            self._frame_elapsed = 0.0
            self._frame_start = dict(self._current_q)
            self._state = TaskState.EXECUTING
            self._task_result = ""

        self._done.clear()
        finished = self._done.wait(timeout=timeout)
        if not finished:
            with self._lock:
                self._state = TaskState.IDLE
                self._sequence = []
            return f"Task '{task_name}' timed out after {timeout}s."
        return self._task_result

    def get_status(self) -> str:
        with self._lock:
            if self._state == TaskState.IDLE:
                return "G1 is idle."
            frame = self._sequence[self._frame_idx] if self._sequence else {}
            return (
                f"G1 executing frame {self._frame_idx + 1}/{len(self._sequence)} "
                f"'{frame.get('label', '?')}' "
                f"({self._frame_elapsed:.1f}s / {frame.get('duration', 0):.1f}s)"
            )

    def available_tasks(self) -> list[str]:
        return list(TASK_REGISTRY.keys())
