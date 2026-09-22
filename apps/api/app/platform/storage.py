"""Private object storage port used by the documents module.

Adapters must never leak backend credentials, endpoints or object keys through
errors or logs: failures surface as the domain errors declared in
``app.core.errors`` with static messages.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import BinaryIO, Protocol


class ObjectStorage(Protocol):
    """Minimal private bucket contract: put, stream, delete and verify."""

    async def put(self, key: str, file_object: BinaryIO, *, content_type: str) -> None:
        """Store ``file_object`` under ``key``; raises StorageUnavailableError."""
        ...

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        """Open ``key`` and return a chunk iterator.

        Missing objects raise StorageObjectNotFoundError before any byte is
        produced, so callers can fail closed before starting a response.
        """
        ...

    async def delete(self, key: str) -> None:
        """Best-effort removal used to compensate failed metadata writes."""
        ...

    async def verify(self, key: str) -> bool:
        """Report whether ``key`` exists; backend failures raise."""
        ...
