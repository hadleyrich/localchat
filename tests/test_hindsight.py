"""Tests for the Hindsight memory layer.

These drive the real ``HindsightMemory`` against a fake client, so they assert the
document shape the server actually consumes (context, timestamp, update_mode) and
the best-effort guarantee, without needing a Hindsight server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from hindsight_client import Hindsight

from custom_components.local_openai import hindsight
from custom_components.local_openai.const import (
    CONF_HINDSIGHT_BANK_ID,
    CONF_HINDSIGHT_BASE_URL,
    CONF_HINDSIGHT_ENABLED,
    CONF_HINDSIGHT_MENTAL_MODELS,
    CONF_HINDSIGHT_OPTIONS,
    CONF_HINDSIGHT_RECALL,
)
from custom_components.local_openai.hindsight import (
    HindsightMemory,
    build_retain_context,
    format_transcript,
    options_from_data,
)

HISTORY = [
    {"role": "user", "content": "Turn the kitchen light on"},
    {"role": "assistant", "content": "Done"},
    {"role": "tool", "content": "{}"},
    {"role": "user", "content": "   "},
]


class FakeClient:
    """Minimal stand-in for hindsight_client.Hindsight."""

    def __init__(self) -> None:
        self.retained: list[dict] = []
        self.recalls: list[tuple] = []
        self.created: list[str] = []
        self.list_calls = 0
        self.closed = False
        self.fail = False

    async def aretain(self, **kwargs) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("server down")
        self.retained.append(kwargs)
        return SimpleNamespace(success=True)

    async def arecall(self, bank_id: str, query: str, **kwargs) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("server down")
        self.recalls.append((bank_id, query, kwargs))
        return SimpleNamespace(
            results=[
                SimpleNamespace(text="Prefers the kitchen lights dim"),
                {"text": "Has a dog named Bess"},
                SimpleNamespace(text=""),
            ]
        )

    async def alist_mental_models(self, bank_id: str, **kwargs) -> SimpleNamespace:
        self.list_calls += 1
        if self.fail:
            raise RuntimeError("server down")
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    id="mm-user", name="User Information", content="Lives in Timaru"
                )
            ]
        )

    async def aget_mental_model(self, bank_id: str, model_id: str, **kwargs):
        return SimpleNamespace(id=model_id, name=model_id, content="fetched")

    async def acreate_mental_model(self, bank_id: str, name: str, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("server down")
        self.created.append(name)

    async def aclose(self) -> None:
        self.closed = True


def make_memory(**kwargs) -> tuple[HindsightMemory, FakeClient]:
    """Return a memory helper wired to a fake client."""
    client = FakeClient()
    memory = HindsightMemory(
        object(),
        "http://hindsight.example:8888/",
        "userprefs",
        client=cast("Hindsight", client),
        **kwargs,
    )
    return memory, client


def test_format_transcript_keeps_prose_only() -> None:
    """Tool results and blank turns are not part of what Hindsight extracts from."""
    assert format_transcript(HISTORY) == (
        "user: Turn the kitchen light on\n\nassistant: Done"
    )


def test_format_transcript_of_nothing() -> None:
    """An empty history formats to an empty string."""
    assert format_transcript([]) == ""


def test_retain_context_names_the_agent() -> None:
    """The context slot tells the extractor what kind of document this is."""
    context = build_retain_context("Kitchen Agent")
    assert "Kitchen Agent" in context
    assert "speech-to-text" in context


def test_options_default_to_disabled() -> None:
    """A config entry without the section leaves memory off."""
    options = options_from_data({})
    assert options.enabled is False
    assert options.usable is False


def test_options_are_read_from_the_section() -> None:
    """The section values map onto the option object, with the URL normalised."""
    options = options_from_data(
        {
            CONF_HINDSIGHT_OPTIONS: {
                CONF_HINDSIGHT_ENABLED: True,
                CONF_HINDSIGHT_BASE_URL: " http://belinda:8888/ ",
                CONF_HINDSIGHT_BANK_ID: "llama_cpp-userprefs",
                CONF_HINDSIGHT_RECALL: False,
                CONF_HINDSIGHT_MENTAL_MODELS: False,
            }
        }
    )
    assert options.usable is True
    assert options.base_url == "http://belinda:8888"
    assert options.bank_id == "llama_cpp-userprefs"
    assert options.recall is False
    assert options.mental_models is False


def test_enabled_without_url_is_not_usable() -> None:
    """Half-configured memory stays inert instead of calling an empty URL."""
    options = options_from_data(
        {CONF_HINDSIGHT_OPTIONS: {CONF_HINDSIGHT_ENABLED: True}}
    )
    assert options.usable is False


async def test_retain_sends_context_timestamp_and_replace() -> None:
    """The retain call carries the document shape the server consumes."""
    memory, client = make_memory()
    when = datetime(2026, 11, 5, 9, 30, tzinfo=timezone.utc)

    await memory.async_retain(
        HISTORY,
        conversation_id="01KMPFR4YY6XNW8SV3Y0BJ4RR8",
        timestamp=when,
        agent_name="Kitchen Agent",
    )

    assert len(client.retained) == 1
    call = client.retained[0]
    assert call["bank_id"] == "userprefs"
    assert call["document_id"] == "01KMPFR4YY6XNW8SV3Y0BJ4RR8"
    assert call["timestamp"] == when
    assert call["update_mode"] == "replace"
    assert call["tags"] == ["conversation"]
    assert "Kitchen Agent" in call["context"]
    assert call["content"].startswith("user: Turn the kitchen light on")
    assert "metadata" not in call


async def test_retain_skips_empty_history() -> None:
    """Nothing worth storing means no request at all."""
    memory, client = make_memory()

    await memory.async_retain(
        [{"role": "tool", "content": "{}"}],
        conversation_id="c1",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )

    assert client.retained == []


async def test_retain_is_best_effort() -> None:
    """A failing server never raises into the conversation."""
    memory, client = make_memory()
    client.fail = True

    await memory.async_retain(
        HISTORY,
        conversation_id="c2",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )

    assert client.retained == []


async def test_memory_prompt_combines_models_and_recall() -> None:
    """Both memory sources land in the prompt block."""
    memory, _ = make_memory()

    block = await memory.async_memory_prompt("what should I do tonight?")

    assert "## User Information" in block
    assert "Lives in Timaru" in block
    assert "## Possibly relevant memories" in block
    assert "- Prefers the kitchen lights dim" in block
    assert "- Has a dog named Bess" in block


async def test_recall_skips_blank_text() -> None:
    """Empty recall results do not become empty bullets."""
    memory, _ = make_memory()

    recalled = await memory.async_recall("kitchen")

    assert recalled.count("\n") == 1
    assert recalled.startswith("- Prefers the kitchen lights dim")


async def test_recall_respects_flags() -> None:
    """Turning both sources off produces no block and no calls."""
    memory, client = make_memory(recall_enabled=False, mental_models_enabled=False)

    assert await memory.async_memory_prompt("anything") == ""
    assert client.recalls == []
    assert client.list_calls == 0


async def test_memory_is_best_effort_on_failure() -> None:
    """An unreachable server yields no memory rather than an error."""
    memory, client = make_memory()
    client.fail = True

    assert await memory.async_memory_prompt("hello") == ""
    assert await memory.async_recall("hello") == ""
    assert await memory.async_mental_models() == ""


async def test_mental_models_are_cached_until_retain() -> None:
    """A cached copy serves voice turns; a retain invalidates it."""
    memory, client = make_memory()

    first = await memory.async_mental_models()
    second = await memory.async_mental_models()
    assert first == second
    assert client.list_calls == 1

    await memory.async_retain(
        HISTORY,
        conversation_id="c3",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )

    # Retain also checks the bank for missing mental models, so compare against
    # the count at that point rather than a fixed total.
    calls_before = client.list_calls
    await memory.async_mental_models()
    assert client.list_calls > calls_before


async def test_ensure_mental_models_creates_only_missing_ones() -> None:
    """Existing models are left alone, the rest are created once."""
    memory, client = make_memory()

    await memory.async_ensure_mental_models()
    await memory.async_ensure_mental_models()

    assert client.created == ["Agent Personality"]
    assert client.list_calls == 1


async def test_ensure_mental_models_survives_an_unreachable_server() -> None:
    """Model creation is best effort and does not raise."""
    memory, client = make_memory()
    client.fail = True

    await memory.async_ensure_mental_models()

    assert client.created == []


async def test_failed_ensure_is_retried() -> None:
    """A failure does not write the models off for the life of the entry."""
    memory, client = make_memory()
    client.fail = True

    await memory.async_ensure_mental_models()
    assert client.created == []

    client.fail = False
    await memory.async_ensure_mental_models()

    assert client.created == ["Agent Personality"]


async def test_retain_creates_mental_models_once_the_bank_exists() -> None:
    """Retain runs first so the bank exists, then models are created just once."""
    memory, client = make_memory()

    await memory.async_retain(
        HISTORY,
        conversation_id="c4",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )
    assert client.created == ["Agent Personality"]

    await memory.async_retain(
        HISTORY,
        conversation_id="c5",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )
    assert client.created == ["Agent Personality"]


async def test_close_closes_the_client() -> None:
    """Unloading the entry closes the shared client."""
    memory, client = make_memory()

    await memory.async_close()

    assert client.closed is True
    assert memory._client is None  # noqa: SLF001 - asserting teardown state


async def test_memory_cache_is_keyed_by_bank(fake_hass) -> None:
    """Two banks on one entry get separate helpers, and closing clears both."""
    first = hindsight.async_get_memory(fake_hass, "entry", "http://h:8888", "bank-a")
    again = hindsight.async_get_memory(fake_hass, "entry", "http://h:8888", "bank-a")
    second = hindsight.async_get_memory(fake_hass, "entry", "http://h:8888", "bank-b")

    assert first is again
    assert first is not second

    await hindsight.async_close_memories(fake_hass, "entry")
    assert fake_hass.data.get("local_openai") is not None
    assert "entry" not in fake_hass.data["local_openai"]


@pytest.fixture
def fake_hass() -> SimpleNamespace:
    """Stand-in for HomeAssistant, with only the data dict the cache uses."""
    return SimpleNamespace(data={}, async_add_executor_job=None)


async def test_store_conversation_is_not_gated_on_continuation(
    fake_hass, monkeypatch
) -> None:
    """A reply that invites a follow-up must still be remembered.

    Regression: the store used to run only when ``continue_conversation`` was
    False, so an agent with "always continue conversation" enabled — the
    natural setting for voice follow-ups — never retained anything at all.
    """
    from custom_components.local_openai import (  # noqa: PLC0415
        conversation as conversation_module,
    )

    retained: list[dict] = []

    class RecordingMemory:
        async def async_retain(self, history, **kwargs) -> None:
            retained.append({"history": history, **kwargs})

    monkeypatch.setattr(
        conversation_module.LocalAiConversationEntity,
        "_memory",
        property(lambda self: RecordingMemory()),
    )

    scheduled: list = []
    fake_hass.async_create_task = lambda coro, **kwargs: scheduled.append(coro)

    entity = object.__new__(conversation_module.LocalAiConversationEntity)
    entity.hass = fake_hass
    entity.entry = SimpleNamespace(entry_id="entry-id", data={})
    entity.subentry = SimpleNamespace(title="Llama: openai/gpt-oss-20b AI Agent")

    chat_log = SimpleNamespace(
        conversation_id="conv-1",
        content=[
            SimpleNamespace(role="user", content="Turn the kitchen light on"),
            SimpleNamespace(role="assistant", content="Done. Anything else?"),
        ],
    )

    entity._async_store_conversation(chat_log)

    assert len(scheduled) == 1, "the turn was not handed to Hindsight"
    await scheduled[0]
    assert retained[0]["conversation_id"] == "conv-1"
    assert [message["content"] for message in retained[0]["history"]] == [
        "Turn the kitchen light on",
        "Done. Anything else?",
    ]


def test_config_schema_wires_the_section_through() -> None:
    """The config flow's section validates and maps onto usable options.

    This is the join between the form and the memory layer, and the piece most
    likely to break when upstream reorganises the config flow.
    """
    from custom_components.local_openai.config_flow import (  # noqa: PLC0415
        LocalAiConfigFlow,
    )

    validated = LocalAiConfigFlow.get_schema()(
        {
            "server_name": "Test server",
            "base_url": "http://hindsight.example:8888",
            CONF_HINDSIGHT_OPTIONS: {
                CONF_HINDSIGHT_ENABLED: True,
                CONF_HINDSIGHT_BASE_URL: "http://belinda:8888",
                CONF_HINDSIGHT_BANK_ID: "llama_cpp-userprefs",
            },
        }
    )

    options = options_from_data(validated)
    assert options.usable is True
    assert options.base_url == "http://belinda:8888"
    assert options.bank_id == "llama_cpp-userprefs"
    assert options.recall is True
    assert options.mental_models is True
