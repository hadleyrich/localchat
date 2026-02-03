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
CONF_HINDSIGHT_USER_MEMORIES_PROMPT = "hindsight_user_memories_prompt"
CONF_HINDSIGHT_AGENT_TRAITS_PROMPT = "hindsight_agent_traits_prompt"

# Default summarization prompt for user memories/preferences
DEFAULT_HINDSIGHT_USER_MEMORIES_PROMPT = """Analyze the following conversation and extract:
1. Any facts mentioned about users, preferences, or context
2. Any patterns in how the user communicates or what they prefer
3. Any important information that should be remembered for future conversations

Only include information that would be useful to remember long-term. Be concise.

Conversation:
{conversation_text}

Extract and format as a numbered list of facts/preferences (one per line, starting with a number):"""

# Default summarization prompt for agent personality/traits
DEFAULT_HINDSIGHT_AGENT_TRAITS_PROMPT = """Analyze the following conversation and extract observations about the assistant's personality and behavior patterns:
1. Communication style and tone used by the assistant
2. Helpful patterns or approaches the assistant took
3. Personality traits exhibited (e.g., formal, casual, humorous, technical)
4. Any consistent behaviors or preferences in how the assistant responded

Focus on extracting traits that would help the assistant maintain a consistent personality. Be concise.

Conversation:
{conversation_text}

Extract and format as a numbered list of personality traits/behaviors (one per line, starting with a number):"""

# Event for conversation completion with Hindsight integration
EVENT_CONVERSATION_FINISHED = f"{DOMAIN}_conversation_finished"

# Default mental model configurations for agent traits bank
# These define agent personality and behavior patterns
DEFAULT_TRAITS_MENTAL_MODELS = [
    {
        "name": "Assistant Personality",  # Human-readable name
        "source_query": "How should a Home Assistant voice assistant speak, behave, and present itself?",  # Query used to generate content
        "tags": ["personality", "behavior", "tone"],  # Tags for filtering/organization
    },
    {
        "name": "Humor Guidelines",
        "source_query": "How and when should humor be used by this assistant?",
        "tags": ["humor", "personality"],
    },
]

# Default mental model configurations for user preferences bank
# These remember user preferences and communication style
DEFAULT_USERPREFS_MENTAL_MODELS = [
    {
        "name": "User Preferences",
        "source_query": "What are the user's preferences and communication style?",
        "tags": ["preferences", "user"],
    },
]

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
