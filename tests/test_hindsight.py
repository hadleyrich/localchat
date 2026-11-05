"""Tests for the Hindsight memory layer.

These drive the real ``HindsightMemory`` against a fake client, so they assert the
document shape the server actually consumes (context, timestamp, update_mode) and
the best-effort guarantee, without needing a Hindsight server.
"""

from __future__ import annotations

import asyncio
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
    DEFAULT_MENTAL_MODEL_MAX_TOKENS,
    DEFAULT_MENTAL_MODEL_TRIGGER,
    DEFAULT_MENTAL_MODELS,
    RETAIN_TAGS,
)
from custom_components.local_openai.hindsight import (
    HindsightMemory,
    _mental_model_changes,
    build_retain_context,
    format_transcript,
    options_from_data,
)

# The fake client reports "User Information" as already present, so the other
# shipped models are the ones a fresh ensure is expected to create.
EXPECTED_CREATED = [
    definition["name"]
    for definition in DEFAULT_MENTAL_MODELS
    if definition["name"] != "User Information"
]


HISTORY = [
    {"role": "user", "content": "Turn the kitchen light on"},
    {"role": "assistant", "content": "Done"},
    {"role": "tool", "content": "{}"},
    {"role": "user", "content": "   "},
]


class BankNotFound(Exception):
    """Stand-in for aiohttp's ClientResponseError with status 404."""

    status = 404


