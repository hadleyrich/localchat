"""Hindsight client wrapper for Local Chat."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import LOGGER


class HindsightClient:
    """Client for interacting with Hindsight API."""

    def __init__(self, base_url: str) -> None:
        """Initialize the Hindsight client."""
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def retain(
        self,
        bank_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Store information in a memory bank.

        Args:
            bank_id: The memory bank identifier
            content: The information to store
            metadata: Optional metadata to attach to the memory

        Returns:
            Response from the Hindsight API

        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/banks/{bank_id}/retain"

        payload: dict[str, Any] = {"content": content}
        if metadata:
            payload["metadata"] = metadata

        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            LOGGER.error("Error storing memory in Hindsight: %s", err)
            raise
        except TimeoutError:
            LOGGER.error("Timeout storing memory in Hindsight")
            raise

    async def recall(
        self,
        bank_id: str,
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Search and retrieve memories from a memory bank.

        Args:
            bank_id: The memory bank identifier
            query: The search query
            limit: Maximum number of results to return

        Returns:
            Response from the Hindsight API

        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/banks/{bank_id}/recall"

        payload = {"query": query, "limit": limit}

        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            LOGGER.error("Error recalling memory from Hindsight: %s", err)
            raise
        except TimeoutError:
            LOGGER.error("Timeout recalling memory from Hindsight")
            raise

    async def reflect(
        self,
        bank_id: str,
        query: str,
    ) -> dict[str, Any]:
        """
        Generate a disposition-aware response using memories.

        Args:
            bank_id: The memory bank identifier
            query: The query to reflect on

        Returns:
            Response from the Hindsight API

        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/banks/{bank_id}/reflect"

        payload = {"query": query}

        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            LOGGER.error("Error reflecting with Hindsight: %s", err)
            raise
        except TimeoutError:
            LOGGER.error("Timeout reflecting with Hindsight")
            raise

    async def create_bank(
        self,
        bank_id: str,
        mission: str | None = None,
        directives: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new memory bank.

        Args:
            bank_id: The memory bank identifier
            mission: Optional mission statement for the bank
            directives: Optional list of directives for the bank

        Returns:
            Response from the Hindsight API

        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/banks"

        payload: dict[str, Any] = {"bank_id": bank_id}
        if mission:
            payload["mission"] = mission
        if directives:
            payload["directives"] = directives

        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            LOGGER.error("Error creating memory bank in Hindsight: %s", err)
            raise
        except TimeoutError:
            LOGGER.error("Timeout creating memory bank in Hindsight")
            raise

    async def get_bank(self, bank_id: str) -> dict[str, Any]:
        """
        Get information about a memory bank.

        Args:
            bank_id: The memory bank identifier

        Returns:
            Response from the Hindsight API

        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v1/banks/{bank_id}"

        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            LOGGER.error("Error getting memory bank from Hindsight: %s", err)
            raise
        except TimeoutError:
            LOGGER.error("Timeout getting memory bank from Hindsight")
            raise


async def summarize_conversation(
    hass: Any,
    conversation_history: list[dict[str, Any]],
    ai_task_entity_id: str | None = None,
) -> str | None:
    """
    Summarize conversation history to extract facts and preferences.

    Args:
        hass: Home Assistant instance
        conversation_history: List of conversation messages
        ai_task_entity_id: Optional AI Task entity to use for summarization

    Returns:
        Summary text containing extracted facts and preferences, or None if failed

    """
    # Format conversation for summarization
    conversation_text = "\n\n".join(
        [
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in conversation_history
            if msg.get("content")
        ]
    )

    if not conversation_text.strip():
        LOGGER.debug("No conversation content to summarize")
        return None

    # Create summarization prompt
    summarization_prompt = f"""Analyze the following conversation and extract:
1. Any facts mentioned about users, preferences, or context
2. Any patterns in how the user communicates or what they prefer
3. Any important information that should be remembered for future conversations

Only include information that would be useful to remember long-term. Be concise.

Conversation:
{conversation_text}

Extract and format as a list of facts/preferences:"""

    try:
        # If specific AI Task entity provided, use it, otherwise find one
        if not ai_task_entity_id:
            # Find an available AI Task entity
            states = hass.states.async_all("ai_task")
            if not states:
                LOGGER.warning("No AI Task entity found for summarization")
                return None
            ai_task_entity_id = states[0].entity_id
            LOGGER.debug("Using AI Task entity: %s", ai_task_entity_id)

        # Call the AI Task service to generate summary
        result = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": ai_task_entity_id,
                "task": summarization_prompt,
            },
            blocking=True,
            return_response=True,
        )

        if result and isinstance(result, dict):
            summary = result.get("data", "")
            LOGGER.debug("Generated conversation summary: %s", summary)
            return summary

        return None

    except Exception:
        LOGGER.exception("Error summarizing conversation")
        return None


async def process_conversation_memory(
    hass: Any,
    hindsight_client: HindsightClient,
    bank_id: str,
    conversation_history: list[dict[str, Any]],
    conversation_id: str,
    ai_task_entity_id: str | None = None,
) -> None:
    """
    Process conversation and store memories in Hindsight.

    Args:
        hass: Home Assistant instance
        hindsight_client: Hindsight client instance
        bank_id: Memory bank identifier
        conversation_history: List of conversation messages
        conversation_id: Unique identifier for this conversation
        ai_task_entity_id: Optional AI Task entity to use for summarization

    """
    try:
        # Summarize the conversation
        summary = await summarize_conversation(
            hass, conversation_history, ai_task_entity_id
        )

        if not summary:
            LOGGER.debug("No summary generated, skipping Hindsight storage")
            return

        # Store in Hindsight with metadata
        metadata = {
            "conversation_id": conversation_id,
            "message_count": len(conversation_history),
            "source": "localchat_conversation",
        }

        await hindsight_client.retain(
            bank_id=bank_id,
            content=summary,
            metadata=metadata,
        )

        LOGGER.info(
            "Successfully stored conversation memory in Hindsight bank: %s", bank_id
        )

    except Exception:
        LOGGER.exception("Error processing conversation memory")
