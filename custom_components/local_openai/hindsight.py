"""
Hindsight long-term memory for the Local OpenAI LLM integration.

Hindsight performs the extraction itself, so this module deliberately does little:
it decides *what* to send (one raw transcript per finished conversation), what to
ask for on the way out (mental models plus per-turn recall), and guarantees that a
memory failure never breaks a conversation.

The shape of the retain call matters more than it looks. Hindsight's retain prompt
renders ``Event Date`` (from ``timestamp``) and ``Context: …`` (from ``context``),
and uses the event date to resolve relative expressions such as "yesterday" into
absolute dates, so both are supplied explicitly rather than left to processing
time and to the model's imagination. ``update_mode="replace"`` keeps a re-retain of
the same conversation idempotent instead of appending a duplicate.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hindsight_client import Hindsight

from .const import (
    CONF_HINDSIGHT_BANK_ID,
    CONF_HINDSIGHT_BASE_URL,
    CONF_HINDSIGHT_ENABLED,
    CONF_HINDSIGHT_MENTAL_MODELS,
    CONF_HINDSIGHT_OPTIONS,
    CONF_HINDSIGHT_RECALL,
    DEFAULT_MENTAL_MODEL_TTL_SECONDS,
    DEFAULT_MENTAL_MODELS,
    DEFAULT_RECALL_BUDGET,
    DEFAULT_RECALL_MAX_TOKENS,
    DOMAIN,
    LOGGER,
    RETAIN_TAGS,
)

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant

# Identifies this integration to the server, in front of the client's own token
USER_AGENT = "local-openai-llm"

# Retain is not a quick write: the server runs its extraction LLM over the
# transcript before answering, which took 30-120s on a 20B model. The client
# timeout must outlast that, or the request is cancelled mid-extraction
# ("[RETAIN CANCELLED] ... client disconnected") and nothing is stored.
WRITE_TIMEOUT_SECONDS = 300.0

# Recall and mental models sit on the conversation path, so they get their own
# short bound instead of inheriting the generous write timeout. Recall sits in
# front of the first token that reaches the speaker, so a server that is slow to
# answer is abandoned rather than allowed to stall the reply.
READ_TIMEOUT_SECONDS = 10.0
RECALL_TIMEOUT_SECONDS = 2.0

# The first recall after start-up also pays for building the client's TLS
# context on the event loop, which measured ~1.6s on top of a ~400ms server
# answer, so the steady-state budget would discard memory on the first turn.
FIRST_RECALL_TIMEOUT_SECONDS = 10.0

# A voice assistant repeats itself ("turn on the kitchen light"), and most of a
# recall's cost is the server reranking candidates, so an identical recent query
# is answered from memory. The cache is cleared whenever a conversation is
# stored, so it can never serve facts the just-finished turn invalidated.
RECALL_CACHE_TTL_SECONDS = 60.0
RECALL_CACHE_MAX_ENTRIES = 32


async def _no_memory() -> str:
    """Stand-in coroutine so both memory lookups can be gathered."""
    return ""


def _create_client(base_url: str) -> Hindsight:
    """Create a Hindsight client (blocking, call in an executor)."""
    return Hindsight(
        base_url=base_url, timeout=WRITE_TIMEOUT_SECONDS, user_agent=USER_AGENT
    )


def _text_of(value: Any) -> str:
    """Return the text of a recall result, which may be an object or a dict."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(getattr(value, "text", "") or "")


def _as_items(result: Any) -> list[Any]:
    """Normalise a client list/recall response into a list of items."""
    for attr in ("items", "results"):
        value = getattr(result, attr, None)
        if value is not None:
            return list(value)
    if isinstance(result, dict):
        for key in ("items", "results"):
            value = result.get(key)
            if value is not None:
                return list(value)
        return []
    return list(result) if isinstance(result, (list, tuple)) else []


def build_retain_context(agent_name: str) -> str:
    """Describe a retained document for the retain prompt."""
    return (
        f"Transcript of a Home Assistant conversation with the assistant "
        f"'{agent_name}'. Turns are speech-to-text from a microphone: speaker "
        "labels are approximate and background television, radio or other people "
        "are sometimes captured as user turns."
    )


