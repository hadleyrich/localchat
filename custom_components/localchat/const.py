"""Constants for the Local Chat integration."""

import logging

from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "localchat"
LOGGER = logging.getLogger(__package__)

CONF_RECOMMENDED = "recommended"
CONF_BASE_URL = "base_url"
CONF_SERVER_NAME = "server_name"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_MAX_MESSAGE_HISTORY = "max_message_history"
CONF_TEMPERATURE = "temperature"
CONF_PARALLEL_TOOL_CALLS = "parallel_tool_calls"
CONF_CHAT_TEMPLATE_OPTS = "chat_template_opts"
CONF_CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"

CONF_CONTENT_INJECTION_METHOD_SYSTEM = "System"
CONF_CONTENT_INJECTION_METHOD_ASSISTANT = "Assistant"
CONF_CONTENT_INJECTION_METHOD_USER = "User"
CONF_CONTENT_INJECTION_METHOD_TOOL = "Tool Result"

CONF_CONTENT_INJECTION_METHOD = "content_injection_method"
CONF_CONTENT_INJECTION_METHODS = [
    CONF_CONTENT_INJECTION_METHOD_TOOL,
    CONF_CONTENT_INJECTION_METHOD_ASSISTANT,
    CONF_CONTENT_INJECTION_METHOD_USER,
]

# Hindsight configuration constants
CONF_HINDSIGHT_ENABLED = "hindsight_enabled"
CONF_HINDSIGHT_BASE_URL = "hindsight_base_url"
CONF_HINDSIGHT_BANK_ID = "hindsight_bank_id"
CONF_HINDSIGHT_SUMMARIZATION_PROMPT = "hindsight_summarization_prompt"

# Default summarization prompt for Hindsight
DEFAULT_HINDSIGHT_SUMMARIZATION_PROMPT = """Analyze the following conversation and extract:
1. Any facts mentioned about users, preferences, or context
2. Any patterns in how the user communicates or what they prefer
3. Any important information that should be remembered for future conversations

Only include information that would be useful to remember long-term. Be concise.

Conversation:
{conversation_text}

Extract and format as a list of facts/preferences:"""

# Event for conversation completion with Hindsight integration
EVENT_CONVERSATION_FINISHED = f"{DOMAIN}_conversation_finished"

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
