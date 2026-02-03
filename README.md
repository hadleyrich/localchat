# Local Chat <small>_(Custom Integration for Home Assistant)_</small>

**Allows use of generic OpenAI-compatible LLM services, such as (but not limited to):**

- llama.cpp
- vLLM
- LM Studio
- Ollama
- OpenRouter
- Scaleway

**This integration has been forked from Home Assistants OpenRouter integration, with the following changes:**

- Added server URL to the initial server configuration
- Made the API Key optional during initial server configuration: can be left blank if your local server does not require one
- Uses streamed LLM responses
- Conversation Agents support TTS streaming
- Automatically strips `<think>` tags from responses
- Added support for image inputs for AI Task Agents
- Added support for reconfiguring Conversation Agents
- Added option to trim conversation history to help stay within your context window
- Added temperature control
- Added option to strip emojis from responses
- Added support for parallel tool calling
- Added experimental Retrieval Augmented Generation capability
- Added chat template arguments support
- **Added Hindsight long-term memory integration for storing conversation memories**

---

## Installation

### Install via HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

Adding Tools for Assist to HACS can be using this button:  
[![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=skye-harris&repository=hass_local_openai_llm&category=integration)

<br>

> [!NOTE]
> If the button above doesn't work, add `https://github.com/skye-harris/hass_local_openai_llm` as a custom repository of type Integration in HACS.

* Click install on the `Local Chat` integration.
* Restart Home Assistant.

<details><summary>Manual Install</summary>

* Copy the `localchat`  folder from [latest release](https://github.com/skye-harris/hass_local_openai_llm/releases/latest) to the [
  `custom_components` folder](https://developers.home-assistant.io/docs/creating_integration_file_structure/#where-home-assistant-looks-for-integrations) in your config directory.
* Restart the Home Assistant.

</details>

## Integration Configuration

After installation, configure the integration through Home Assistant's UI:

1. Go to `Settings` → `Devices & Services`.
2. Click `Add Integration`.
3. Search for `Local Chat`.
4. Follow the setup wizard to configure your desired services.

### Configuration Notes

- The Server URL must be a fully qualified URL pointing to an OpenAI-compatible API.
    - This typically ends with `/v1` but may differ depending on your server configuration.
- If you have the `Extended OpenAI Conversation` integration installed, this has a dependency of an older version of the OpenAI client library.
    - It is strongly recommended this be uninstalled to ensure that HACS installs the correct OpenAI client library.
- Assist requires a fairly lengthy context for tooling and entity definitions.
    - It is strongly recommended to use _at least_ 8k context size and to limit history length to avoid context overflow issues.
    - This is not configurable through OpenAI-compatible APIs, and needs to be configured with the inference server directly.
- Tool calling must be enabled in your inference engine, eg:
    - **vLLM**: https://docs.vllm.ai/en/latest/features/tool_calling/
    - **llama.cpp**: https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- Parallel tool calling requires support from both your model and inference server.
    - In some cases, control of this is handled by the server directly, in which case toggling this will not have any result.
- Chat Template Arguments allow you to provide custom arguments to your model
    - Arguments are supplied as key/value pairs and provided to the `chat_template_kwargs` request parameter
    - Values support Jinja2 templates, in order to provide non-string and more complex data structures
    - Arguments differ per model, and not all models make use of user-provided arguments
    - See your models documentation for what arguments are available to be used

### Experimental: Date/Time Context Injection Role

This integration supports injecting some dynamic content, presently the date and time, into the active Conversation Agent prompt when making a request.
This was added as it is beneficial for the model to be grounded with this context in its role as an assistant, and was previously added to the system prompt by Home Assistant itself before later being removed due to negative effects on prompt caching
and performance.

This was previously always-on but has been extracted as an **experimental** configuration option as this is not a once-size-fits-all for all models.
To this end I have provided a number of options so that users can try them out and select the one that works best, or disable entirely if none work well, for their chosen model.

The available options are:

#### <u>Tool Result</u>:
The date and time are inserted as a `Tool Call Result` message to the model, before the current user message.

As long as the model does not reject it, this is the recommended method to use and produces the most reliable results during testing.

#### <u>Assistant</u>:
The date and time are inserted as an additional `Assistant` message to the model, before the current user message.

In cases where the `Tool Call Result` role method does not work for a model, this is the next recommended to test with.

#### <u>User</u>:
The date and time are inserted as an additional `User` message to the model, before the current user message.

Recommended only where neither the `System` nor `Assistant` injection methods work for the model, but may not produce desirable results.
Some models have been known to repeat the date/time back to the user without request.

#### <u>Disabled (no selection)</u>:
If your model simply refuses to work well with any method, simply remove the value from the configuration option to disable this again.

### Hindsight Long-Term Memory Integration

This integration now supports **Hindsight**, a long-term memory system designed specifically for AI agents. When enabled, conversation histories are automatically summarized and stored in a Hindsight memory bank for future reference.

#### Setup:

1. Install and run Hindsight server (see [Hindsight documentation](https://hindsight.vectorize.io/))
2. During Local Chat configuration, enable "Hindsight Memory"
3. Provide your Hindsight server URL (e.g., `http://localhost:8888`)
4. Specify a Memory Bank ID (e.g., `my-assistant`)

#### How it Works:

- After each conversation completes, the conversation history is automatically processed
- The AI Task agent summarizes the conversation to extract:
  - Facts mentioned about users, preferences, or context
  - Patterns in communication style or preferences
  - Important information for future conversations
- Extracted memories are stored in your Hindsight memory bank
- This happens asynchronously, so it doesn't slow down conversations

#### Benefits:

- Your AI agent remembers facts and preferences across sessions
- No need to repeat information in every conversation
- The agent builds a knowledge base about users and context over time
- Uses Hindsight's multi-strategy retrieval (semantic, keyword, graph, temporal)

#### Requirements:

- A running Hindsight server
- At least one AI Task agent configured (used for summarization)
- Hindsight memory bank created (automatic on first use)


## Web Search & Additional Tools

Looking to add some more functionality to your Home Assistant conversation agent, such as web and localised business/location search? Check out my [Tools for Assist](https://github.com/skye-harris/llm_intents) integration here!

These tools exist as a separate integration for compatibility across the wider Home Assistant Conversation ecosystem.

## Acknowledgements

- This integration is forked from the [OpenRouter](https://github.com/home-assistant/core/tree/dev/homeassistant/components/open_router) integration for Home Assistant by [@joostlek](https://github.com/joostlek)

---

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/skyeharris)
