"""Hindsight memory integration for Local Chat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hindsight_client import Hindsight

from .const import LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def summarize_conversation(
    hass: HomeAssistant,
    conversation_history: list[dict[str, Any]],
    ai_task_entity_id: str | None = None,
) -> str | None:
    """
    Summarize conversation history to extract facts and preferences.

    Args:
        hass: Home Assistant instance
        conversation_history: List of conversation messages
        ai_task_entity_id: Optional AI Task entity to use for summarization

    Returns:
        Summary text containing extracted facts and preferences, or None if failed

    """
    # Format conversation for summarization
    conversation_text = "\n\n".join(
        [
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in conversation_history
            if msg.get("content")
        ]
    )

    if not conversation_text.strip():
        LOGGER.debug("No conversation content to summarize")
        return None

    # Create summarization prompt
    summarization_prompt = f"""Analyze the following conversation and extract:
1. Any facts mentioned about users, preferences, or context
2. Any patterns in how the user communicates or what they prefer
3. Any important information that should be remembered for future conversations

Only include information that would be useful to remember long-term. Be concise.

Conversation:
{conversation_text}

Extract and format as a list of facts/preferences:"""

    try:
        # If specific AI Task entity provided, use it, otherwise find one
        if not ai_task_entity_id:
            # Find an available AI Task entity
            states = hass.states.async_all("ai_task")
            if not states:
                LOGGER.warning("No AI Task entity found for summarization")
                return None
            ai_task_entity_id = states[0].entity_id
            LOGGER.debug("Using AI Task entity: %s", ai_task_entity_id)

        # Call the AI Task service to generate summary
        result = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": ai_task_entity_id,
                "task": summarization_prompt,
            },
            blocking=True,
            return_response=True,
        )

        if result and isinstance(result, dict):
            summary = result.get("data", "")
            LOGGER.debug("Generated conversation summary: %s", summary)
            return summary
        return None  # noqa: TRY300

    except Exception:
        LOGGER.exception("Error summarizing conversation")
        return None


async def process_conversation_memory(
    hass: HomeAssistant,
    hindsight_base_url: str,
    bank_id: str,
    conversation_history: list[dict[str, Any]],
    conversation_id: str,
    ai_task_entity_id: str | None = None,
) -> None:
    """
    Process conversation and store memories in Hindsight.

    Args:
        hass: Home Assistant instance
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier
        conversation_history: List of conversation messages
        conversation_id: Unique identifier for this conversation
        ai_task_entity_id: Optional AI Task entity to use for summarization

    """
    try:
        # Summarize the conversation
        summary = await summarize_conversation(
            hass, conversation_history, ai_task_entity_id
        )

        if not summary:
            LOGGER.debug("No summary generated, skipping Hindsight storage")
            return

        # Use official Hindsight client
        client = Hindsight(base_url=hindsight_base_url, timeout=30.0)

        try:
            # Store in Hindsight with metadata
            await client.aretain(
                bank_id=bank_id,
                content=summary,
                metadata={
                    "conversation_id": conversation_id,
                    "message_count": len(conversation_history),
                    "source": "localchat_conversation",
                },
            )

            LOGGER.info(
                "Successfully stored conversation memory in Hindsight bank: %s", bank_id
            )
        finally:
            # Close the client connection
            client.close()

    except Exception:
        LOGGER.exception("Error processing conversation memory")

