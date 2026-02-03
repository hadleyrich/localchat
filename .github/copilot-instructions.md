# LocalChat Project Instructions

## Project Overview

**LocalChat** is a Home Assistant custom integration that enables use of generic OpenAI-compatible LLM services. It features integrated support for **Hindsight**, a long-term memory system that automatically summarizes and stores conversation histories for persistent context across sessions.

- **Repository**: Local Chat integration for Home Assistant
- **Language**: Python 3.13+
- **Package Manager**: UV (uv sync)
- **Key Dependencies**: homeassistant, openai, hindsight-client

## Project Structure

```
localchat/
├── custom_components/localchat/          # Main integration code
│   ├── __init__.py                       # Entry point and configuration
│   ├── config_flow.py                    # Configuration UI flow
│   ├── conversation.py                   # Conversation entity (handles user messages)
│   ├── entity.py                         # Base entity class with LLM handling
│   ├── ai_task.py                        # AI Task agent (conversation summarization)
│   ├── hindsight.py                      # Hindsight memory integration
│   ├── const.py                          # Constants and configuration keys
│   ├── manifest.json                     # Integration metadata
│   └── translations/en.json              # English translations
├── pyproject.toml                        # UV-compatible project configuration
├── requirements.txt                      # Legacy requirements
└── README.md                             # User documentation
```

## Key Components

### conversation.py
- **Purpose**: Main conversation entity that processes user input and generates responses
- **Key Method**: `_extract_conversation_history()` - Extracts text messages from chat log
  - **Important**: Must filter out `ToolResultContent` objects to avoid AttributeError
  - Only processes text messages with `content` attribute

### hindsight.py
- **Purpose**: Handles memory storage integration with Hindsight server
- **Key Method**: `process_conversation_memory()` - Stores conversation summaries
- **Important**: Metadata fields like `message_count` must be strings, not integers (Pydantic validation)

### entity.py
- **Purpose**: Base entity with LLM integration for generating responses
- **Pattern**: Handles tool results using `isinstance(content, conversation.ToolResultContent)`

### ai_task.py
- **Purpose**: AI Task agent that summarizes conversations for Hindsight storage
- **Role**: Called to extract facts and key information from conversations

## Common Patterns

### Filtering Content Types
When processing `chat_log.content`, always check content type:
```python
if isinstance(content, conversation.ToolResultContent):
    continue  # Skip tool results
# Process text content
```

### Type Validation with Pydantic
When passing data to hindsight-client APIs, ensure field types match the MemoryItem schema:
- `metadata.message_count` must be a string: use `str(value)`
- All metadata fields should be strings or serializable types

### Async Patterns
- Hindsight operations use async: `await client.aretain_batch()`
- Always use proper error handling with try/except for external API calls

## Configuration

### pyproject.toml Structure
- **Main dependencies**: Listed in `[project] dependencies`
- **Dev dependencies**: Listed in `[project.optional-dependencies] dev`
- **Python requirement**: `>=3.13.2` (matches homeassistant requirement)
- **UV config**: `[tool.uv] dev-dependencies` for development tools

### Environment Setup
```bash
uv sync              # Install all dependencies including dev
uv run python script  # Run scripts with proper environment
```

## Common Issues & Solutions

### Pydantic ValidationError for metadata
- **Issue**: `metadata.message_count` Input should be a valid string
- **Solution**: Convert integers to strings before passing to hindsight-client: `str(len(...))`

### AttributeError: 'ToolResultContent' object has no attribute 'content'
- **Issue**: Processing tool results as if they're text messages
- **Solution**: Filter with `isinstance(content, conversation.ToolResultContent)`

### Python version conflict
- **Issue**: `requires-python` doesn't match dependency requirements
- **Solution**: Ensure `requires-python` is `>=3.13.2` (homeassistant minimum)

## Development Workflow

1. **Make changes** to code in `custom_components/localchat/`
2. **Test** against Home Assistant instance
3. **Update types**: Ensure Pydantic models receive correct types
4. **Run linting**: Use ruff (configured in pyproject.toml)
5. **Commit**: Changes to the repository

## Important Notes

- This is a Home Assistant custom integration; code runs within HA context
- Async/await patterns are essential for Home Assistant compatibility
- Hindsight integration is optional but requires proper error handling
- Memory bank IDs and bank configurations are user-provided via config flow
- Conversations are processed asynchronously to avoid blocking the UI

## Related Integrations

- **conversation**: Core Home Assistant conversation framework
- **assist_pipeline**: Voice/text processing pipeline
- **intent**: Intent recognition system

## Testing Hindsight Integration

When debugging Hindsight issues:
1. Verify Hindsight server is running and accessible
2. Check `process_conversation_memory()` event handling
3. Ensure `ai_task.py` successfully summarizes conversations
4. Validate metadata types match MemoryItem schema
5. Monitor logs for async task completion
