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

# Event for conversation completion with Hindsight integration
EVENT_CONVERSATION_FINISHED = f"{DOMAIN}_conversation_finished"

# Default mental model configurations - all stored in single userprefs bank
# These define agent personality and remember user preferences
DEFAULT_MENTAL_MODELS = [
    {
        "name": "Agent Personality",  # Human-readable name
        "source_query": "Summarize the AI agent's personality and behaviour in a way that can be directly used as instructions in a prompt. Describe tone, style, humour, problem-solving approach, decision-making tendencies, and interaction style. Write as if giving a new AI instance guidance on how this agent should speak, think, and respond to users, highlighting notable personality traits and recurring patterns in behaviour.",  # Query used to generate content
        "tags": ["personality", "behavior", "tone"],  # Tags for filtering/organization
    },
    {
        "name": "User Information",
        "source_query": "Summarize the user’s preferences, habits, interests, communication style, priorities, and relevant context in language suitable for directly instructing an AI. Include patterns in behaviour, recurring topics, preferred ways of interacting, and any constraints or dislikes. Write as guidance for an AI on how to adapt responses to align with the user’s personality, needs, and preferences.",
        "tags": ["preferences", "user"],
    },
]

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
