# Local Chat <small>_(Custom Integration for Home Assistant)_</small>

**Allows use of generic OpenAI-compatible LLM services**

This integration has been forked from https://github.com/skye-harris/hass_local_openai_llm

This integration supports **Hindsight**, a long-term memory system designed specifically for AI agents. When enabled, conversation histories are automatically summarized and stored in a Hindsight memory bank for future reference.

### Mental Models

Mental Models are pre-computed, automatically-refreshing summaries that define your agent's personality and remember user preferences. They are stored directly in your memory bank alongside observations for maximum context.

**Default Mental Models:**
- **Assistant Personality**: How your assistant should speak, behave, and present itself
- **Humor Guidelines**: When and how humor should be used
- **User Preferences**: Communication style and user preferences

**How They Work:**
1. Mental models are automatically created when Hindsight is enabled (always on)
2. All models are stored in the `{entity_name}-userprefs` bank alongside conversation memories
3. Content is retrieved and injected into the system prompt before each conversation
4. They automatically refresh after observation consolidation to stay current

**Benefits:**
- Consistent personality across all conversations
- Fast retrieval (pre-computed responses)
- Automatic learning from interactions
- Mental models have full context from the memory bank
- High-quality, curated responses for common topics

#### Setup:

1. Install and run Hindsight server (see [Hindsight documentation](https://hindsight.vectorize.io/))
2. During Local Chat configuration, enable "Hindsight Memory"
3. Provide your Hindsight server URL (e.g., `http://localhost:8888`)
4. Optionally customize the summarization prompt for memory extraction

#### How it Works:

- After each conversation completes, the conversation history is automatically processed
- The AI Task agent summarizes the conversation to extract:
  - Facts mentioned about users, preferences, or context
  - Patterns in communication style or preferences
  - Agent personality traits and behavior patterns
  - Important information for future conversations
- Extracted memories are stored in your Hindsight memory bank:
  - `{entity_name}-userprefs`: All memories including user preferences and agent personality
- Mental models are automatically created in this bank on first conversation and refresh after consolidation
- This happens asynchronously, so it doesn't slow down conversations

#### Benefits:

- Your AI agent remembers facts and preferences across sessions
- Consistent personality through Mental Models
- No need to repeat information in every conversation
- The agent builds a comprehensive knowledge base about users, context, and its own personality over time
- Uses Hindsight's multi-strategy retrieval (semantic, keyword, graph, temporal)
- Mental models provide instant, pre-computed responses for personality questions

#### Requirements:

- A running Hindsight server
- At least one AI Task agent configured (used for summarization and mental model generation)
- Memory bank is created automatically on first use

## Acknowledgements

- This integration is forked from [Hass Local OpenAI LLM](https://github.com/skye-harris/hass_local_openai_llm) integration by Skye Harris
