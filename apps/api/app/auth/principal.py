from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    session_id: UUID
    auth_method: str
