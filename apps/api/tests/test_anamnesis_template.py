from __future__ import annotations

import dataclasses

import pytest

from app.anamnesis.templates.cfo_2026_v1 import (
    SECTIONS,
    TEMPLATE_ID,
    AnswerType,
    Option,
    Question,
    Section,
    YesNoUnknown,
)

APPROVED_SECTION_IDS = (
    "chief_complaint",
    "current_history",
    "medical_history",
    "dental_history",
    "family_history",
    "social_history",
    "digestive_conditions",
    "hepatic_conditions",
    "cardiovascular_conditions",
    "respiratory_conditions",
    "renal_conditions",
    "motor_conditions",
    "infectious_conditions",
    "endocrine_metabolic_conditions",
    "allergies",
    "anesthesia",
    "bleeding",
    "healing",
    "surgeries",
    "pregnancy",
    "neoplasms",
    "psychological_conditions",
    "disabilities",
    "medications",
    "habits",
    "dental_inventory",
)

APPROVED_DENTAL_INVENTORY_TOPICS = (
    "dental_inventory.hygiene",
    "dental_inventory.flossing",
    "dental_inventory.pain",
    "dental_inventory.bleeding",
    "dental_inventory.mobility",
    "dental_inventory.halitosis",
    "dental_inventory.xerostomia",
    "dental_inventory.atm",
    "dental_inventory.sensitivity",
    "dental_inventory.lesions",
    "dental_inventory.bruxism",
    "dental_inventory.diet",
    "dental_inventory.endodontics",
    "dental_inventory.prostheses",
    "dental_inventory.previous_surgeries",
)


def _questions() -> list[Question]:
    return [question for section in SECTIONS for question in section.questions]


def test_template_id_is_the_fixed_version() -> None:
    assert TEMPLATE_ID == "cfo_2026_v1"


def test_yes_no_unknown_vocabulary_is_fixed() -> None:
    assert tuple(YesNoUnknown) == ("YES", "NO", "UNKNOWN")


def test_approved_sections_are_present_in_deterministic_order() -> None:
    assert tuple(section.id for section in SECTIONS) == APPROVED_SECTION_IDS


def test_section_ids_are_unique() -> None:
    section_ids = [section.id for section in SECTIONS]
    assert len(section_ids) == len(set(section_ids))


def test_question_ids_are_unique() -> None:
    question_ids = [question.id for question in _questions()]
    assert len(question_ids) == len(set(question_ids))


def test_question_ids_are_namespaced_by_their_section() -> None:
    for section in SECTIONS:
        assert section.questions, f"section {section.id} has no questions"
        for question in section.questions:
            assert question.id.startswith(f"{section.id}.")


def test_every_question_has_a_prompt() -> None:
    for question in _questions():
        assert question.prompt.strip()


def test_yes_no_unknown_questions_do_not_declare_options() -> None:
    for question in _questions():
        if question.answer_type is AnswerType.YES_NO_UNKNOWN:
            assert question.options == ()


def test_single_choice_questions_declare_options_with_unique_ids() -> None:
    for question in _questions():
        if question.answer_type is not AnswerType.SINGLE_CHOICE:
            continue
        option_ids = [option.id for option in question.options]
        assert option_ids, f"question {question.id} has no options"
        assert len(option_ids) == len(set(option_ids))
        for option in question.options:
            assert option.label.strip()


def test_text_questions_do_not_declare_options_or_details() -> None:
    for question in _questions():
        if question.answer_type is AnswerType.TEXT:
            assert question.options == ()
            assert question.details_prompt is None
            assert question.details_required is False


def test_required_details_declare_a_prompt() -> None:
    for question in _questions():
        if question.details_required:
            assert question.details_prompt
        if question.details_prompt is not None:
            assert question.details_prompt.strip()


def test_dental_inventory_covers_the_approved_topics() -> None:
    inventory = next(section for section in SECTIONS if section.id == "dental_inventory")
    inventory_ids = {question.id for question in inventory.questions}
    assert set(APPROVED_DENTAL_INVENTORY_TOPICS) <= inventory_ids


def test_catalog_is_immutable() -> None:
    assert isinstance(SECTIONS, tuple)
    for section in SECTIONS:
        assert isinstance(section, Section)
        assert isinstance(section.questions, tuple)
        for question in section.questions:
            assert isinstance(question, Question)
            assert isinstance(question.options, tuple)
            for option in question.options:
                assert isinstance(option, Option)

    with pytest.raises(dataclasses.FrozenInstanceError):
        SECTIONS[0].id = "changed"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _questions()[0].prompt = "changed"  # type: ignore[misc]
