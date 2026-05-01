from nestor_mcp.orchestration.state import WorkflowStatus
from nestor_mcp.services.task_service import TaskService
from nestor_mcp.tools.ha_gitops import format_ha_explain_tool_response, register_ha_gitops_tools
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse


def test_task_service_creates_task() -> None:
    task = TaskService().create("Water plants")

    assert task.title == "Water plants"
    assert task.completed is False


def test_format_ha_explain_tool_response_is_user_facing_text() -> None:
    text = format_ha_explain_tool_response(
        HaExplainResponse(
            run_id="haexp_test",
            status=WorkflowStatus.completed,
            answer="Les lumières s'allument car une présence est détectée.",
            referenced_files=["packages/areas/salon.yaml"],
            referenced_entities=["light.salon"],
            follow_up_suggestions=["Pourquoi après 10 minutes ?"],
        )
    )

    assert text.startswith("Les lumières s'allument")
    assert "Questions de suivi possibles" in text
    assert "haexp_test" in text
    assert "packages/areas/salon.yaml" not in text
    assert "light.salon" not in text


def test_ha_explain_tools_include_natural_behavior_alias() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("test", host="0.0.0.0")
    register_ha_gitops_tools(mcp)

    tool = mcp._tool_manager._tools["explain_smart_home_behavior"]

    assert "why something happens" in tool.description
    assert "lights turn on or off by themselves" in tool.description
    assert "Home Assistant configuration" in tool.description
