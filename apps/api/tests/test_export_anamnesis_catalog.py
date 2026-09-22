from __future__ import annotations

import json
from pathlib import Path

from scripts.export_anamnesis_catalog import (
    DEFAULT_PATH,
    check_catalog,
    render_catalog,
    write_catalog,
)


def test_render_catalog_is_deterministic_and_covers_the_template() -> None:
    rendered = render_catalog()

    catalog = json.loads(rendered)
    assert catalog["template_id"] == "cfo_2026_v1"
    assert len(catalog["sections"]) >= 20
    question_ids = [
        question["id"] for section in catalog["sections"] for question in section["questions"]
    ]
    assert len(question_ids) == len(set(question_ids))
    assert "allergies.known_allergy" in question_ids
    assert rendered.endswith("\n")
    assert rendered == render_catalog()


def test_check_catalog_detects_missing_and_stale_files(tmp_path: Path) -> None:
    target = tmp_path / "catalog.json"

    assert check_catalog(target) is False

    write_catalog(target)
    assert check_catalog(target) is True

    target.write_text("{}\n", encoding="utf-8")
    assert check_catalog(target) is False


def test_committed_web_catalog_matches_the_python_template() -> None:
    assert check_catalog(DEFAULT_PATH) is True
