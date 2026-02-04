"""Conversation support for Local Chat."""

from datetime import datetime
from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LocalChatConfigEntry
from .const import (
    CONF_HINDSIGHT_BASE_URL,
    CONF_HINDSIGHT_ENABLED,
    DOMAIN,
    EVENT_CONVERSATION_FINISHED,
    LOGGER,
)
from .entity import LocalChatEntity
from .hindsight import retrieve_mental_models


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
        # Track how many messages have been sent to Hindsight per conversation_id
        self._sent_message_counts: dict[str, int] = {}

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
        LOGGER.debug(f"System prompt: {system_prompt}")

        # Retrieve and inject mental models if Hindsight is enabled
        parent_options = self.entry.data
        hindsight_enabled = parent_options.get(CONF_HINDSIGHT_ENABLED, False)

        if hindsight_enabled:
            hindsight_base_url = parent_options.get(CONF_HINDSIGHT_BASE_URL)
            if hindsight_base_url:
                # Generate bank ID from entity name
                entity_name = (
                    self.entity_id.split(".")[-1]
                    if "." in self.entity_id
                    else self.entity_id
                )
                bank_id = f"{entity_name}-userprefs"

                # Retrieve mental model content from bank
                mental_model_content = await retrieve_mental_models(
                    self.hass,
                    hindsight_base_url,
                    bank_id,
                )

                # Inject mental models into system prompt if content exists
                if mental_model_content:
                    mental_models_section = (
                        f"\n\nIMPORTANT: The following information about the user and your personality has been provided to you. "
                        f"You MUST use this information when answering questions about the user, their preferences, or their household. "
                        f"This is factual information you have access to.\n\n"
                        f"{mental_model_content}"
                    )
                    system_prompt = (system_prompt or "") + mental_models_section
                    LOGGER.debug(
                        f"Injected mental models into system prompt for entity {self.entity_id}."
                    )

                dt = datetime.now()
                date_str = dt.strftime("%A %d %B, %Y")

                system_prompt = (
                    (system_prompt or "")
                    + "\n\n"
                    + f"The current date is: `{date_str}`."
                )

                LOGGER.debug(f"Update system prompt: {system_prompt}")

        # Add current date to system prompt even if Hindsight is disabled
        if not hindsight_enabled:
            dt = datetime.now()
            date_str = dt.strftime("%A %d %B, %Y")
            system_prompt = (
                (system_prompt or "") + "\n\n" + f"The current date is: `{date_str}`."
            )

        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        LOGGER.debug(
            f"Final system prompt before async_provide_llm_data: {system_prompt}"
        )

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        # Log chat_log content to verify system prompt was added
        LOGGER.debug(f"Chat log content count: {len(chat_log.content)}")
        for i, content in enumerate(chat_log.content):
            content_preview = getattr(content, "content", "N/A")
            if isinstance(content_preview, str) and len(content_preview) > 200:
                content_preview = content_preview[:200] + "..."
            LOGGER.debug(
                f"Chat log content[{i}]: role={getattr(content, 'role', 'N/A')}, type={type(content).__name__}, content={content_preview}"
            )

        await self._async_handle_chat_log(chat_log, user_input=user_input)

        result = conversation.async_get_result_from_chat_log(user_input, chat_log)

        # Fire event for conversation completion with Hindsight integration
        # Only fire when conversation is complete (not continuing)
        # Check if Hindsight is enabled in the parent config entry
        parent_options = self.entry.data
        hindsight_enabled = parent_options.get(CONF_HINDSIGHT_ENABLED, False)

        if hindsight_enabled and not result.continue_conversation:
            # Extract only NEW conversation history from chat_log
            # that hasn't been sent to Hindsight yet
            conversation_history = self._extract_conversation_history(
                chat_log, chat_log.conversation_id
            )

            # Only send if there are new messages
            if conversation_history:
                # Generate bank name from entity_id
                # Extract the entity name (e.g., "llamacpp" from "conversation.llamacpp")
                entity_name = (
                    self.entity_id.split(".")[-1]
                    if "." in self.entity_id
                    else self.entity_id
                )
                bank_id = f"{entity_name}-userprefs"

                # Fire event asynchronously (non-blocking)
                self.hass.bus.async_fire(
                    EVENT_CONVERSATION_FINISHED,
                    {
                        "conversation_id": chat_log.conversation_id,
                        "entity_id": self.entity_id,
                        "config_entry_id": self.entry.entry_id,
                        "hindsight_base_url": parent_options.get(CONF_HINDSIGHT_BASE_URL),
                        "bank_id": bank_id,
                        "conversation_history": conversation_history,
                    },
                )

            # Clean up tracking for this conversation since it's complete
            # (continue_conversation=False means this conversation is done)
            if chat_log.conversation_id in self._sent_message_counts:
                del self._sent_message_counts[chat_log.conversation_id]

        return result

    def _extract_conversation_history(
        self, chat_log: conversation.ChatLog, conversation_id: str | None
    ) -> list[dict]:
        """
        Extract NEW conversation history from chat log.

        Only extracts messages that haven't been sent to Hindsight yet,
        based on tracking the message count per conversation_id.

        Args:
            chat_log: The chat log to extract from
            conversation_id: The conversation identifier for tracking

        Returns:
            List of NEW message dictionaries with role and content

        """
        # Get all current messages (filtering out tool results)
        all_messages = []
        for content in chat_log.content:
            # Skip tool results, only process text messages
            if isinstance(content, conversation.ToolResultContent):
                continue
            msg = {
                "role": content.role,
                "content": content.content or "",
            }
            all_messages.append(msg)

        # If no conversation_id, return all messages (shouldn't happen but be safe)
        if not conversation_id:
            return all_messages

        # Get the number of messages already sent for this conversation
        already_sent_count = self._sent_message_counts.get(conversation_id, 0)

        # Extract only new messages (those after already_sent_count)
        new_messages = all_messages[already_sent_count:]

        # Update the tracking count to include these new messages
        self._sent_message_counts[conversation_id] = len(all_messages)

        return new_messages
