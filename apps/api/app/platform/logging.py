from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

SERVICE_NAME = "api"
LOGGER_NAME = "easydentist.api"
DEVELOPMENT = "development"

ALLOWED_CONTEXT_FIELDS = frozenset(
    {
        "request_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
        "error_type",
        "user_id",
        "clinic_id",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Serialises one allowlisted JSON event per line.

    Only the event name, the fixed metadata and allowlisted context fields are
    emitted: request bodies, cookies, tokens, query strings, e-mail addresses,
    raw IPs and exception messages never reach the output.
    """

    def __init__(self, environment: str) -> None:
        super().__init__()
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _timestamp(record.created),
            "service": SERVICE_NAME,
            "environment": self._environment,
            "level": record.levelname,
            "event": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            for key, value in context.items():
                if key in ALLOWED_CONTEXT_FIELDS:
                    payload[key] = value
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def _timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_logging(environment: str | None = None) -> None:
    resolved = (environment or os.environ.get("APP_ENV", DEVELOPMENT)).strip().lower()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter(resolved))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.disabled = True
    access_logger.propagate = False

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    get_logger().setLevel(logging.INFO)