class FakeClient:
    """Minimal stand-in for hindsight_client.Hindsight."""

    def __init__(self) -> None:
        self.retained: list[dict] = []
        self.recalls: list[tuple] = []
        self.created: list[str] = []
        self.created_kwargs: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
        self.list_calls = 0
        self.closed = False
        self.fail = False
        self.missing_bank = False

    async def aretain(self, **kwargs) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("server down")
        self.retained.append(kwargs)
        return SimpleNamespace(success=True)

    async def arecall(self, bank_id: str, query: str, **kwargs) -> SimpleNamespace:
        if self.missing_bank:
            raise BankNotFound(f"Bank '{bank_id}' not found")
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
        if self.missing_bank:
            raise BankNotFound(f"Bank '{bank_id}' not found")
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
        self.created_kwargs.append({"name": name, **kwargs})

    async def aupdate_mental_model(self, bank_id: str, model_id: str, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("server down")
        self.updated.append((model_id, kwargs))

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


def test_retain_context_excludes_ephemeral_state_and_capability_claims() -> None:
    """The context tells the extractor what not to record.

    Without it a voice bank fills with live sensor readings and the assistant's
    own capability claims, which later recall presents as current truth.
    """
    context = build_retain_context("Kitchen Agent").lower()

    assert "durable facts" in context
    assert "output no facts for" in context
    for ephemeral in ("occupancy", "presence", "motion", "device states"):
        assert ephemeral in context
    for capability in ("abilities", "tools", "internet access"):
        assert capability in context
    for filler in ("greetings", "thanks", "one-word commands"):
        assert filler in context


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


async def test_recall_treats_a_missing_bank_as_no_memory(caplog) -> None:
    """A brand-new agent has no bank yet; that is not a warning.

    The bank only exists after the first successful retain, so every turn
    before that returned 404 and logged a warning against a server that was
    working perfectly.
    """
    memory, client = make_memory()
    client.missing_bank = True

    with caplog.at_level("WARNING"):
        assert await memory.async_recall("what coffee do I like?") == ""

    assert not [record for record in caplog.records if record.levelname == "WARNING"]


async def test_mental_models_treat_a_missing_bank_as_no_memory(caplog) -> None:
    """Same for the mental-model read on a bank that has not been created."""
    memory, client = make_memory()
    client.missing_bank = True

    with caplog.at_level("WARNING"):
        assert await memory.async_mental_models() == ""

    assert not [record for record in caplog.records if record.levelname == "WARNING"]


def test_client_timeout_outlasts_server_side_extraction() -> None:
    """Retain is slow: the server runs its extraction LLM before answering.

    A 30s client timeout cancelled every retain mid-extraction
    ("[RETAIN CANCELLED] ... client disconnected") and stored nothing, so the
    timeout has to outlast extraction rather than track a read.
    """
    client = hindsight._create_client("http://hindsight.example:8888")
    assert client._timeout >= 120


async def test_recall_gives_up_quickly_on_a_slow_server(monkeypatch) -> None:
    """Recall sits in front of the first token, so it must not inherit the write timeout."""
    memory, client = make_memory()

    async def slow_recall(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(1)

    monkeypatch.setattr(client, "arecall", slow_recall)
    monkeypatch.setattr(hindsight, "RECALL_TIMEOUT_SECONDS", 0.05)

    assert await memory.async_recall("what coffee do I like?") == ""


async def test_repeated_query_is_answered_from_cache() -> None:
    """A voice assistant repeats itself; an identical recent query costs no round trip.

    Most of a recall's latency is server-side reranking, so this is the
    difference between ~300ms and nothing on a repeated command.
    """
    memory, client = make_memory()

    first = await memory.async_recall("Turn on the kitchen light")
    second = await memory.async_recall("turn on the  kitchen LIGHT")

    assert first == second
    assert len(client.recalls) == 1


async def test_storing_a_conversation_drops_cached_recalls() -> None:
    """A finished turn can invalidate what was recalled, so the cache is cleared."""
    memory, client = make_memory()
    when = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)

    await memory.async_recall("what coffee do I like?")
    await memory.async_retain(
        HISTORY,
        conversation_id="01KMPFR4YY6XNW8SV3Y0BJ4RR8",
        timestamp=when,
        agent_name="Kitchen Agent",
    )
    await memory.async_recall("what coffee do I like?")

    assert len(client.recalls) == 2


async def test_memory_prompt_fetches_both_lookups() -> None:
    """Mental models and recall are gathered together, not serialised."""
    memory, client = make_memory()

    block = await memory.async_memory_prompt("Turn on the kitchen light")

    assert client.list_calls == 1
    assert len(client.recalls) == 1
    assert "Possibly relevant memories" in block


async def test_memory_prompt_can_run_with_recall_disabled() -> None:
    """Recall can be switched off without also losing the mental models."""
    memory, client = make_memory(recall_enabled=False)

    block = await memory.async_memory_prompt("Turn on the kitchen light")

    assert client.list_calls == 1
    assert client.recalls == []
    assert "Possibly relevant memories" not in block


async def test_first_recall_gets_the_longer_budget(monkeypatch) -> None:
    """A cold start pays TLS setup on the event loop, so the first call gets slack.

    Measured: ~1.6s of client set-up on the first request on top of a ~400ms
    server answer. Applying the steady-state 2s budget there discarded memory
    on the very first turn.
    """
    memory, client = make_memory()

    async def slow_recall(*args: object, **kwargs: object) -> SimpleNamespace:
        await asyncio.sleep(0.2)
        return SimpleNamespace(results=[SimpleNamespace(text="something")])

    monkeypatch.setattr(client, "arecall", slow_recall)
    monkeypatch.setattr(hindsight, "RECALL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(hindsight, "FIRST_RECALL_TIMEOUT_SECONDS", 1.0)

    assert await memory.async_recall("Turn on the kitchen light") == "- something"

    # Now warmed, the tight budget applies and the same call is abandoned.
    assert await memory.async_recall("Turn off the kitchen light") == ""


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

    assert client.created == EXPECTED_CREATED
    assert client.list_calls == 1


def test_mental_models_are_scoped_to_the_tags_we_actually_retain() -> None:
    """A model scoped to a tag no document carries can never see a source.

    Hindsight treats a mental model's tags as a scope filter over memory tags.
    Both shipped models once declared their own descriptive tags ("preferences",
    "user", "personality", "behavior", "tone") while retains only ever carried
    "conversation", so every refresh returned "no_sources_in_scope" and the
    content stayed empty -- silently, with last_refreshed_at still advancing.
    """
    for definition in DEFAULT_MENTAL_MODELS:
        assert definition["tags"] == list(RETAIN_TAGS), definition["name"]


async def test_mental_models_get_a_token_ceiling_and_delta_refresh() -> None:
    """Every model is capped and refreshes by delta.

    Both matter for cost: the cap bounds what is injected on every turn, and
    delta is the mode where a configured decision model can skip the LLM call
    entirely when no new memory could change the model.
    """
    memory, client = make_memory()

    await memory.async_ensure_mental_models()

    assert client.created_kwargs
    for kwargs in client.created_kwargs:
        assert kwargs["max_tokens"] == DEFAULT_MENTAL_MODEL_MAX_TOKENS
        assert kwargs["trigger"]["mode"] == "delta"
        assert kwargs["trigger"]["refresh_after_consolidation"] is True


def test_mental_model_changes_reconciles_a_stale_model() -> None:
    """A model created by an older version is brought in line, key by key.

    Creation is name-checked, so a bank that already holds the models would
    otherwise never pick up a corrected scope, a cap, or delta refresh.
    """
    definition = DEFAULT_MENTAL_MODELS[0]
    stale = SimpleNamespace(
        max_tokens=2048,
        source_query="an older query",
        tags=["preferences", "user"],
        trigger={"mode": "full", "refresh_after_consolidation": False, "budget": None},
    )

    changes = _mental_model_changes(definition, stale)

    assert changes["max_tokens"] == DEFAULT_MENTAL_MODEL_MAX_TOKENS
    assert changes["source_query"] == definition["source_query"]
    assert changes["tags"] == list(RETAIN_TAGS)
    assert changes["trigger"]["mode"] == "delta"
    assert changes["trigger"]["refresh_after_consolidation"] is True
    # Settings we do not manage survive the update.
    assert changes["trigger"]["budget"] is None

    current = SimpleNamespace(
        max_tokens=DEFAULT_MENTAL_MODEL_MAX_TOKENS,
        source_query=definition["source_query"],
        tags=list(RETAIN_TAGS),
        trigger=dict(DEFAULT_MENTAL_MODEL_TRIGGER),
    )
    assert _mental_model_changes(definition, current) == {}


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

    assert client.created == EXPECTED_CREATED


async def test_retain_creates_mental_models_once_the_bank_exists() -> None:
    """Retain runs first so the bank exists, then models are created just once."""
    memory, client = make_memory()

    await memory.async_retain(
        HISTORY,
        conversation_id="c4",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )
    assert client.created == EXPECTED_CREATED

    await memory.async_retain(
        HISTORY,
        conversation_id="c5",
        timestamp=datetime(2026, 11, 5, tzinfo=timezone.utc),
        agent_name="Agent",
    )
    assert client.created == EXPECTED_CREATED


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


async def test_remember_retains_a_deliberate_fact() -> None:
    """A fact the user asked for is stored on its own, tagged like a transcript.

    Tagging it with RETAIN_TAGS matters: the mental models are scoped to that
    tag, so an untagged fact would be invisible to every one of them.
    """
    memory, client = make_memory()

    assert await memory.async_remember("  The   bins go out on Tuesday  ") is True

    assert client.retained[-1]["content"] == "The bins go out on Tuesday"
    assert client.retained[-1]["tags"] == list(RETAIN_TAGS)
    assert client.retained[-1]["update_mode"] == "append"


async def test_remember_of_nothing_is_not_stored() -> None:
    """Whitespace is not a fact and does not reach the bank."""
    memory, client = make_memory()

    assert await memory.async_remember("   ") is False
    assert client.retained == []


async def test_remember_failure_is_reported_not_raised() -> None:
    """Memory stays best effort: a write failure is a False, not an exception."""
    memory, client = make_memory()
    client.fail = True

    assert await memory.async_remember("The bins go out on Tuesday") is False


async def test_recall_deduplicates_world_facts_and_observations() -> None:
    """The same fact arrives as a world fact and the observation built from it."""
    memory, client = make_memory()

    async def arecall(bank_id: str, query: str, **kwargs) -> SimpleNamespace:
        return SimpleNamespace(
            results=[
                SimpleNamespace(text="The bins go out on Tuesday nights"),
                SimpleNamespace(text="The bins go out on Tuesday nights"),
                SimpleNamespace(text="   "),
                SimpleNamespace(text="Recycling is collected fortnightly"),
            ]
        )

    client.arecall = arecall

    recalled = await memory.async_recall("bins")

    assert recalled.count("bins go out") == 1
    assert "Recycling is collected fortnightly" in recalled
