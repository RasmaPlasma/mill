"""Redis Streams event bus for session-level streaming.

Each session gets its own Redis Stream (append-only log).
Background consumers append events via XADD; SSE endpoints read via XREAD.

Streams persist messages (unlike pub/sub fire-and-forget), so events
published before the SSE connects are still available. Each stream is
trimmed to ~1000 entries to prevent unbounded memory growth.

No in-memory fallback. If Redis is down, operations raise directly.
"""

import json
import logging
import os

import redis.asyncio as redis
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)


def _get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RedisStreamBus:
    """Redis Streams event bus for session-level streaming."""

    MAXLEN = 1000  # Approximate max entries per session stream

    def __init__(self):
        self._redis_url = _get_redis_url()
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            # socket_timeout=None is required for blocking commands like XREAD
            # with BLOCK > 0. redis-py async otherwise raises TimeoutError when
            # the socket read timeout fires before the blocking command returns.
            self._redis = redis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None
            )
        return self._redis

    def _stream_key(self, session_id: str) -> str:
        return f"session:{session_id}:events:stream"

    async def append(self, session_id: str, event: dict) -> str:
        """Append an event to the session's Redis Stream.

        Returns the generated stream entry ID.
        Raises if Redis is unreachable — no silent failure.
        """
        r = await self._get_redis()
        key = self._stream_key(session_id)
        payload = json.dumps(event, default=str)
        entry_id = await r.xadd(key, {"payload": payload}, maxlen=self.MAXLEN, approximate=True)
        return entry_id

    async def read(
        self,
        session_id: str,
        last_id: str = "$",
        block_ms: int = 100,
        count: int = 1,
    ) -> list[dict]:
        """Read events from the session's Redis Stream.

        Args:
            last_id: Start reading after this ID. Use "$" for only new messages,
                     "0" for all messages from the beginning.
            block_ms: Max time to block waiting for new messages (ms).
                      Use 0 for non-blocking.
            count: Max events to return in one call.

        Returns:
            List of event dicts, each with {id, type, data, run_id, timestamp}.
            Empty list if no new messages within block_ms.

        Raises:
            RedisTimeoutError: If block_ms expires with no message.
            ConnectionError: If Redis is unreachable.
        """
        r = await self._get_redis()
        key = self._stream_key(session_id)

        resp = await r.xread({key: last_id}, count=count, block=block_ms)
        events: list[dict] = []
        if resp:
            for _stream_name, entries in resp:
                for entry_id, fields in entries:
                    payload = fields.get("payload", "")
                    try:
                        event = json.loads(payload)
                        event["_stream_id"] = entry_id
                        events.append(event)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON in stream %s entry %s", key, entry_id)
        return events
