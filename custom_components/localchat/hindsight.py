"""Hindsight memory integration for Local Chat."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hindsight_client import Hindsight

from .const import (
    DEFAULT_MENTAL_MODELS,
    LOGGER,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


async def process_conversation_memory(
    hass: HomeAssistant,
    hindsight_base_url: str,
    bank_id: str,
    conversation_history: list[dict[str, Any]],
    conversation_id: str,
) -> None:
    """
    Process conversation and store in Hindsight.

    Passes the full conversation to Hindsight for it to extract facts itself.

    Args:
        hass: Home Assistant instance
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier
        conversation_history: List of conversation messages
        conversation_id: Unique identifier for this conversation

    """
    try:
        # Format conversation as a single text string (exclude system prompts, only include user/assistant)
        conversation_text = "\n\n".join(
            [
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                for msg in conversation_history
                if msg.get("content") and msg.get("role") in ("user", "assistant")
            ]
        )

        if not conversation_text.strip():
            LOGGER.debug("No conversation content to store")
            return

        # Create client in executor to avoid blocking the event loop on SSL setup
        def create_client() -> Hindsight:
            return Hindsight(base_url=hindsight_base_url, timeout=30.0)

        client = await hass.async_add_executor_job(create_client)

        try:
            # Store the entire conversation as a single memory item
            # Hindsight will extract facts and observations from it
            await client.aretain(
                bank_id=bank_id,
                content=conversation_text,
                document_id=conversation_id,
                metadata={
                    "conversation_id": conversation_id,
                    "message_count": str(len(conversation_history)),
                    "source": "localchat_conversation",
                },
                tags=["conversation"],
            )

            LOGGER.info(
                "Successfully stored conversation in Hindsight bank: %s",
                bank_id,
            )
        finally:
            # Close the client connection asynchronously
            await client.aclose()

    except Exception:
        LOGGER.exception("Error processing conversation memory")


async def ensure_mental_models(
    hass: HomeAssistant,
    hindsight_base_url: str,
    bank_id: str,
    mental_models: list[dict] | None = None,
) -> None:
    """
    Ensure mental models exist in the Hindsight bank.

    Creates mental models if they don't exist, with auto-refresh enabled.

    Args:
        hass: Home Assistant instance
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier
        mental_models: List of mental model definitions with 'name', 'source_query', and optional 'tags'
                      If None, uses DEFAULT_MENTAL_MODELS

    """
    try:
        # Use default mental models if not provided
        if mental_models is None:
            mental_models = DEFAULT_MENTAL_MODELS

        # Create client in executor to avoid blocking the event loop on SSL setup
        def create_client() -> Hindsight:
            return Hindsight(base_url=hindsight_base_url, timeout=30.0)

        client = await hass.async_add_executor_job(create_client)

        try:
            # Get existing mental models (bank may not exist yet, which is fine)
            try:
                existing = await client._mental_models_api.list_mental_models(
                    bank_id, tags=None
                )
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
                    # Build request object directly
                    from hindsight_client_api.models import (
                        create_mental_model_request,
                        mental_model_trigger,
                    )

                    trigger_obj = mental_model_trigger.MentalModelTrigger(
                        refresh_after_consolidation=True
                    )
                    request_obj = create_mental_model_request.CreateMentalModelRequest(
                        name=model_def["name"],
                        source_query=model_def["source_query"],
                        tags=model_def.get("tags", []),
                        max_tokens=None,
                        trigger=trigger_obj,
                    )

                    result = await client._mental_models_api.create_mental_model(
                        bank_id, request_obj
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
    hass: HomeAssistant,
    hindsight_base_url: str,
    bank_id: str,
) -> str:
    """
    Retrieve all mental model content from Hindsight bank.

    Args:
        hass: Home Assistant instance
        hindsight_base_url: Base URL for Hindsight server
        bank_id: Memory bank identifier

    Returns:
        Combined text of all mental model content, or empty string if none found

    """
    try:
        # Create client in executor to avoid blocking the event loop on SSL setup
        def create_client() -> Hindsight:
            return Hindsight(base_url=hindsight_base_url, timeout=30.0)

        client = await hass.async_add_executor_job(create_client)

        try:
            # List all mental models (bank may not exist yet)
            try:
                mental_models = await client._mental_models_api.list_mental_models(
                    bank_id, tags=None
                )
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
                    full_model = await client._mental_models_api.get_mental_model(
                        bank_id, mental_model.id
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
