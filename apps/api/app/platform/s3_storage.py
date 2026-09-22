"""S3-compatible adapter for the private document bucket.

The adapter keeps boto3 behind a small protocol, wraps every backend failure in
domain errors with static messages (credentials, endpoints and keys never reach
the caller or the logs) and runs the blocking boto3 calls in worker threads so
the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import BinaryIO, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.errors import StorageObjectNotFoundError, StorageUnavailableError
from app.platform.logging import get_logger

DEVELOPMENT = "development"
DEFAULT_ENDPOINT_URL = "http://127.0.0.1:9000"
DEFAULT_ACCESS_KEY = "easydentist"
DEFAULT_SECRET_KEY = "easydentist-local-only"
DEFAULT_BUCKET = "easydentist"
DEFAULT_REGION = "us-east-1"
READ_CHUNK_BYTES = 1024 * 1024
NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NoSuchVersion"})

_logger = get_logger()


@dataclass(frozen=True, slots=True)
class StorageSettings:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    key_prefix: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> StorageSettings:
        """Load storage settings, failing fast in production.

        Development falls back to the local Compose SeaweedFS endpoint; a
        production boot without endpoint or credentials raises before serving.
        The error message never echoes the supplied values.
        """

        values = os.environ if environment is None else environment
        app_env = values.get("APP_ENV", DEVELOPMENT).strip().lower()
        production = app_env == "production"

        endpoint_url = values.get("S3_ENDPOINT_URL", "").strip()
        access_key = values.get("S3_ACCESS_KEY", "").strip()
        secret_key = values.get("S3_SECRET_KEY", "").strip()

        if production and (not endpoint_url or not access_key or not secret_key):
            raise RuntimeError(
                "S3_ENDPOINT_URL, S3_ACCESS_KEY and S3_SECRET_KEY are required in production"
            )

        if not endpoint_url:
            endpoint_url = DEFAULT_ENDPOINT_URL
        if not access_key:
            access_key = DEFAULT_ACCESS_KEY
        if not secret_key:
            secret_key = DEFAULT_SECRET_KEY

        prefix = values.get("S3_KEY_PREFIX", "").strip().strip("/")
        key_prefix = f"{prefix}/" if prefix else ""

        return cls(
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
            bucket=values.get("S3_BUCKET", DEFAULT_BUCKET).strip() or DEFAULT_BUCKET,
            region=values.get("S3_REGION", DEFAULT_REGION).strip() or DEFAULT_REGION,
            key_prefix=key_prefix,
        )


class S3Client(Protocol):
    """The subset of the boto3 S3 client the adapter relies on."""

    def upload_fileobj(
        self,
        file_object: BinaryIO,
        bucket: str,
        key: str,
        *,
        ExtraArgs: Mapping[str, str] | None = ...,
    ) -> None: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def delete_object(self, *, Bucket: str, Key: str) -> None: ...


class S3Body(Protocol):
    """The streaming body returned by boto3 ``get_object``."""

    def read(self, amount: int | None = ...) -> bytes: ...

    def close(self) -> None: ...


def _unavailable(operation: str, error: Exception) -> StorageUnavailableError:
    _logger.error(
        f"storage.{operation}_failed",
        extra={"context": {"error_type": type(error).__name__}},
    )
    return StorageUnavailableError("storage is unavailable")


def _is_not_found(error: ClientError) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in NOT_FOUND_CODES


async def _read_chunks(body: S3Body) -> AsyncIterator[bytes]:
    try:
        while True:
            chunk = await asyncio.to_thread(body.read, READ_CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(body.close)


class S3ObjectStorage:
    """ObjectStorage implementation backed by an S3-compatible bucket."""

    def __init__(self, client: S3Client, *, bucket: str, key_prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._key_prefix = key_prefix

    def _object_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    async def put(self, key: str, file_object: BinaryIO, *, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.upload_fileobj,
                file_object,
                self._bucket,
                self._object_key(key),
                ExtraArgs={"ContentType": content_type},
            )
        except (BotoCoreError, ClientError) as error:
            raise _unavailable("put", error) from None

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=self._object_key(key)
            )
        except ClientError as error:
            if _is_not_found(error):
                raise StorageObjectNotFoundError("object not found") from None
            raise _unavailable("stream", error) from None
        except BotoCoreError as error:
            raise _unavailable("stream", error) from None
        return _read_chunks(cast(S3Body, response["Body"]))

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete_object, Bucket=self._bucket, Key=self._object_key(key)
            )
        except (BotoCoreError, ClientError) as error:
            raise _unavailable("delete", error) from None

    async def verify(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=self._object_key(key)
            )
        except ClientError as error:
            if _is_not_found(error):
                return False
            raise _unavailable("verify", error) from None
        except BotoCoreError as error:
            raise _unavailable("verify", error) from None
        return True


def create_s3_storage(settings: StorageSettings) -> S3ObjectStorage:
    """Build the production adapter; no network call happens here."""

    client = cast(
        S3Client,
        boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        ),
    )
    return S3ObjectStorage(
        client,
        bucket=settings.bucket,
        key_prefix=settings.key_prefix,
    )
