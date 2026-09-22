from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.anamnesis.schemas import (
    DETAILS_MAX_LENGTH,
    TEXT_MAX_LENGTH,
    AnamnesisCompletePayload,
    AnamnesisPayload,
)
from app.anamnesis.templates.cfo_2026_v1 import SECTIONS


def question_field_names(section_id: str) -> set[str]:
    section = next(candidate for candidate in SECTIONS if candidate.id == section_id)
    return {question.id.split(".", 1)[1] for question in section.questions}


def full_payload() -> dict[str, object]:
    payload: dict[str, object] = {}
    for section in SECTIONS:
        answers: dict[str, object] = {}
        for question in section.questions:
            short = question.id.split(".", 1)[1]
            match question.answer_type:
                case "TEXT":
                    answers[short] = {"text": f"Resposta {question.id}"}
                case "YES_NO_UNKNOWN":
                    answers[short] = {"value": "NO"}
                case "SINGLE_CHOICE":
                    answers[short] = {"value": question.options[0].id}
        payload[section.id] = answers
    return payload


def test_every_section_and_question_has_a_declared_field() -> None:
    for section in SECTIONS:
        draft_field = AnamnesisPayload.model_fields[section.id]
        assert draft_field.annotation is not None
        draft_section = draft_field.annotation.__args__[0]
        complete_field = AnamnesisCompletePayload.model_fields[section.id]
        assert complete_field.annotation is not None
        complete_section = complete_field.annotation
        for question in section.questions:
            short = question.id.split(".", 1)[1]
            assert short in draft_section.model_fields, question.id
            assert short in complete_section.model_fields, question.id


def test_draft_payload_accepts_a_partial_typed_answer() -> None:
    payload = AnamnesisPayload.model_validate(
        {
            "allergies": {
                "known_allergy": {"value": "YES", "details": "  Penicilina  "},
            },
            "chief_complaint": {"description": {"text": "  Dor no dente  "}},
        }
    )

    dumped = payload.model_dump(exclude_unset=True, exclude_none=True)
    assert dumped == {
        "allergies": {"known_allergy": {"value": "YES", "details": "Penicilina"}},
        "chief_complaint": {"description": {"text": "Dor no dente"}},
    }


def test_draft_payload_rejects_unknown_section_question_and_answer_keys() -> None:
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate({"unknown_section": {}})
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate({"allergies": {"unknown_question": {"value": "NO"}}})
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate({"allergies": {"known_allergy": {"value": "NO", "x": 1}}})


def test_draft_payload_rejects_invalid_option_and_wrong_answer_shape() -> None:
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate(
            {"dental_history": {"last_visit": {"value": "not_an_option"}}}
        )
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate({"dental_history": {"last_visit": {"text": "ontem"}}})
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate({"chief_complaint": {"description": {"value": "NO"}}})


def test_draft_payload_accepts_every_catalog_option() -> None:
    for section in SECTIONS:
        for question in section.questions:
            if question.answer_type != "SINGLE_CHOICE":
                continue
            for option in question.options:
                AnamnesisPayload.model_validate(
                    {section.id: {question.id.split(".")[1]: {"value": option.id}}}
                )


def test_payload_rejects_oversized_text_and_details() -> None:
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate(
            {"chief_complaint": {"description": {"text": "a" * (TEXT_MAX_LENGTH + 1)}}}
        )
    with pytest.raises(ValidationError):
        AnamnesisPayload.model_validate(
            {
                "allergies": {
                    "known_allergy": {"value": "YES", "details": "a" * (DETAILS_MAX_LENGTH + 1)}
                }
            }
        )


def test_complete_payload_requires_every_section_and_question() -> None:
    AnamnesisCompletePayload.model_validate(full_payload())

    with pytest.raises(ValidationError):
        AnamnesisCompletePayload.model_validate({})

    partial = full_payload()
    allergies = dict(partial["allergies"])  # type: ignore[arg-type]
    allergies.pop("emergency_care")
    partial["allergies"] = allergies
    with pytest.raises(ValidationError):
        AnamnesisCompletePayload.model_validate(partial)


def test_complete_payload_requires_details_for_positive_findings() -> None:
    payload = full_payload()
    payload["allergies"] = {  # type: ignore[dict-item]
        "known_allergy": {"value": "YES"},
        "emergency_care": {"value": "NO"},
    }
    with pytest.raises(ValidationError):
        AnamnesisCompletePayload.model_validate(payload)

    payload["allergies"] = {  # type: ignore[dict-item]
        "known_allergy": {"value": "YES", "details": "   "},
        "emergency_care": {"value": "NO"},
    }
    with pytest.raises(ValidationError):
        AnamnesisCompletePayload.model_validate(payload)

    payload["allergies"] = {  # type: ignore[dict-item]
        "known_allergy": {"value": "YES", "details": "Penicilina"},
        "emergency_care": {"value": "NO"},
    }
    AnamnesisCompletePayload.model_validate(payload)


def test_complete_payload_rejects_empty_text_answers() -> None:
    payload = full_payload()
    payload["chief_complaint"] = {  # type: ignore[dict-item]
        "description": {"text": "   "},
        "duration": {"text": "dois dias"},
        "evolution": {"text": "estável"},
    }
    with pytest.raises(ValidationError):
        AnamnesisCompletePayload.model_validate(payload)


def test_declared_question_short_names_are_unique_per_section() -> None:
    for section in SECTIONS:
        names = [question.id.split(".", 1)[1] for question in section.questions]
        assert len(names) == len(set(names)), section.id


def test_question_field_names_helper_matches_catalog_sections() -> None:
    for section in SECTIONS:
        assert question_field_names(section.id) == {
            question.id.split(".", 1)[1] for question in section.questions
        }
