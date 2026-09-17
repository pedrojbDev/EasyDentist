from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.auth.models import EmailOutbox
from app.auth.repositories.outbox_repository import EmailOutboxRepository, next_attempt_at

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def test_backoff_grows_exponentially() -> None:
    assert next_attempt_at(1, NOW) == NOW + timedelta(seconds=30)
    assert next_attempt_at(2, NOW) == NOW + timedelta(seconds=60)
    assert next_attempt_at(3, NOW) == NOW + timedelta(seconds=120)


def test_backoff_is_capped() -> None:
    assert next_attempt_at(20, NOW) == NOW + timedelta(hours=1)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)


def make_repository() -> tuple[EmailOutboxRepository, FakeSession]:
    session = FakeSession()
    return EmailOutboxRepository(session), session  # type: ignore[arg-type]


def make_outbox() -> EmailOutbox:
    outbox = EmailOutbox(
        idempotency_key="invitation:1",
        recipient="owner@example.com",
        template="invitation",
        payload={"subject": "Convite", "body": "Corpo"},
    )
    outbox.attempt_count = 0
    return outbox


def test_add_builds_outbox_row_with_payload() -> None:
    repository, session = make_repository()

    outbox = repository.add(
        idempotency_key="invitation:1",
        recipient="owner@example.com",
        template="invitation",
        subject="Convite",
        body="Corpo",
    )

    assert session.added == [outbox]
    assert outbox.idempotency_key == "invitation:1"
    assert outbox.recipient == "owner@example.com"
    assert outbox.template == "invitation"
    assert outbox.payload == {"subject": "Convite", "body": "Corpo"}


def test_mark_sent_sets_status_and_timestamp() -> None:
    repository, _ = make_repository()
    outbox = make_outbox()

    repository.mark_sent(outbox, now=NOW)

    assert outbox.status == "SENT"
    assert outbox.sent_at == NOW
    assert outbox.next_attempt_at is None
    assert outbox.updated_at == NOW


def test_mark_attempt_failed_schedules_retry() -> None:
    repository, _ = make_repository()
    outbox = make_outbox()

    repository.mark_attempt_failed(outbox, now=NOW)

    assert outbox.attempt_count == 1
    assert outbox.next_attempt_at == NOW + timedelta(seconds=30)
    assert outbox.status != "FAILED"


def test_mark_attempt_failed_gives_up_after_max_attempts() -> None:
    repository, _ = make_repository()
    outbox = make_outbox()
    outbox.attempt_count = 4

    repository.mark_attempt_failed(outbox, now=NOW)

    assert outbox.attempt_count == 5
    assert outbox.status == "FAILED"
    assert outbox.next_attempt_at is None
