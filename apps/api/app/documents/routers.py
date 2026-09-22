from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import SessionFactoryDep, require_csrf
from app.clinics.dependencies import MembershipDep
from app.documents.schemas import (
    TITLE_MAX_LENGTH,
    DocumentCategory,
    DocumentListParams,
    DocumentListResponse,
    DocumentResponse,
)
from app.documents.services import (
    DocumentService,
    content_disposition,
)
from app.platform.storage import ObjectStorage

router = APIRouter(
    prefix="/api/v1/clinics", tags=["documents"], dependencies=[Depends(require_csrf)]
)


def get_object_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage = request.app.state.object_storage
    return storage


StorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]


@router.get("/{clinic_id}/patients/{patient_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
    params: Annotated[DocumentListParams, Query()],
) -> DocumentListResponse:
    page = await DocumentService(session_factory, storage).list_documents(
        membership.context, membership.role, patient_id, params
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/patients/{patient_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Arquivo PDF, JPEG ou PNG de até 10 MB")],
    title: Annotated[str, Form(min_length=1, max_length=TITLE_MAX_LENGTH)],
    category: Annotated[DocumentCategory, Form()],
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> DocumentResponse:
    document = await DocumentService(session_factory, storage).upload_document(
        membership.context,
        membership.role,
        patient_id,
        category=category,
        title=title,
        upload=file,
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/{clinic_id}/patients/{patient_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
async def get_document(
    membership: MembershipDep,
    patient_id: UUID,
    document_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> DocumentResponse:
    document = await DocumentService(session_factory, storage).get_document(
        membership.context, membership.role, patient_id, document_id
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/{clinic_id}/patients/{patient_id}/documents/{document_id}/content",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Conteúdo privado do documento",
            "content": {
                "application/pdf": {},
                "image/jpeg": {},
                "image/png": {},
            },
        }
    },
)
async def get_document_content(
    membership: MembershipDep,
    patient_id: UUID,
    document_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> StreamingResponse:
    content = await DocumentService(session_factory, storage).open_content(
        membership.context, membership.role, patient_id, document_id
    )
    return StreamingResponse(
        content.chunks,
        media_type=content.document.detected_mime,
        headers={
            "Content-Disposition": content_disposition(content.document.original_filename),
        },
    )


@router.post(
    "/{clinic_id}/patients/{patient_id}/documents/{document_id}/archive",
    response_model=DocumentResponse,
)
async def archive_document(
    membership: MembershipDep,
    patient_id: UUID,
    document_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> DocumentResponse:
    document = await DocumentService(session_factory, storage).set_archived(
        membership.context, membership.role, patient_id, document_id, archived=True
    )
    return DocumentResponse.model_validate(document)


@router.post(
    "/{clinic_id}/patients/{patient_id}/documents/{document_id}/restore",
    response_model=DocumentResponse,
)
async def restore_document(
    membership: MembershipDep,
    patient_id: UUID,
    document_id: UUID,
    session_factory: SessionFactoryDep,
    storage: StorageDep,
) -> DocumentResponse:
    document = await DocumentService(session_factory, storage).set_archived(
        membership.context, membership.role, patient_id, document_id, archived=False
    )
    return DocumentResponse.model_validate(document)
