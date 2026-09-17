from __future__ import annotations

from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.models import ClinicFeatureFlag
from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches


class FeatureKey(StrEnum):
    """Central typed registry of feature flags.

    The registry starts empty in M1.2 because no concrete use case exists yet.
    Every new key must be declared here; the default is always disabled, so
    enabling a flag requires an explicit operational row per clinic.
    """


class FeatureFlagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_row(self, context: TenantContext, key: str) -> ClinicFeatureFlag | None:
        ensure_context_matches(self._session, context)
        return await self._session.get(ClinicFeatureFlag, (context.clinic_id, key))


class FeatureFlagService:
    def __init__(self, repository: FeatureFlagRepository) -> None:
        self._repository = repository

    async def is_enabled(self, context: TenantContext, key: FeatureKey) -> bool:
        row = await self._repository.get_row(context, key.value)
        return row.enabled if row is not None else False
