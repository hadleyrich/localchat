"""Conversation support for Local Chat."""

from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalChatConfigEntry
from .const import (
    CONF_HINDSIGHT_BANK_ID,
    CONF_HINDSIGHT_BASE_URL,
    CONF_HINDSIGHT_ENABLED,
    DOMAIN,
    EVENT_CONVERSATION_FINISHED,
)
from .entity import LocalChatEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LocalChatConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != "conversation":
            continue
        async_add_entities(
            [LocalChatConversationEntity(config_entry, subentry)],
            config_subentry_id=subentry_id,
        )


class LocalChatConversationEntity(LocalChatEntity, conversation.ConversationEntity):
    """Local Chat conversation agent."""

    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: LocalChatConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the agent."""
        super().__init__(entry, subentry)
        if self.subentry.data.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Process the user input and call the API."""
        options = self.subentry.data
        system_prompt = options.get(CONF_PROMPT)

        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log, user_input=user_input)

        result = conversation.async_get_result_from_chat_log(user_input, chat_log)

        # Fire event for conversation completion with Hindsight integration
        # Only fire when conversation is complete (not continuing)
        # Check if Hindsight is enabled in the parent config entry
        parent_options = self.entry.data
        hindsight_enabled = parent_options.get(CONF_HINDSIGHT_ENABLED, False)

        if hindsight_enabled and not result.continue_conversation:
            # Extract conversation history from chat_log
            conversation_history = self._extract_conversation_history(chat_log)

            # Fire event asynchronously (non-blocking)
            self.hass.bus.async_fire(
                EVENT_CONVERSATION_FINISHED,
                {
                    "conversation_id": chat_log.conversation_id,
                    "entity_id": self.entity_id,
                    "config_entry_id": self.entry.entry_id,
                    "hindsight_base_url": parent_options.get(CONF_HINDSIGHT_BASE_URL),
                    "hindsight_bank_id": parent_options.get(CONF_HINDSIGHT_BANK_ID),
                    "conversation_history": conversation_history,
                },
            )

        return result

    def _extract_conversation_history(
        self, chat_log: conversation.ChatLog
    ) -> list[dict]:
        """
        Extract conversation history from chat log.

        Args:
            chat_log: The chat log to extract from

        Returns:
            List of message dictionaries with role and content

        """
        history = []
        for content in chat_log.content:
            # Skip tool results, only process text messages
            if isinstance(content, conversation.ToolResultContent):
                continue
            msg = {
                "role": content.role,
                "content": content.content or "",
            }
            history.append(msg)
        return history
