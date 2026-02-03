# Local Chat <small>_(Custom Integration for Home Assistant)_</small>

**Allows use of generic OpenAI-compatible LLM services**

This integration has been forked from https://github.com/skye-harris/hass_local_openai_llm

This integration supports **Hindsight**, a long-term memory system designed specifically for AI agents. When enabled, conversation histories are automatically summarized and stored in a Hindsight memory bank for future reference.

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

## Acknowledgements

- This integration is forked from [Hass Local OpenAI LLM](https://github.com/skye-harris/hass_local_openai_llm) integration by Skye Harris
