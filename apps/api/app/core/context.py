from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: UUID
    clinic_id: UUID
