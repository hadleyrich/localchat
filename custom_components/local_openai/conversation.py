"""Conversation support for Local OpenAI LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from homeassistant.components import conversation
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT, MATCH_ALL
from homeassistant.helpers import llm
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALWAYS_CONTINUE_CONVERSATION,
    CONF_ALWAYS_CONTINUE_CONVERSATION_DEFAULT,
    CONF_CONTENT_INJECTION_METHOD,
    CONF_PARALLEL_TOOL_CALLS,
    CONF_SERVER_TYPE,
    DOMAIN,
    SERVER_TYPE_DEEPSEEK,
    SERVER_TYPE_GENERIC,
    SERVER_TYPE_GOOGLE_GEMINI,
    SERVER_TYPE_LLAMACPP,
    SERVER_TYPE_LOCALAI,
    SERVER_TYPE_VLLM,
)
from .entity import LocalAiEntity
from .hindsight import HindsightMemory, async_get_memory, options_from_data
from .tools.api import InternalToolApi
from .tools.memory import build_memory_tools
from .tools.stop_talking import StopTalkingTool

if TYPE_CHECKING:
    from homeassistant.core import Context

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import LocalAiConfigEntry

MEMORY_INSTRUCTIONS = (
    "The following information about the user and your own personality comes "
    "from long-term memory. Treat it as factual and use it when answering "
    "questions about the user, their preferences or their household."
)


def _extract_history(chat_log: conversation.ChatLog) -> list[dict[str, str]]:
    """
    Return the user and assistant turns worth remembering.

    Tool calls and tool results are skipped: Hindsight extracts facts from prose,
    and tool plumbing is noise that would otherwise be stored as conversation.
    """
    history: list[dict[str, str]] = []
    for content in chat_log.content:
        if content.role not in ("user", "assistant"):
            continue
        if text := (content.content or "").strip():
            history.append({"role": content.role, "content": text})
    return history


def _get_conversation_entity(
    server_type: str,
) -> type[LocalAiConversationEntity]:
    if getattr(_get_conversation_entity, "entity_map", None) is None:
        from .entities.deepseek import DeepSeekConversationEntity  # noqa: PLC0415
        from .entities.google_gemini import (  # noqa: PLC0415
            GoogleGeminiConversationEntity,
        )
        from .entities.llama_cpp import LlamaCppConversationEntity  # noqa: PLC0415
        from .entities.localai import LocalAIServerConversationEntity  # noqa: PLC0415
        from .entities.vllm import VllmConversationEntity  # noqa: PLC0415

        _get_conversation_entity.entity_map = {
            SERVER_TYPE_DEEPSEEK: DeepSeekConversationEntity,
            SERVER_TYPE_GOOGLE_GEMINI: GoogleGeminiConversationEntity,
            SERVER_TYPE_LLAMACPP: LlamaCppConversationEntity,
            SERVER_TYPE_LOCALAI: LocalAIServerConversationEntity,
            SERVER_TYPE_VLLM: VllmConversationEntity,
        }

    return _get_conversation_entity.entity_map.get(
        server_type,
        LocalAiConversationEntity,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LocalAiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    entity_cls = _get_conversation_entity(
        config_entry.data.get(CONF_SERVER_TYPE, SERVER_TYPE_GENERIC),
    )
    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type != "conversation":
            continue
        async_add_entities(
            [entity_cls(config_entry, subentry)],
            config_subentry_id=subentry_id,
        )


class LocalAiConversationEntity(LocalAiEntity, conversation.ConversationEntity):
    """Local OpenAI LLM conversation agent."""

    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: LocalAiConfigEntry, subentry: ConfigSubentry) -> None:
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
        system_prompt = await self._async_system_prompt(options, user_input.text)
        parallel_tool_calls = options.get(CONF_PARALLEL_TOOL_CALLS, True)
        always_continue_conversation = options.get(
            CONF_ALWAYS_CONTINUE_CONVERSATION, CONF_ALWAYS_CONTINUE_CONVERSATION_DEFAULT
        )

        hass_apis = [api.id for api in llm.async_get_apis(self.hass)]

        # Filter out any tool providers that no longer exist
        llm_apis = options.get(CONF_LLM_HASS_API, [])
        llm_apis = [api for api in llm_apis if api in hass_apis]

        if always_continue_conversation and not llm_apis:
            # Inject our internal tooling for `stop_talking` as an API if no other tooling providers exist
            llm_apis = InternalToolApi(
                hass=self.hass,
                name="DOMAIN",
            )

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                llm_apis,
                system_prompt,
                user_input.extra_system_prompt,
            )

            if always_continue_conversation and not isinstance(
                llm_apis, InternalToolApi
            ):
                # Append our stop_talking tool to the existing tooling if tooling APIs were configured
                chat_log.llm_api.tools.append(StopTalkingTool())

            if (memory := self._memory) is not None and chat_log.llm_api is not None:
                # Memory belongs to the agent rather than to an optional tool
                # provider: the bank is ours, so remembering and looking
                # something up must not depend on which control APIs the user
                # selected for this agent.
                chat_log.llm_api.tools.extend(build_memory_tools(memory))
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        halt_conversation = await self._async_handle_chat_log(
            chat_log,
            user_input=user_input,
            parallel_tool_calls=parallel_tool_calls,
        )

        chat_log_result = conversation.async_get_result_from_chat_log(
            user_input, chat_log
        )

        if halt_conversation:
            # If we've received our stop_talking halt signal
            chat_log_result.continue_conversation = False
        elif always_continue_conversation:
            chat_log_result.continue_conversation = True

        # Store on every completed turn, whatever the continuation flag says:
        # "always continue conversation" keeps one turn open across follow-ups,
        # and gating on it would mean an agent configured that way never
        # remembers anything. Re-storing the same conversation replaces its
        # document, and the server retains only the delta.
        self._async_store_conversation(chat_log, user_input.context)

        return chat_log_result

    @property
    def bank_id(self) -> str:
        """
        Return the Hindsight bank for this agent.

        A configured bank wins; otherwise fall back to '<entity name>-userprefs'
        so a bank created by an earlier version of this integration keeps working.
        """
        if configured := options_from_data(self.entry.data).bank_id:
            return configured

        entity_name = (
            self.entity_id.split(".")[-1] if "." in self.entity_id else self.entity_id
        )
        return f"{entity_name}-userprefs"

    @property
    def _memory(self) -> HindsightMemory | None:
        """Return the memory helper for this agent, or None when unconfigured."""
        options = options_from_data(self.entry.data)
        if not options.usable:
            return None

        return async_get_memory(
            self.hass,
            self.entry.entry_id,
            options.base_url,
            self.bank_id,
            recall_enabled=options.recall,
            mental_models_enabled=options.mental_models,
        )

    async def _async_system_prompt(
        self,
        options: dict,
        user_text: str | None,
    ) -> str | None:
        """Build the system prompt, including any memory worth injecting."""
        parts: list[str] = []

        if base_prompt := options.get(CONF_PROMPT):
            parts.append(base_prompt)

        if (memory := self._memory) and (
            block := await memory.async_memory_prompt(user_text)
        ):
            parts.append(f"{MEMORY_INSTRUCTIONS}\n\n{block}")

        # The date is injected with the user turn when a content injection method
        # is configured, so only add it to the prompt when it is not.
        if not options.get(CONF_CONTENT_INJECTION_METHOD):
            parts.append(f"The current date is: `{dt_util.now():%A %d %B, %Y}`.")

        return "\n\n".join(parts) or None

    def _async_store_conversation(
        self, chat_log: conversation.ChatLog, context: Context | None = None
    ) -> None:
        """
        Hand a finished conversation to Hindsight, off the response path.

        The speaker is recorded as a tag so a per-person mental model can read
        only that person's memories; without it every preference in a household
        is attributed to an undifferentiated "the user".
        """
        memory = self._memory
        if memory is None:
            return

        if not (history := _extract_history(chat_log)):
            return

        self.hass.async_create_task(
            memory.async_retain(
                history,
                conversation_id=chat_log.conversation_id,
                timestamp=dt_util.now(dt_util.UTC),
                agent_name=str(getattr(self.subentry, "title", "") or self.entity_id),
                user_id=getattr(context, "user_id", None),
            ),
            name=f"{DOMAIN} retain {chat_log.conversation_id}",
        )
