"""
Tools that let the agent use long-term memory deliberately.

Injected memory is passive: everything the agent might need is pushed into the
prompt on every turn, whether or not the turn needs it. These two tools invert
that for the cases where deliberate use is better -- the user says "remember
that ..." and nothing has captured it yet, or the user asks something specific
that injected summaries are too coarse to answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import probatio
from homeassistant.helpers import llm

from custom_components.local_openai.const import (
    DOMAIN,
    HOUSE_MANUAL_PAGE,
    LOGGER,
    TOOL_NAME_HOUSE_MANUAL,
    TOOL_NAME_RECALL_MEMORY,
    TOOL_NAME_REMEMBER,
)

if TYPE_CHECKING:
    from typing import Protocol

    from homeassistant.core import HomeAssistant

    class MemoryBackend(Protocol):
        """The slice of HindsightMemory these tools depend on."""

        recall_enabled: bool

        async def async_remember(self, text: str, user_id: str | None = None) -> bool:
            """Store one fact, returning whether it was stored."""
            ...

        async def async_recall(self, query: str) -> str:
            """Return memories relevant to a query, formatted for a prompt."""
            ...

        async def async_search_house_manual(self, query: str) -> str:
            """Return house manual passages relevant to a query."""
            ...


REMEMBER_DESCRIPTION = (
    "Store a durable fact about the user or the household: a preference, routine, "
    "relationship, device name, or standing arrangement. Call this when the user asks "
    "you to remember something, or states a lasting fact about themselves or the home. "
    "Never call it for current sensor readings, device states, occupancy, weather, "
    "one-off requests, greetings, or anything that will not still be true next month."
)

RECALL_DESCRIPTION = (
    "Search long-term memory about this household for something your context does not "
    "already answer: past conversations, specific preferences, routines, relationships "
    "or details about the home. Prefer this over guessing when the user refers to "
    "something you do not have in front of you."
)


class RememberFactTool(llm.Tool):
    """Store one deliberate fact, separate from the conversation transcript."""

    integration = DOMAIN
    name = TOOL_NAME_REMEMBER
    description = REMEMBER_DESCRIPTION
    annotations = llm.ToolAnnotations(
        read_only=False, destructive=False, idempotent=False, open_world=False
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                "fact",
                description=(
                    "The fact to remember, written as one self-contained sentence that "
                    "makes sense without the conversation, e.g. 'The bins go out on "
                    "Tuesday nights'. Do not include the user's exact words if a clearer "
                    "statement is possible."
                ),
            ): str,
        }
    )

    def __init__(self, memory: MemoryBackend) -> None:
        """Initialize the tool against one bank."""
        self._memory = memory

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Retain one fact."""
        data = self.parameters(tool_input.tool_args)
        fact = " ".join(str(data["fact"]).split())
        if not fact:
            return llm.ToolResult(data={"error": "Nothing to remember"}, error=True)

        context = llm_context.context if llm_context.context else None
        stored = await self._memory.async_remember(
            fact, user_id=getattr(context, "user_id", None)
        )
        LOGGER.debug("remember tool stored=%s fact=%r", stored, fact[:80])
        if not stored:
            return llm.ToolResult(
                data={"error": "Memory is unavailable, nothing was stored"}, error=True
            )
        return llm.ToolResult(data={"stored": True})


class SearchMemoryTool(llm.Tool):
    """Look something up in long-term memory on demand."""

    integration = DOMAIN
    name = TOOL_NAME_RECALL_MEMORY
    description = RECALL_DESCRIPTION
    annotations = llm.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                "query",
                description=(
                    "What to look for, phrased as a short search query, e.g. "
                    "'when do the bins go out' or 'what does the user call the lounge lamp'."
                ),
            ): str,
        }
    )

    def __init__(self, memory: MemoryBackend) -> None:
        """Initialize the tool against one bank."""
        self._memory = memory

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Recall memories relevant to a query."""
        data = self.parameters(tool_input.tool_args)
        query = str(data["query"]).strip()
        if not query:
            return llm.ToolResult(data={"error": "No query"}, error=True)

        found = await self._memory.async_recall(query)
        if not found:
            return llm.ToolResult(
                data={"memories": "", "note": "Nothing relevant was found"}
            )
        return llm.ToolResult(data={"memories": found})


class SearchHouseManualTool(llm.Tool):
    """Consult the long-form house manual the bank maintains about itself."""

    integration = DOMAIN
    name = TOOL_NAME_HOUSE_MANUAL
    description = (
        "Consult the house manual: a document kept about this home covering rooms, "
        "devices and what they are called, where things live, the weekly rhythm and "
        "known quirks. Use it for questions about the home itself that the short "
        "summaries do not answer."
    )
    annotations = llm.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    parameters = probatio.Schema(
        {
            probatio.Required(
                "query",
                description="What to look up in the manual, e.g. 'which switch is the porch light'.",
            ): str,
        }
    )

    def __init__(self, memory: MemoryBackend) -> None:
        """Initialize the tool against one bank."""
        self._memory = memory

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Search the house manual."""
        data = self.parameters(tool_input.tool_args)
        query = str(data["query"]).strip()
        if not query:
            return llm.ToolResult(data={"error": "No query"}, error=True)

        found = await self._memory.async_search_house_manual(query)
        if not found:
            return llm.ToolResult(
                data={
                    "manual": "",
                    "note": f"No matching section in the {HOUSE_MANUAL_PAGE}",
                }
            )
        return llm.ToolResult(data={"manual": found})


def build_memory_tools(memory: MemoryBackend) -> list[llm.Tool]:
    """Return the memory tools that suit this bank's configuration."""
    tools: list[llm.Tool] = [RememberFactTool(memory)]
    if memory.recall_enabled:
        tools.append(SearchMemoryTool(memory))
        tools.append(SearchHouseManualTool(memory))
    return tools
