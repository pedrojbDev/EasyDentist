from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import check_spec, render_spec, write_spec


def test_render_spec_is_deterministic_and_covers_the_api() -> None:
    rendered = render_spec()

    spec = json.loads(rendered)
    assert spec["info"]["title"] == "EasyDentist API"
    assert "/api/v1/auth/login" in spec["paths"]
    assert "/api/v1/clinics/{clinic_id}" in spec["paths"]
    assert rendered.endswith("\n")
    assert rendered == render_spec()


def test_check_spec_detects_missing_and_stale_files(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    assert check_spec(target) is False

    write_spec(target)
    assert check_spec(target) is True

    target.write_text("{}\n", encoding="utf-8")
    assert check_spec(target) is False
