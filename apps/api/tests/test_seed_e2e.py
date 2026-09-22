from __future__ import annotations

from pathlib import Path

import pytest

from scripts import seed_e2e

MIGRATION_URL = "postgresql+asyncpg://migrator:secret@db:5432/easydentist"

INVALID_RUN_IDS = (
    "%",
    "_",
    "/",
    "e2e-%",
    "e2e-0123456789ab",
    "E2E-0123456789AB",
    "0123456789a",
    "0123456789abc",
    "0123456789ag",
    "zzzzzzzzzzzz",
    "01234567 89ab",
)


def _forbid_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("create_async_engine must not be called")

    monkeypatch.setattr(seed_e2e, "create_async_engine", fail)


def _forbid_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("storage cleanup must not be called")

    monkeypatch.setattr(seed_e2e, "_delete_run_objects", fail)


@pytest.mark.parametrize("run_id", INVALID_RUN_IDS)
def test_cleanup_rejects_invalid_run_id_before_database_or_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, run_id: str
) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATION_URL)
    _forbid_database(monkeypatch)
    _forbid_storage(monkeypatch)

    with pytest.raises(SystemExit):
        seed_e2e.main(["--cleanup", "--run-id", run_id, "--manifest", str(tmp_path / "none")])


@pytest.mark.parametrize("run_id", INVALID_RUN_IDS)
def test_seed_rejects_invalid_run_id_before_database(
    monkeypatch: pytest.MonkeyPatch, run_id: str
) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATION_URL)
    _forbid_database(monkeypatch)
    _forbid_storage(monkeypatch)

    with pytest.raises(SystemExit):
        seed_e2e.main(["--run-id", run_id])


@pytest.mark.parametrize("run_id", ("", "e2e-"))
def test_cleanup_requires_a_run_id_when_the_manifest_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, run_id: str
) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATION_URL)
    _forbid_database(monkeypatch)
    _forbid_storage(monkeypatch)

    with pytest.raises(SystemExit):
        seed_e2e.main(["--cleanup", "--run-id", run_id, "--manifest", str(tmp_path / "none")])


def test_cleanup_rejects_a_manifest_with_an_out_of_format_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATION_URL)
    _forbid_database(monkeypatch)
    _forbid_storage(monkeypatch)
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"run_id": "e2e-%"}', encoding="utf-8")

    with pytest.raises(SystemExit):
        seed_e2e.main(["--cleanup", "--manifest", str(manifest)])


def test_validate_run_id_accepts_the_generated_format() -> None:
    run_id = seed_e2e._new_run_id()

    assert seed_e2e._validate_run_id(run_id) == run_id
    assert seed_e2e._validate_run_id("0123456789ab") == "0123456789ab"


@pytest.mark.parametrize("run_id", INVALID_RUN_IDS)
def test_validate_run_id_rejects_out_of_format_values(run_id: str) -> None:
    with pytest.raises(SystemExit):
        seed_e2e._validate_run_id(run_id)
