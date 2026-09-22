from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import PrincipalDep, SessionFactoryDep, require_csrf
from app.core.clock import utcnow
from app.core.context import UserContext
from app.core.tenancy import user_transaction
from app.users.repositories.professional_profile_repository import (
    ProfessionalProfileRepository,
)
from app.users.schemas import ProfessionalProfileRequest, ProfessionalProfileResponse

router = APIRouter(prefix="/api/v1/users", tags=["users"], dependencies=[Depends(require_csrf)])


@router.get("/me/professional-profile", response_model=ProfessionalProfileResponse | None)
async def get_my_professional_profile(
    principal: PrincipalDep,
    session_factory: SessionFactoryDep,
) -> ProfessionalProfileResponse | None:
    context = UserContext(user_id=principal.user_id)
    async with user_transaction(session_factory, context) as session:
        profile = await ProfessionalProfileRepository(session).get(context)
    if profile is None:
        return None
    return ProfessionalProfileResponse.model_validate(profile)


@router.put("/me/professional-profile", response_model=ProfessionalProfileResponse)
async def put_my_professional_profile(
    payload: ProfessionalProfileRequest,
    principal: PrincipalDep,
    session_factory: SessionFactoryDep,
) -> ProfessionalProfileResponse:
    context = UserContext(user_id=principal.user_id)
    async with user_transaction(session_factory, context) as session:
        profile = await ProfessionalProfileRepository(session).upsert(
            context,
            professional_name=payload.professional_name,
            cro_number=payload.cro_number,
            cro_state=payload.cro_state,
            updated_at=utcnow(),
        )
    return ProfessionalProfileResponse.model_validate(profile)
