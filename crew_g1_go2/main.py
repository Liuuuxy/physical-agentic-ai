#!/usr/bin/env python3
"""
Entry point for the dual-robot CrewAI system.

Usage:
  source setup_env.sh
  python3 main.py                    # interactive REPL
  python3 main.py "carry box to room_b"   # single command

The script starts the ROS2 bridge in a daemon thread, then enters an
interactive loop that accepts natural-language commands from the user
and dispatches them to the CrewAI crew.
"""

import sys
import os

# ---------------------------------------------------------------------------
# Validate environment before importing ROS-dependent modules
# ---------------------------------------------------------------------------
SIM_MODE = os.environ.get("CREW_SIM") == "1"

if not SIM_MODE and not os.environ.get("AMENT_PREFIX_PATH"):
    print(
        "[ERROR] ROS2 environment not sourced.\n"
        "Run:  source setup_env.sh && python3 main.py\n"
        "Or for simulation (no ROS2):  CREW_SIM=1 python3 main.py"
    )
    sys.exit(1)

if not os.environ.get("OPENAI_API_KEY"):
    print(
        "[ERROR] OPENAI_API_KEY is not set.\n"
        "Export it before running:  export OPENAI_API_KEY=sk-..."
    )
    sys.exit(1)

# ---------------------------------------------------------------------------

from ros_bridge.bridge_node import get_bridge, shutdown_bridge
from crew_system.crew import run_mission

_SIM_LINE = "║   *** SIMULATION MODE – no robot hardware ***        ║\n" if SIM_MODE else ""
BANNER = f"""
╔══════════════════════════════════════════════════════╗
║   Dual-Robot CrewAI Controller                       ║
{_SIM_LINE}║   G1 Humanoid  (manipulation) → /user_lowcmd         ║
║   Go2 Quadruped (navigation)  → /goal_point          ║
╚══════════════════════════════════════════════════════╝
Type a task description, or:
  status   – show robot status
  tasks    – list G1 tasks
  locs     – list Go2 locations
  quit     – exit
"""

EXAMPLE_COMMANDS = [
    "grab the box from the table and wave",
    "navigate Go2 to table_a while G1 waves",
    "G1 grab the object from the table, then Go2 carry it to room_b, then G1 place it",
    "wave",
    "go to charging",
]


def print_status(g1, go2):
    print(f"  G1:  {g1.get_status() if g1 else 'disabled (GO2_ONLY mode)'}")
    print(f"  Go2: {go2.get_status()}")


def main():
    print(BANNER)

    print("Initialising ROS2 bridge…", end=" ", flush=True)
    g1, go2 = get_bridge()
    print("ready.")

    print("\nExample commands:")
    for ex in EXAMPLE_COMMANDS:
        print(f"  • {ex}")
    print()

    # Single-shot command from argv
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
        print(f"Running: {request}\n")
        result = run_mission(request)
        print(f"\n{'='*60}\nFinal result:\n{result}\n{'='*60}")
        shutdown_bridge()
        return

    # Interactive REPL
    try:
        while True:
            try:
                raw = input("\nTask> ").strip()
            except EOFError:
                break

            if not raw:
                continue

            lower = raw.lower()
            if lower in ("quit", "exit", "q"):
                break
            elif lower == "status":
                print_status(g1, go2)
            elif lower == "tasks":
                if g1:
                    print("  " + ", ".join(g1.available_tasks()))
                else:
                    print("  G1 disabled (GO2_ONLY mode)")
            elif lower == "locs":
                from ros_bridge.go2_controller import NAMED_LOCATIONS
                print("  " + ", ".join(NAMED_LOCATIONS.keys()))
            else:
                print(f"\nDispatching to CrewAI: {raw!r}\n")
                result = run_mission(raw)
                print(f"\n{'='*60}\nMission result:\n{result}\n{'='*60}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        print("Shutting down ROS2 bridge…")
        shutdown_bridge()
        print("Done.")


if __name__ == "__main__":
    main()
