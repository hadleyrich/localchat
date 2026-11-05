"""Constants for the Local OpenAI LLM integration."""

import logging

from homeassistant.components import ai_task
from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "local_openai"
LOGGER = logging.getLogger(__package__)

PLACEHOLDER_API_KEY = "local-openai"

CONF_RECOMMENDED = "recommended"
CONF_BASE_URL = "base_url"
CONF_SERVER_NAME = "server_name"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_MAX_MESSAGE_HISTORY = "max_message_history"
CONF_TEMPERATURE = "temperature"
CONF_PARALLEL_TOOL_CALLS = "parallel_tool_calls"
CONF_CHAT_TEMPLATE_OPTS = "chat_template_opts"
CONF_CHAT_TEMPLATE_KWARGS = "chat_template_kwargs"
CONF_REQUEST_BODY_OPTS = "request_body_opts"
CONF_REQUEST_BODY_PARAMETERS = "request_body_parameters"
CONF_PASS_SESSION_ID = "pass_session_id"  # noqa: S105
CONF_SERVER_OPTIONS = "server_options"
CONF_SERVER_TYPE = "server_type"
CONF_GENERIC_CONFIG = "generic_config"
CONF_LLAMACPP_CONFIG = "llamacpp_config"
CONF_LLAMACPP_ENABLE_THINKING = "llamacpp_enable_thinking"
CONF_LLAMACPP_THINKING_MODE = "llamacpp_thinking_mode"
CONF_LLAMACPP_THINKING_MODE_ALWAYS = "always"
CONF_LLAMACPP_THINKING_MODE_FIRST_LOOP = "first_loop"
CONF_LLAMACPP_INCLUDE_PRIOR_THINKING = "llamacpp_include_prior_thinking"
CONF_LLAMACPP_ID_SLOT = "llamacpp_id_slot"
CONF_LLAMACPP_TOP_P = "llamacpp_top_p"
CONF_LLAMACPP_TOP_K = "llamacpp_top_k"
CONF_LLAMACPP_MIN_P = "llamacpp_min_p"
CONF_LLAMACPP_REPEAT_PENALTY = "llamacpp_repeat_penalty"
CONF_LLAMACPP_PRESENCE_PENALTY = "llamacpp_presence_penalty"
CONF_LLAMACPP_USE_LOADED_MODEL = "llamacpp_use_loaded_model"
CONF_VLLM_CONFIG = "vllm_config"
CONF_VLLM_THINKING_TOKEN_BUDGET = "vllm_thinking_token_budget"  # noqa: S105
CONF_VLLM_THINKING_TOKEN_BUDGET_DEFAULT = 1024
CONF_VLLM_THINKING_MODE = "vllm_thinking_mode"
CONF_VLLM_THINKING_MODE_ALWAYS = "always"
CONF_VLLM_THINKING_MODE_FIRST_LOOP = "first_loop"
CONF_DEEPSEEK_CONFIG = "deepseek_config"
CONF_DEEPSEEK_REASONING_EFFORT = "deepseek_reasoning_effort"
CONF_DEEPSEEK_REASONING_EFFORT_HIGH = "high"
CONF_DEEPSEEK_REASONING_EFFORT_MAX = "max"
CONF_DEEPSEEK_REASONING_EFFORT_DEFAULT = CONF_DEEPSEEK_REASONING_EFFORT_HIGH
CONF_DEEPSEEK_THINKING_MODE = "deepseek_thinking_mode"
CONF_DEEPSEEK_THINKING_MODE_ALWAYS = "always"
CONF_DEEPSEEK_THINKING_MODE_FIRST_LOOP = "first_loop"
CONF_LOCALAI_CONFIG = "localai_config"
CONF_GOOGLE_GEMINI_CONFIG = "google_gemini_config"

