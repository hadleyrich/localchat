"""The Local Chat integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from openai import AsyncOpenAI, AuthenticationError, OpenAIError

from .const import (
    CONF_BASE_URL,
    CONF_HINDSIGHT_AGENT_TRAITS_PROMPT,
    CONF_HINDSIGHT_BASE_URL,
    CONF_HINDSIGHT_ENABLED,
    CONF_HINDSIGHT_USER_MEMORIES_PROMPT,
    EVENT_CONVERSATION_FINISHED,
    LOGGER,
)
from .hindsight import process_conversation_memory

if TYPE_CHECKING:
    from homeassistant.core import Event, HomeAssistant
    from homeassistant.helpers.typing import ConfigType

PLATFORMS = [Platform.AI_TASK, Platform.CONVERSATION]

type LocalChatConfigEntry = ConfigEntry[AsyncOpenAI]


async def async_setup_entry(hass: HomeAssistant, entry: LocalChatConfigEntry) -> bool:
    """Set up Local Chat from a config entry."""
    client = AsyncOpenAI(
        base_url=entry.data[CONF_BASE_URL],
        api_key=entry.data.get(CONF_API_KEY, ""),
        http_client=get_async_client(hass),
    )

    # Cache current platform data which gets added to each request (caching done by library)
    _ = await hass.async_add_executor_job(client.platform_headers)

    try:
        async for _ in client.with_options(timeout=10.0).models.list():
            break
    except AuthenticationError as err:
        LOGGER.error("Invalid API key: %s", err)
        msg = "Invalid API key"
        raise ConfigEntryError(msg) from err
    except OpenAIError as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up Hindsight event listener if enabled
    if entry.data.get(CONF_HINDSIGHT_ENABLED, False):
        hindsight_base_url = entry.data.get(CONF_HINDSIGHT_BASE_URL)
        user_memories_prompt = entry.data.get(CONF_HINDSIGHT_USER_MEMORIES_PROMPT)
        agent_traits_prompt = entry.data.get(CONF_HINDSIGHT_AGENT_TRAITS_PROMPT)

        if hindsight_base_url:
            LOGGER.info(
                "Setting up Hindsight integration with auto-generated bank names"
            )

            async def handle_conversation_finished(event: Event) -> None:
                """Handle conversation finished event."""
                # Only process events for this config entry
                if event.data.get("config_entry_id") != entry.entry_id:
                    return

                conversation_id = event.data.get("conversation_id")
                conversation_history = event.data.get("conversation_history", [])
                user_memories_bank_id = event.data.get("user_memories_bank_id")
                agent_traits_bank_id = event.data.get("agent_traits_bank_id")

                LOGGER.debug(
                    "Processing conversation %s for Hindsight storage in banks: %s, %s",
                    conversation_id,
                    user_memories_bank_id,
                    agent_traits_bank_id,
                )

                # Process user memories
                if user_memories_bank_id:
                    await process_conversation_memory(
                        hass,
                        hindsight_base_url,
                        user_memories_bank_id,
                        conversation_history,
                        conversation_id,
                        user_memories_prompt,
                    )

                # Process agent traits
                if agent_traits_bank_id:
                    await process_conversation_memory(
                        hass,
                        hindsight_base_url,
                        agent_traits_bank_id,
                        conversation_history,
                        conversation_id,
                        agent_traits_prompt,
                    )

            # Register event listener
            entry.async_on_unload(
                hass.bus.async_listen(
                    EVENT_CONVERSATION_FINISHED, handle_conversation_finished
                )
            )
        else:
            LOGGER.warning("Hindsight enabled but base URL not configured")

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: LocalChatConfigEntry
) -> None:
    """Handle update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LocalChatConfigEntry) -> bool:
    """Unload Local Chat."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up is called when Home Assistant is loading our component."""
    return True
