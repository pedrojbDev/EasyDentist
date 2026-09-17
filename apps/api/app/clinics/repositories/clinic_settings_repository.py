from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.models import ClinicSettings
from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches


class ClinicSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, context: TenantContext) -> ClinicSettings | None:
        ensure_context_matches(self._session, context)
        return await self._session.get(ClinicSettings, context.clinic_id)

    async def update(
        self,
        context: TenantContext,
        *,
        display_name: str | None = None,
        timezone: str | None = None,
        locale: str | None = None,
        currency: str | None = None,
    ) -> ClinicSettings | None:
        ensure_context_matches(self._session, context)
        settings = await self.get(context)
        if settings is None:
            return None
        if display_name is not None:
            settings.display_name = display_name
        if timezone is not None:
            settings.timezone = timezone
        if locale is not None:
            settings.locale = locale
        if currency is not None:
            settings.currency = currency
        settings.updated_at = datetime.now(UTC)
        await self._session.flush()
        return settings
