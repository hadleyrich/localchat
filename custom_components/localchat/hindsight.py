"""Hindsight memory integration for Local Chat."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hindsight_client import Hindsight

from .const import (
    DEFAULT_HINDSIGHT_USER_MEMORIES_PROMPT,
    DEFAULT_TRAITS_MENTAL_MODELS,
    DEFAULT_USERPREFS_MENTAL_MODELS,
    LOGGER,
)

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

    # Debug logging to show the prompt being used
    LOGGER.debug("Hindsight summarization prompt: %s", formatted_prompt)

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
                "task_name": "Summarize conversation",
                "instructions": formatted_prompt,
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
                # Using regex to properly handle multi-digit numbers
                cleaned_line = re.sub(r"^[\d\.\-\*•\s]+", "", line).strip()
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
        prompt = summarization_prompt or DEFAULT_HINDSIGHT_USER_MEMORIES_PROMPT

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
                        "message_count": str(len(conversation_history)),
                        "source": "localchat_conversation",
                    },
                }
                for fact in facts
            ]

            await client.aretain_batch(
                bank_id=bank_id,
                items=batch_items,
                document_id=conversation_id,
                retain_async=True,  # Process asynchronously in background for better performance
                # Note: This returns before facts are fully stored, but errors are handled by Hindsight server
            )

            LOGGER.info(
                "Successfully stored %d facts from conversation in Hindsight bank: %s",
                len(facts),
                bank_id,
            )
        finally:
            # Close the client connection asynchronously
            await client.aclose()

    except Exception:
        LOGGER.exception("Error processing conversation memory")


async def ensure_mental_models(
    hindsight_base_url: str,
    bank_id: str,
    mental_models: list[dict] | None = None,
) -> None:
    """
    Ensure mental models exist in the Hindsight bank.

    Creates mental models if they don't exist, with auto-refresh enabled.

    Args:
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier
        mental_models: List of mental model definitions with 'name', 'source_query', and optional 'tags'
                      If None, determines appropriate models based on bank_id suffix

    """
    try:
        # Determine which mental models to use based on bank_id
        if mental_models is None:
            if bank_id.endswith("-traits"):
                mental_models = DEFAULT_TRAITS_MENTAL_MODELS
            elif bank_id.endswith("-userprefs"):
                mental_models = DEFAULT_USERPREFS_MENTAL_MODELS
            else:
                LOGGER.warning(
                    "Cannot determine mental models for bank %s - expected bank_id to end with '-traits' or '-userprefs'",
                    bank_id,
                )
                return

        client = Hindsight(base_url=hindsight_base_url, timeout=30.0)

        try:
            # Get existing mental models (bank may not exist yet, which is fine)
            try:
                existing = await client.alist_mental_models(bank_id=bank_id)
                existing_names = {m.name for m in existing.items}
            except Exception as list_err:
                LOGGER.debug(
                    "Bank %s may not exist yet, will create models: %s",
                    bank_id,
                    list_err,
                )
                existing_names = set()

            # Create missing mental models
            for model_def in mental_models:
                if model_def["name"] not in existing_names:
                    LOGGER.info(
                        "Creating mental model '%s' in bank %s",
                        model_def["name"],
                        bank_id,
                    )
                    result = await client.acreate_mental_model(
                        bank_id=bank_id,
                        name=model_def["name"],
                        source_query=model_def["source_query"],
                        tags=model_def.get("tags", []),
                        trigger={"refresh_after_consolidation": True},
                    )
                    LOGGER.debug(
                        "Mental model creation operation ID: %s", result.operation_id
                    )
                else:
                    LOGGER.debug(
                        "Mental model '%s' already exists in bank %s",
                        model_def["name"],
                        bank_id,
                    )
        finally:
            await client.aclose()

    except Exception:
        LOGGER.exception("Error ensuring mental models")


async def retrieve_mental_models(
    hindsight_base_url: str,
    bank_id: str,
) -> str:
    """
    Retrieve all mental model content from Hindsight bank.

    Args:
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier

    Returns:
        Combined text of all mental model content, or empty string if none found

    """
    try:
        client = Hindsight(base_url=hindsight_base_url, timeout=30.0)

        try:
            # List all mental models (bank may not exist yet)
            try:
                mental_models = await client.alist_mental_models(bank_id=bank_id)
            except Exception as list_err:
                LOGGER.debug(
                    "Could not list mental models from bank %s (may not exist yet): %s",
                    bank_id,
                    list_err,
                )
                return ""

            if not mental_models.items:
                LOGGER.debug("No mental models found in bank %s", bank_id)
                return ""

            # Retrieve content from each mental model
            contents = []
            for mental_model in mental_models.items:
                try:
                    # Get full mental model details including content
                    full_model = await client.aget_mental_model(
                        bank_id=bank_id,
                        mental_model_id=mental_model.id,
                    )
                    # Mental models may not have content yet if still generating
                    if full_model.content:
                        contents.append(f"## {full_model.name}\n{full_model.content}")
                        LOGGER.debug(
                            "Retrieved mental model '%s' content (%d chars)",
                            full_model.name,
                            len(full_model.content),
                        )
                    else:
                        LOGGER.debug(
                            "Mental model '%s' has no content yet (still generating)",
                            full_model.name,
                        )
                except Exception as get_err:
                    LOGGER.warning(
                        "Could not retrieve mental model %s: %s",
                        mental_model.id,
                        get_err,
                    )

            combined = "\n\n".join(contents)
            if combined:
                LOGGER.debug(
                    "Retrieved %d mental models from bank %s (%d total chars)",
                    len(contents),
                    bank_id,
                    len(combined),
                )
            return combined

        finally:
            await client.aclose()

    except Exception:
        LOGGER.exception("Error retrieving mental models")
        return ""


async def retrieve_mental_models_from_multiple_banks(
    hindsight_base_url: str,
    bank_ids: list[str],
) -> str:
    """
    Retrieve all mental model content from multiple Hindsight banks.

    Args:
        hindsight_base_url: Base URL for Hindsight server
        bank_ids: List of memory bank identifiers

    Returns:
        Combined text of all mental model content from all banks, or empty string if none found

    """
    all_contents = []

    for bank_id in bank_ids:
        content = await retrieve_mental_models(hindsight_base_url, bank_id)
        if content:
            all_contents.append(content)

    combined = "\n\n".join(all_contents)
    if combined:
        LOGGER.debug(
            "Retrieved mental models from %d banks (%d total chars)",
            len(all_contents),
            len(combined),
        )
    return combined
