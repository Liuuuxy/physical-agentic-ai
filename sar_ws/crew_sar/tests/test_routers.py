import subprocess
import sys

from crew_system.routers import router_config, PLAN_SCHEMA


def test_all_baselines_get_the_plan_schema():
    for b in ("llm-only", "skill-list", "rao-prompt", "rao"):
        with_tools, schema = router_config(b)
        assert schema == PLAN_SCHEMA
        assert "JSON" in schema


def test_tool_retrieval_gating():
    assert router_config("llm-only")[0] is False
    assert router_config("skill-list")[0] is True
    assert router_config("rao-prompt")[0] is True
    assert router_config("rao")[0] is True


def test_importing_routers_does_not_import_crewai():
    # Run in a subprocess so we start with a clean import state.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import crew_system.routers; import sys; "
            "assert 'crewai' not in sys.modules, 'crewai was imported at module level'",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
