"""Hindsight memory integration for Local Chat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hindsight_client import Hindsight

from .const import DEFAULT_HINDSIGHT_SUMMARIZATION_PROMPT, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def summarize_conversation(
    hass: HomeAssistant,
    conversation_history: list[dict[str, Any]],
    summarization_prompt: str,
    ai_task_entity_id: str | None = None,
) -> list[str] | None:
    """
    Summarize conversation history to extract facts and preferences.

    Args:
        hass: Home Assistant instance
        conversation_history: List of conversation messages
        summarization_prompt: Prompt template for summarization (with {conversation_text} placeholder)
        ai_task_entity_id: Optional AI Task entity to use for summarization

    Returns:
        List of extracted facts/preferences, or None if failed

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

    # Create summarization prompt using template
    formatted_prompt = summarization_prompt.format(conversation_text=conversation_text)

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
                "task": formatted_prompt,
            },
            blocking=True,
            return_response=True,
        )

        if result and isinstance(result, dict):
            summary = result.get("data", "")
            LOGGER.debug("Generated conversation summary: %s", summary)

            # Parse the summary to extract individual facts
            # Expected format: numbered list (1. fact, 2. fact, etc.) or bullet points
            facts = []
            for raw_line in summary.split("\n"):
                line = raw_line.strip()
                if not line:
                    continue
                # Remove numbering (1. 2. etc.), bullets (- * •), and leading/trailing whitespace
                cleaned_line = line.lstrip("0123456789.-*• ").strip()
                if cleaned_line:
                    facts.append(cleaned_line)

            return facts if facts else None
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
    summarization_prompt: str | None = None,
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
        summarization_prompt: Optional custom prompt template for summarization
        ai_task_entity_id: Optional AI Task entity to use for summarization

    """
    try:
        # Use default prompt if not provided
        prompt = summarization_prompt or DEFAULT_HINDSIGHT_SUMMARIZATION_PROMPT

        # Summarize the conversation to get list of facts
        facts = await summarize_conversation(
            hass, conversation_history, prompt, ai_task_entity_id
        )

        if not facts:
            LOGGER.debug("No facts extracted, skipping Hindsight storage")
            return

        # Use official Hindsight client
        client = Hindsight(base_url=hindsight_base_url, timeout=30.0)

        try:
            # Store each fact as a separate item in Hindsight batch
            batch_items = [
                {
                    "content": fact,
                    "metadata": {
                        "conversation_id": conversation_id,
                        "message_count": len(conversation_history),
                        "source": "localchat_conversation",
                    },
                }
                for fact in facts
            ]

            await client.aretain_batch(
                bank_id=bank_id,
                items=batch_items,
                document_id=conversation_id,
                retain_async=True,  # Process asynchronously for better performance
            )

            LOGGER.info(
                "Successfully stored %d facts from conversation in Hindsight bank: %s",
                len(facts),
                bank_id,
            )
        finally:
            # Close the client connection
            client.close()

    except Exception:
        LOGGER.exception("Error processing conversation memory")


