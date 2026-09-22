"""Typed schemas for the versioned anamnesis of the ``cfo_2026_v1`` template.

Every section and question of the immutable catalog gets an explicit Pydantic
field: section IDs name the payload sections, question IDs (short name after
the dot) name the answer fields, and ``extra="forbid"`` rejects anything the
catalog does not declare. Drafts accept partial and incomplete answers;
``AnamnesisCompletePayload`` is the stricter gate used by finalization and
requires every question plus the mandatory textual complements of positive
findings.

The models are generated from ``SECTIONS`` so the catalog remains the single
source of clinical IDs; hand-written IDs would drift from it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Final, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    create_model,
    field_validator,
    model_validator,
)

from app.anamnesis.templates.cfo_2026_v1 import (
    SECTIONS,
    AnswerType,
    Question,
    Section,
    YesNoUnknown,
)

TEXT_MAX_LENGTH: Final[int] = 4000
DETAILS_MAX_LENGTH: Final[int] = 2000


class AnamnesisStatus(StrEnum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_text(value: str) -> str:
    return value.strip()


class TextAnswer(BaseModel):
    """Free-text answer accepted while the anamnesis is a draft."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=TEXT_MAX_LENGTH)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return _clean_text(value)


class CompleteTextAnswer(BaseModel):
    """Free-text answer required by a finalized anamnesis."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=TEXT_MAX_LENGTH)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if not cleaned:
            raise ValueError("text is required")
        return cleaned


class YesNoUnknownAnswer(BaseModel):
    """Answer of a closed ``YES/NO/UNKNOWN`` question."""

    model_config = ConfigDict(extra="forbid")

    value: YesNoUnknown
    details: str | None = Field(default=None, max_length=DETAILS_MAX_LENGTH)

    @field_validator("details")
    @classmethod
    def clean_details(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class YesNoUnknownAnswerWithDetails(YesNoUnknownAnswer):
    """Answer whose textual complement is mandatory for a positive finding."""

    @model_validator(mode="after")
    def require_details(self) -> YesNoUnknownAnswerWithDetails:
        if self.value == YesNoUnknown.YES and not self.details:
            raise ValueError("details are required for a positive answer")
        return self


def _single_choice_answer_model(question: Question) -> type[BaseModel]:
    enum_name = f"{_pascal_case(question.id)}Option"
    option_enum = StrEnum(enum_name, {option.id: option.id for option in question.options})  # type: ignore[misc]
    return create_model(
        f"{_pascal_case(question.id)}Answer",
        __config__=ConfigDict(extra="forbid"),
        value=(option_enum, ...),
    )


def _complete_yes_no_answer_model(question: Question) -> type[BaseModel]:
    if not question.details_required:
        return YesNoUnknownAnswer
    return YesNoUnknownAnswerWithDetails


def _draft_answer_model(question: Question) -> type[BaseModel]:
    if question.answer_type == AnswerType.TEXT:
        return TextAnswer
    if question.answer_type == AnswerType.YES_NO_UNKNOWN:
        return YesNoUnknownAnswer
    return _SINGLE_CHOICE_MODELS[question.id]


def _complete_answer_model(question: Question) -> type[BaseModel]:
    if question.answer_type == AnswerType.TEXT:
        return CompleteTextAnswer
    if question.answer_type == AnswerType.YES_NO_UNKNOWN:
        return _COMPLETE_YES_NO_MODELS[question.id]
    return _SINGLE_CHOICE_MODELS[question.id]


_SINGLE_CHOICE_MODELS: dict[str, type[BaseModel]] = {
    question.id: _single_choice_answer_model(question)
    for section in SECTIONS
    for question in section.questions
    if question.answer_type == AnswerType.SINGLE_CHOICE
}

_COMPLETE_YES_NO_MODELS: dict[str, type[BaseModel]] = {
    question.id: _complete_yes_no_answer_model(question)
    for section in SECTIONS
    for question in section.questions
    if question.answer_type == AnswerType.YES_NO_UNKNOWN
}


def question_field_name(question: Question) -> str:
    """Short payload field of a catalog question (the part after the dot)."""

    return question.id.split(".", 1)[1]


def _build_section_model(section: Section, *, complete: bool) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for question in section.questions:
        name = question_field_name(question)
        answer_model = (
            _complete_answer_model(question) if complete else _draft_answer_model(question)
        )
        fields[name] = (answer_model, ...) if complete else (answer_model | None, None)
    return create_model(
        f"{_pascal_case(section.id)}Payload",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


_DRAFT_SECTION_MODELS: dict[str, type[BaseModel]] = {
    section.id: _build_section_model(section, complete=False) for section in SECTIONS
}
_COMPLETE_SECTION_MODELS: dict[str, type[BaseModel]] = {
    section.id: _build_section_model(section, complete=True) for section in SECTIONS
}

_DRAFT_PAYLOAD_FIELDS: dict[str, Any] = {
    section.id: (_DRAFT_SECTION_MODELS[section.id] | None, None) for section in SECTIONS
}
_COMPLETE_PAYLOAD_FIELDS: dict[str, Any] = {
    section.id: (_COMPLETE_SECTION_MODELS[section.id], ...) for section in SECTIONS
}

AnamnesisPayload: type[BaseModel] = create_model(
    "AnamnesisPayload",
    __config__=ConfigDict(extra="forbid"),
    **_DRAFT_PAYLOAD_FIELDS,
)

AnamnesisCompletePayload: type[BaseModel] = create_model(
    "AnamnesisCompletePayload",
    __config__=ConfigDict(extra="forbid"),
    **_COMPLETE_PAYLOAD_FIELDS,
)

SerializedAnamnesisPayload = Annotated[
    AnamnesisPayload,  # type: ignore[valid-type]
    PlainSerializer(
        lambda payload: payload.model_dump(exclude_none=True),
        return_type=dict[str, Any],
    ),
]


def merge_payload(stored: Mapping[str, object], update: Mapping[str, object]) -> dict[str, object]:
    """Apply a partial payload over the stored one, section by section.

    Only questions explicitly present in ``update`` are touched; ``None``
    removes the answer, and an explicitly null section removes the section.
    """

    merged: dict[str, object] = {
        section_id: dict(answers)
        for section_id, answers in stored.items()
        if isinstance(answers, Mapping)
    }
    for section_id, section_update in update.items():
        if section_update is None:
            merged.pop(section_id, None)
            continue
        if not isinstance(section_update, Mapping):
            continue
        current = merged.get(section_id)
        answers: dict[str, object] = dict(current) if isinstance(current, Mapping) else {}
        for question_name, answer in section_update.items():
            if answer is None:
                answers.pop(question_name, None)
            else:
                answers[question_name] = answer
        if answers:
            merged[section_id] = answers
        else:
            merged.pop(section_id, None)
    return merged


def payload_updates(payload: object) -> dict[str, object]:
    """Extract only the explicitly provided fields of a validated payload."""

    return cast(BaseModel, payload).model_dump(exclude_unset=True)


class AnamnesisCreateRequest(BaseModel):
    """Starts an empty draft or a revision copied from a final version."""

    model_config = ConfigDict(extra="forbid")

    base_version_id: UUID | None = None


class AnamnesisUpdateRequest(BaseModel):
    """Partial payload update of a draft."""

    model_config = ConfigDict(extra="forbid")

    payload: AnamnesisPayload  # type: ignore[valid-type]


class AnamnesisListParams(BaseModel):
    status: AnamnesisStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AnamnesisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    status: AnamnesisStatus
    version_number: int | None
    template: str
    payload: SerializedAnamnesisPayload
    base_version_id: UUID | None
    author_user_id: UUID
    author_professional_name: str | None
    author_cro_number: str | None
    author_cro_state: str | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AnamnesisListResponse(BaseModel):
    items: list[AnamnesisResponse]
    total: int
    limit: int
    offset: int