SERVER_TYPE_GENERIC = "generic"
SERVER_TYPE_LLAMACPP = "llama_cpp"
SERVER_TYPE_VLLM = "vllm"
SERVER_TYPE_DEEPSEEK = "deepseek"
SERVER_TYPE_LOCALAI = "localai"
SERVER_TYPE_GOOGLE_GEMINI = "google_gemini"


SERVER_TYPE_OPTIONS = {
    SERVER_TYPE_GENERIC: "Generic OpenAI-Compatible",
    SERVER_TYPE_LLAMACPP: "llama.cpp",
    SERVER_TYPE_VLLM: "vLLM",
    SERVER_TYPE_DEEPSEEK: "DeepSeek Cloud",
    SERVER_TYPE_LOCALAI: "LocalAI",
    SERVER_TYPE_GOOGLE_GEMINI: "Google (Gemini)",
}

# Server types that may serve decision models through the TypeSafe-compatible /v1/systemone API
DECISION_SERVER_TYPES = (SERVER_TYPE_GENERIC, SERVER_TYPE_LLAMACPP)

CONF_ALWAYS_CONTINUE_CONVERSATION = "always_continue_conversation"
CONF_ALWAYS_CONTINUE_CONVERSATION_DEFAULT = False

TOOL_NAME_STOP_TALKING = "stop_talking"
TOOL_NAME_REMEMBER = "remember_fact"
TOOL_NAME_RECALL_MEMORY = "search_memory"
TOOL_NAME_HOUSE_MANUAL = "search_house_manual"

CONF_AI_TASK_SUPPORTED_ATTRIBUTES = "supported_attributes"
CONF_AI_TASK_SUPPORTED_ATTRIBUTE_OPTIONS = {
    "generate_data": ai_task.AITaskEntityFeature.GENERATE_DATA
    | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS,
    "generate_image": ai_task.AITaskEntityFeature.GENERATE_IMAGE
    | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS,
}

CONF_AI_TASK_TOOLS_SECTION = "tooling"

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

CONF_CUSTOM_HEADERS = "custom_headers"
CONF_SERVER_HEADERS = "server_headers"
CONF_WEAVIATE_OPTIONS = "weaviate_options"
CONF_WEAVIATE_HOST = "weaviate_host"
CONF_WEAVIATE_API_KEY = "weaviate_api_key"
CONF_WEAVIATE_CLASS_NAME = "weaviate_class_name"
CONF_WEAVIATE_MAX_RESULTS = "weaviate_max_results"
CONF_WEAVIATE_THRESHOLD = "weaviate_threshold"
CONF_WEAVIATE_HYBRID_SEARCH_ALPHA = "weaviate_hybrid_search_alpha"

CONF_WEAVIATE_DEFAULT_CLASS_NAME = "Homeassistant"
CONF_WEAVIATE_DEFAULT_THRESHOLD = 0.9
CONF_WEAVIATE_DEFAULT_MAX_RESULTS = 2
CONF_WEAVIATE_DEFAULT_HYBRID_SEARCH_ALPHA = 0.5
CONF_WEAVIATE_MAX_RESULTS_MAX = 10

CONF_HINDSIGHT_OPTIONS = "hindsight_options"
CONF_HINDSIGHT_ENABLED = "hindsight_enabled"
CONF_HINDSIGHT_BASE_URL = "hindsight_base_url"
CONF_HINDSIGHT_BANK_ID = "hindsight_bank_id"
CONF_HINDSIGHT_RECALL = "hindsight_recall"
CONF_HINDSIGHT_MENTAL_MODELS = "hindsight_mental_models"

# Recall runs per utterance, so keep it small: Assist turns are latency sensitive
DEFAULT_RECALL_MAX_TOKENS = 600
DEFAULT_RECALL_BUDGET = "low"
# Mental models only change when Hindsight consolidates, so a cached copy is good
# enough for voice turns instead of an HTTP round trip per utterance
DEFAULT_MENTAL_MODEL_TTL_SECONDS = 900