def format_transcript(history: Iterable[Mapping[str, Any]]) -> str:
    """Render conversation turns as the text Hindsight extracts facts from."""
    return "\n\n".join(
        f"{msg.get('role', 'unknown')}: {content}"
        for msg in history
        if msg.get("role") in ("user", "assistant")
        and (content := str(msg.get("content") or "").strip())
    )


@dataclass(frozen=True, slots=True)
class HindsightOptions:
    """Hindsight configuration for one config entry."""

    enabled: bool = False
    base_url: str = ""
    bank_id: str = ""
    recall: bool = True
    mental_models: bool = True

    @property
    def usable(self) -> bool:
        """Return True when memory is enabled and pointed at a server."""
        return self.enabled and bool(self.base_url)


def options_from_data(data: Mapping[str, Any]) -> HindsightOptions:
    """Build Hindsight options from a config entry's data."""
    raw = data.get(CONF_HINDSIGHT_OPTIONS) or {}
    if not isinstance(raw, Mapping):
        return HindsightOptions()

    return HindsightOptions(
        enabled=bool(raw.get(CONF_HINDSIGHT_ENABLED, False)),
        base_url=str(raw.get(CONF_HINDSIGHT_BASE_URL) or "").strip().rstrip("/"),
        bank_id=str(raw.get(CONF_HINDSIGHT_BANK_ID) or "").strip(),
        recall=bool(raw.get(CONF_HINDSIGHT_RECALL, True)),
        mental_models=bool(raw.get(CONF_HINDSIGHT_MENTAL_MODELS, True)),
    )


def _is_missing_bank(err: Exception) -> bool:
    """
    Return True when Hindsight says the bank does not exist yet.

    A bank is created by the first successful retain, so recall and
    mental-model reads return 404 on every turn until a conversation has been
    stored. That is the normal state of a new agent, not a failure worth
    logging a warning about on every turn.
    """
    return getattr(err, "status", None) == 404


