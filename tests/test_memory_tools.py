"""Tests for the deliberate memory tools."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import llm

from custom_components.local_openai.const import (
    TOOL_NAME_RECALL_MEMORY,
    TOOL_NAME_REMEMBER,
)
from custom_components.local_openai.tools.memory import (
    RememberFactTool,
    SearchMemoryTool,
    build_memory_tools,
)


class FakeMemory:
    """Stand-in for HindsightMemory, recording what the tools ask for."""

    def __init__(
        self,
        *,
        stored: bool = True,
        recalled: str = "Lives in Timaru",
        recall_enabled: bool = True,
    ) -> None:
        """Initialize the fake."""
        self.stored = stored
        self.recalled = recalled
        self.recall_enabled = recall_enabled
        self.remembered: list[str] = []
        self.queries: list[str] = []

    async def async_remember(self, text: str) -> bool:
        """Record a remembered fact."""
        self.remembered.append(text)
        return self.stored

    async def async_recall(self, query: str) -> str:
        """Record a query and return canned memories."""
        self.queries.append(query)
        return self.recalled


def make_context() -> llm.LLMContext:
    """Return a minimal LLM context for a tool call."""
    return llm.LLMContext(
        platform="test",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
        agent_id="conversation.test_agent",
    )


async def call(tool: llm.Tool, **tool_args: Any) -> llm.ToolResult:
    """Call a tool the way the chat log does."""
    tool_input = llm.ToolInput(tool_name=tool.name, tool_args=tool_args)
    return await tool.async_call(  # type: ignore[arg-type]
        hass=None, tool_input=tool_input, llm_context=make_context()
    )


async def test_remember_tool_stores_the_fact() -> None:
    """The tool hands a normalised fact to the bank."""
    memory = FakeMemory()
    result = await call(
        RememberFactTool(memory), fact="  The   bins go out on Tuesday  "
    )

    assert result.data == {"stored": True}
    assert result.error is False
    assert memory.remembered == ["The bins go out on Tuesday"]


async def test_remember_tool_reports_when_memory_is_unavailable() -> None:
    """A failed write is an error result, not a silent success."""
    memory = FakeMemory(stored=False)
    result = await call(RememberFactTool(memory), fact="The bins go out on Tuesday")

    assert result.error is True
    assert "unavailable" in str(result.data["error"])


async def test_remember_tool_rejects_an_empty_fact() -> None:
    """Whitespace is not a fact."""
    memory = FakeMemory()
    result = await call(RememberFactTool(memory), fact="   ")

    assert result.error is True
    assert memory.remembered == []


async def test_search_tool_returns_memories() -> None:
    """The search tool returns what recall found, so the model can read it."""
    memory = FakeMemory(recalled="- Lives in Timaru\n- Prefers the kitchen lights dim")
    result = await call(SearchMemoryTool(memory), query="where does the user live")

    assert result.error is False
    assert "Timaru" in str(result.data["memories"])
    assert memory.queries == ["where does the user live"]


async def test_search_tool_says_so_when_nothing_is_found() -> None:
    """An empty result is reported as empty rather than as an error."""
    memory = FakeMemory(recalled="")
    result = await call(SearchMemoryTool(memory), query="anything about a boat")

    assert result.error is False
    assert str(result.data["memories"]) == ""


def test_build_memory_tools_follows_recall_setting() -> None:
    """Remembering stays available even when recall is disabled."""
    both = build_memory_tools(FakeMemory())
    assert [tool.name for tool in both] == [
        TOOL_NAME_REMEMBER,
        TOOL_NAME_RECALL_MEMORY,
    ]

    remember_only = build_memory_tools(FakeMemory(recall_enabled=False))
    assert [tool.name for tool in remember_only] == [TOOL_NAME_REMEMBER]


def test_tools_declare_safe_annotations() -> None:
    """Recall is read-only; neither tool is destructive or reaches outside HA."""
    remember = RememberFactTool(FakeMemory())
    search = SearchMemoryTool(FakeMemory())

    assert remember.annotations.read_only is False
    assert search.annotations.read_only is True
    for tool in (remember, search):
        assert tool.annotations.destructive is False
        assert tool.annotations.open_world is False
