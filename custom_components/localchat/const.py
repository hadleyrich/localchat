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
        "source_query": "Summarize the user's habits, interests, priorities, lifestyle patterns, and personal preferences in clear, neutral language suitable for inclusion in an AI prompt. Describe recurring topics, likes, dislikes, routines, and contextual facts about the user. Exclude any preferences related to how an assistant should speak, format responses, manage conversation flow, ask questions, handle timing, or support text to speech. Do not include interaction rules, assistant capabilities, or response strategies.",
        "tags": ["preferences", "user"],
    },
]

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