class HindsightMemory:
    """
    Read and write memory for one config entry's Hindsight bank.

    Two kinds of memory are exposed:

    * mental models - pre-computed, slowly changing summaries ("who is the user",
      "how should I behave"). Cached, because they only change after consolidation.
    * recall - per-turn semantic retrieval for the thing being asked about.

    Every call is best effort: memory never breaks a conversation.
    """

    def __init__(  # noqa: PLR0913 - one keyword-only knob per tuning parameter
        self,
        hass: HomeAssistant,
        base_url: str,
        bank_id: str,
        *,
        recall_enabled: bool = True,
        mental_models_enabled: bool = True,
        recall_max_tokens: int = DEFAULT_RECALL_MAX_TOKENS,
        recall_budget: str = DEFAULT_RECALL_BUDGET,
        mental_model_ttl: int = DEFAULT_MENTAL_MODEL_TTL_SECONDS,
        client: Hindsight | None = None,
    ) -> None:
        """Initialize the memory helper."""
        self.hass = hass
        self.base_url = base_url.rstrip("/")
        self.bank_id = bank_id
        self.recall_enabled = recall_enabled
        self.mental_models_enabled = mental_models_enabled
        self.recall_max_tokens = recall_max_tokens
        self.recall_budget = recall_budget
        self.mental_model_ttl = mental_model_ttl
        self._client = client
        self._client_lock = asyncio.Lock()
        self._mental_models: str = ""
        self._mental_models_at: float | None = None
        self._mental_models_ensured = False
        self._recall_cache: dict[str, tuple[float, str]] = {}
        self._recall_warmed = False

    async def _async_client(self) -> Hindsight:
        """Return the shared client, creating it on first use."""
        async with self._client_lock:
            if self._client is None:
                self._client = await self.hass.async_add_executor_job(
                    _create_client, self.base_url
                )
        client = self._client
        assert client is not None  # noqa: S101 - set above under the lock
        return client

    async def async_memory_prompt(self, query: str | None) -> str:
        """
        Build the memory block for the system prompt.

        Returns an empty string when there is nothing to inject or Hindsight
        cannot be reached.
        """
        sections: list[str] = []

        # Both lookups hit the same server and neither depends on the other, so
        # fetch them together: the mental-model read is usually a few
        # milliseconds, but it should not be serialised in front of recall.
        mental_models, recalled = await asyncio.gather(
            self.async_mental_models() if self.mental_models_enabled else _no_memory(),
            self.async_recall(query) if self.recall_enabled and query else _no_memory(),
        )

        if mental_models:
            sections.append(mental_models)

        if recalled:
            sections.append(f"## Possibly relevant memories\n{recalled}")

        return "\n\n".join(sections)

    async def async_mental_models(self) -> str:
        """Return the mental model content, cached for ``mental_model_ttl``."""
        if (
            self._mental_models
            and self._mental_models_at is not None
            and time.monotonic() - self._mental_models_at < self.mental_model_ttl
        ):
            return self._mental_models

        try:
            client = await self._async_client()
            result = await asyncio.wait_for(
                client.alist_mental_models(self.bank_id, detail="content"),
                READ_TIMEOUT_SECONDS,
            )
            contents: list[str] = []
            for item in _as_items(result):
                content = getattr(item, "content", None)
                model_id = getattr(item, "id", None)
                if not content and model_id:
                    # Servers older than the detail parameter only return
                    # metadata from the list call, so fetch this one directly.
                    model = await asyncio.wait_for(
                        client.aget_mental_model(self.bank_id, model_id),
                        READ_TIMEOUT_SECONDS,
                    )
                    content = getattr(model, "content", None)
                if content:
                    name = getattr(item, "name", None) or model_id or "Memory"
                    contents.append(f"## {name}\n{content}")
        except Exception as err:
            if _is_missing_bank(err):
                LOGGER.debug(
                    "Bank %s does not exist yet at %s; no mental models",
                    self.bank_id,
                    self.base_url,
                )
                return ""
            LOGGER.warning(
                "Could not read mental models from %s: %s", self.base_url, err
            )
            return self._mental_models

        self._mental_models = "\n\n".join(contents)
        self._mental_models_at = time.monotonic()
        LOGGER.debug(
            "Loaded %s mental model(s) from bank %s (%s chars)",
            len(contents),
            self.bank_id,
            len(self._mental_models),
        )
        return self._mental_models

    async def async_recall(self, query: str) -> str:
        """Return memories relevant to ``query``, formatted for a prompt."""
        cache_key = " ".join(query.lower().split())
        if (cached := self._cached_recall(cache_key)) is not None:
            LOGGER.debug(
                "Recall cache hit in bank %s for: %s", self.bank_id, query[:80]
            )
            return cached

        try:
            client = await self._async_client()
            recall_timeout = (
                RECALL_TIMEOUT_SECONDS
                if self._recall_warmed
                else FIRST_RECALL_TIMEOUT_SECONDS
            )
            result = await asyncio.wait_for(
                client.arecall(
                    self.bank_id,
                    query,
                    max_tokens=self.recall_max_tokens,
                    budget=self.recall_budget,
                ),
                recall_timeout,
            )
        except Exception as err:
            if _is_missing_bank(err):
                LOGGER.debug(
                    "Bank %s does not exist yet at %s; nothing to recall",
                    self.bank_id,
                    self.base_url,
                )
                return ""
            LOGGER.warning("Could not recall from %s: %s", self.base_url, err)
            return ""

        self._recall_warmed = True
        lines = [
            f"- {text}"
            for item in _as_items(result)
            if (text := _text_of(item).strip())
        ]
        LOGGER.debug(
            "Recalled %s memories from bank %s for: %s",
            len(lines),
            self.bank_id,
            query[:80],
        )
        recalled = "\n".join(lines)
        self._store_recall(cache_key, recalled)
        return recalled

    def _cached_recall(self, cache_key: str) -> str | None:
        """Return a recent recall of this exact query, if it is still fresh."""
        entry = self._recall_cache.get(cache_key)
        if entry is None:
            return None

        stored_at, recalled = entry
        if time.monotonic() - stored_at > RECALL_CACHE_TTL_SECONDS:
            self._recall_cache.pop(cache_key, None)
            return None

        return recalled

    def _store_recall(self, cache_key: str, recalled: str) -> None:
        """Remember this recall briefly, dropping the oldest entry when full."""
        if len(self._recall_cache) >= RECALL_CACHE_MAX_ENTRIES:
            oldest = min(self._recall_cache, key=lambda key: self._recall_cache[key][0])
            self._recall_cache.pop(oldest, None)

        self._recall_cache[cache_key] = (time.monotonic(), recalled)

    async def async_retain(
        self,
        history: Iterable[Mapping[str, Any]],
        *,
        conversation_id: str,
        timestamp: datetime,
        agent_name: str,
    ) -> None:
        """Store a finished conversation for extraction by Hindsight."""
        transcript = format_transcript(history)
        if not transcript.strip():
            LOGGER.debug("No conversation content to store")
            return

        try:
            client = await self._async_client()
            await client.aretain(
                bank_id=self.bank_id,
                content=transcript,
                context=build_retain_context(agent_name),
                timestamp=timestamp,
                document_id=conversation_id,
                update_mode="replace",
                tags=list(RETAIN_TAGS),
            )
        except Exception as err:
            LOGGER.warning("Could not store conversation in %s: %s", self.base_url, err)
            return

        LOGGER.debug("Stored conversation %s in bank %s", conversation_id, self.bank_id)

        # Mental models refresh after consolidation, so drop the cached copy
        # and let the next turn pick up whatever changed. Cached recalls are
        # dropped for the same reason: this conversation may invalidate them.
        self._mental_models_at = None
        self._recall_cache.clear()

        # The retain above created the bank if it did not exist, so create the
        # default mental models now rather than racing bank creation on first use.
        await self.async_ensure_mental_models()

    async def async_ensure_mental_models(self) -> None:
        """
        Create the default mental models in the bank if they are missing.

        Called after a successful retain has guaranteed the bank exists, once per
        loaded entry; the models themselves are refreshed by the server after
        consolidation. A failed attempt is retried on the next conversation
        instead of being written off.
        """
        if self._mental_models_ensured:
            return

        try:
            client = await self._async_client()
        except Exception as err:
            LOGGER.warning("Could not reach Hindsight at %s: %s", self.base_url, err)
            return

        try:
            result = await client.alist_mental_models(self.bank_id)
            existing = {getattr(item, "name", "") for item in _as_items(result)}
        except Exception as err:
            LOGGER.debug(
                "Bank %s not readable yet (%s), creating models", self.bank_id, err
            )
            existing = set()

        failures = 0
        for definition in DEFAULT_MENTAL_MODELS:
            if definition["name"] in existing:
                continue
            try:
                await client.acreate_mental_model(
                    self.bank_id,
                    name=definition["name"],
                    source_query=definition["source_query"],
                    tags=definition.get("tags", []),
                    trigger={"refresh_after_consolidation": True},
                )
            except Exception as err:
                failures += 1
                LOGGER.warning(
                    "Could not create mental model '%s' in %s: %s",
                    definition["name"],
                    self.bank_id,
                    err,
                )
            else:
                LOGGER.info(
                    "Created mental model '%s' in bank %s",
                    definition["name"],
                    self.bank_id,
                )

        if not failures:
            self._mental_models_ensured = True

    async def async_close(self) -> None:
        """Close the underlying client."""
        if self._client is None:
            return
        client, self._client = self._client, None
        try:
            await client.aclose()
        except Exception:
            LOGGER.debug("Error closing Hindsight client", exc_info=True)


def async_get_memory(  # noqa: PLR0913 - mirrors the per-bank tuning arguments
    hass: HomeAssistant,
    entry_id: str,
    base_url: str,
    bank_id: str,
    *,
    recall_enabled: bool = True,
    mental_models_enabled: bool = True,
    client: Hindsight | None = None,
) -> HindsightMemory:
    """Return the memory helper for a bank, creating it on first use."""
    memories: dict[str, HindsightMemory] = hass.data.setdefault(DOMAIN, {}).setdefault(
        entry_id, {}
    )
    if (memory := memories.get(bank_id)) is None:
        memory = HindsightMemory(
            hass,
            base_url,
            bank_id,
            recall_enabled=recall_enabled,
            mental_models_enabled=mental_models_enabled,
            client=client,
        )
        memories[bank_id] = memory
    return memory


async def async_close_memories(hass: HomeAssistant, entry_id: str) -> None:
    """Close every Hindsight client belonging to a config entry."""
    memories = hass.data.get(DOMAIN, {}).pop(entry_id, {})
    for memory in memories.values():
        await memory.async_close()