# Stored in the agent's bank on first use. Hindsight refreshes them after
# consolidation, so they follow the conversation without per-turn work.
#
# Mental-model ``tags`` are not labels: they select which memories the model may
# read. A model scoped to a tag no document carries is starved forever, and it
# fails silently -- the refresh succeeds, ``last_refreshed_at`` advances, and the
# content stays empty. Retains are tagged with RETAIN_TAGS, so the models are
# scoped to that same constant rather than to their own descriptive words.
RETAIN_TAGS = ("conversation",)

# Prefix for the tag that records who was speaking. Retains carry it alongside
# RETAIN_TAGS, so a model can be scoped to one person without losing the shared
# view: a household is not one "user".
USER_TAG_PREFIX = "user:"

# The knowledge page is the long tail: a document the bank rewrites as it learns,
# read only when the agent asks for it. The mental models below are short blocks
# injected on every turn; this is the house manual, so it gets a larger budget.
HOUSE_MANUAL_PAGE = "House Manual"
HOUSE_MANUAL_MAX_TOKENS = 1200
HOUSE_MANUAL_QUERY = (
    "Describe this home the way a new butler would need it on their first morning: "
    "the rooms and what each is used for, the devices and what the household calls "
    "them, where everyday things live, the weekly rhythm, and any quirks or standing "
    "arrangements. Write a short, practical document. Include only what the household "
    "has actually said; never invent devices or rooms, and never include current "
    "readings or device states."
)

# Every model is injected into the prompt on every turn, so each one has a token
# ceiling. Delta refreshes edit the existing content instead of regenerating it,
# which is what makes a cheap gate possible: with a decision model configured the
# server can skip the LLM call entirely when no new memory could change the model.
DEFAULT_MENTAL_MODEL_MAX_TOKENS = 400
DEFAULT_MENTAL_MODEL_TRIGGER = {
    "refresh_after_consolidation": True,
    "mode": "delta",
    # "all" requires the model's tags but still admits untagged memories, so a
    # second client writing to this bank without our tag is not invisible.
    "tags_match": "all",
}

DEFAULT_MENTAL_MODELS = [
    {
        "name": "User Information",
        "source_query": (
            "Summarize the user's habits, interests, priorities, lifestyle patterns, and "
            "personal preferences in clear, neutral language suitable for inclusion in "
            "an AI prompt. Describe recurring topics, likes, dislikes, routines, and "
            "contextual facts about the user. Exclude any preferences related to how an "
            "assistant should speak, format responses, manage conversation flow, ask "
            "questions, handle timing, or support text to speech. Do not include "
            "interaction rules, assistant capabilities, or response strategies."
        ),
        "tags": list(RETAIN_TAGS),
    },
    {
        "name": "Interaction Preferences",
        "source_query": (
            "Summarize how the user has asked the assistant to behave, in the "
            "user's own terms: things they asked it to stop doing, words or "
            "phrases they dislike, and requests about tone, humour, length or "
            "level of detail. Report only preferences the user actually stated. "
            "Do not infer traits from the assistant's own behaviour, and do not "
            "invent generalisations. Write short second-person instructions, each "
            "traceable to something the user said."
        ),
        "tags": list(RETAIN_TAGS),
    },
    {
        "name": "Household & Devices",
        "source_query": (
            "Summarize the home itself: its rooms and areas, the devices in them, and "
            "what the user calls each one ('the big lamp', 'the back door'). Include any "
            "quirks or problems the user has mentioned about the house or its devices. "
            "Report only what the user said; do not infer devices from requests, and do "
            "not include current readings or device states."
        ),
        "tags": list(RETAIN_TAGS),
    },
    {
        "name": "People & Routines",
        "source_query": (
            "Summarize the people in the user's household and life -- first names, "
            "relationships, birthdays -- and the recurring shape of their week: wake and "
            "sleep times, work patterns, regular commitments and events. Include only "
            "durable facts that recur; omit one-off visits and anything that was only "
            "true for a moment."
        ),
        "tags": list(RETAIN_TAGS),
    },
]


RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}
