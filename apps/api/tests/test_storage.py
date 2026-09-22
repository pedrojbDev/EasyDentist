from __future__ import annotations

import hashlib
import io
from typing import BinaryIO

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from starlette.datastructures import UploadFile

from app.core.errors import (
    PayloadTooLargeError,
    StorageObjectNotFoundError,
    StorageUnavailableError,
    UnsupportedMediaTypeError,
)
from app.documents.services import (
    MAX_DOCUMENT_BYTES,
    content_disposition,
    detect_document_mime,
    sanitize_filename,
    stage_document,
)
from app.platform.s3_storage import READ_CHUNK_BYTES, S3ObjectStorage, StorageSettings

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 32
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
PLAIN_BYTES = b"nome do paciente: Maria Souza"

SECRET = "super-secret-access-key-must-not-leak"


def make_upload(data: bytes, filename: str = "documento.pdf") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


class FakeStreamingBody:
    def __init__(self, data: bytes, chunk_size: int = READ_CHUNK_BYTES) -> None:
        self._data = data
        self._chunk_size = chunk_size
        self._offset = 0
        self.closed = False

    def read(self, amount: int | None = None) -> bytes:
        size = self._chunk_size if amount is None else min(amount, self._chunk_size)
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


def not_found_error(code: str = "NoSuchKey") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "not found"}}, "GetObject")


class FakeS3Client:
    """In-memory stand-in for the boto3 S3 client; never touches the network."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[tuple[str, str, str, bytes]] = []
        self.deletes: list[tuple[str, str]] = []
        self.failure: Exception | None = None
        self.stream_chunk_size = READ_CHUNK_BYTES

    def _maybe_fail(self) -> None:
        if self.failure is not None:
            raise self.failure

    def upload_fileobj(
        self,
        file_object: BinaryIO,
        bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, str] | None = None,
    ) -> None:
        self._maybe_fail()
        payload = file_object.read()
        self.puts.append((bucket, key, (ExtraArgs or {}).get("ContentType", ""), payload))
        self.objects[(bucket, key)] = payload

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self._maybe_fail()
        payload = self.objects.get((Bucket, Key))
        if payload is None:
            raise not_found_error()
        return {"Body": FakeStreamingBody(payload, self.stream_chunk_size)}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self._maybe_fail()
        if (Bucket, Key) not in self.objects:
            raise not_found_error("404")
        return {}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self._maybe_fail()
        self.deletes.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def fake_client() -> FakeS3Client:
    return FakeS3Client()


@pytest.fixture
def storage(fake_client: FakeS3Client) -> S3ObjectStorage:
    return S3ObjectStorage(fake_client, bucket="easydentist", key_prefix="test-documents/run-1/")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_development_defaults() -> None:
    settings = StorageSettings.from_environment({})

    assert settings.endpoint_url == "http://127.0.0.1:9000"
    assert settings.bucket == "easydentist"
    assert settings.region == "us-east-1"
    assert settings.access_key == "easydentist"
    assert settings.key_prefix == ""


def test_settings_production_requires_endpoint_and_credentials() -> None:
    with pytest.raises(RuntimeError, match="S3_ENDPOINT_URL"):
        StorageSettings.from_environment({"APP_ENV": "production"})

    with pytest.raises(RuntimeError) as error:
        StorageSettings.from_environment(
            {
                "APP_ENV": "production",
                "S3_ENDPOINT_URL": "https://s3.example.test",
                "S3_ACCESS_KEY": "access",
            }
        )
    assert SECRET not in str(error.value)
    assert "access" not in str(error.value)


def test_settings_reads_environment_and_normalizes_prefix() -> None:
    settings = StorageSettings.from_environment(
        {
            "APP_ENV": "production",
            "S3_ENDPOINT_URL": "https://s3.example.test",
            "S3_ACCESS_KEY": "access",
            "S3_SECRET_KEY": SECRET,
            "S3_BUCKET": "bucket-name",
            "S3_REGION": "sa-east-1",
            "S3_KEY_PREFIX": "test-documents/abc",
        }
    )

    assert settings.endpoint_url == "https://s3.example.test"
    assert settings.bucket == "bucket-name"
    assert settings.region == "sa-east-1"
    assert settings.access_key == "access"
    assert settings.secret_key == SECRET
    assert settings.key_prefix == "test-documents/abc/"


# ---------------------------------------------------------------------------
# S3 adapter (fake client, no network)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_put_uses_prefixed_key_and_content_type(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    await storage.put("opaque-key", io.BytesIO(PDF_BYTES), content_type="application/pdf")

    assert fake_client.puts == [
        ("easydentist", "test-documents/run-1/opaque-key", "application/pdf", PDF_BYTES)
    ]


@pytest.mark.anyio
async def test_stream_returns_the_stored_bytes_in_chunks(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    payload = b"x" * (2 * READ_CHUNK_BYTES + 17)
    await storage.put("opaque-key", io.BytesIO(payload), content_type="application/pdf")
    fake_client.stream_chunk_size = 4096

    chunks = [chunk async for chunk in await storage.stream("opaque-key")]

    assert len(chunks) > 1
    assert b"".join(chunks) == payload


@pytest.mark.anyio
async def test_stream_missing_object_maps_to_not_found(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    with pytest.raises(StorageObjectNotFoundError):
        await storage.stream("missing-key")


@pytest.mark.anyio
async def test_verify_reports_existence_without_raising(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    assert await storage.verify("missing-key") is False

    await storage.put("present-key", io.BytesIO(PNG_BYTES), content_type="image/png")

    assert await storage.verify("present-key") is True


@pytest.mark.anyio
async def test_delete_removes_the_prefixed_object(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    await storage.put("opaque-key", io.BytesIO(PDF_BYTES), content_type="application/pdf")

    await storage.delete("opaque-key")

    assert fake_client.deletes == [("easydentist", "test-documents/run-1/opaque-key")]
    assert await storage.verify("opaque-key") is False


@pytest.mark.anyio
async def test_backend_failures_are_wrapped_without_leaking_credentials(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    fake_client.failure = EndpointConnectionError(
        endpoint_url=f"http://127.0.0.1:9000/?X-Amz-Credential={SECRET}"
    )

    with pytest.raises(StorageUnavailableError) as error:
        await storage.put("opaque-key", io.BytesIO(PDF_BYTES), content_type="application/pdf")

    assert SECRET not in str(error.value)
    assert error.value.__cause__ is None

    with pytest.raises(StorageUnavailableError):
        await storage.delete("opaque-key")


@pytest.mark.anyio
async def test_client_errors_are_wrapped_as_unavailable(
    storage: S3ObjectStorage, fake_client: FakeS3Client
) -> None:
    fake_client.failure = ClientError(
        {"Error": {"Code": "InternalError", "Message": "backend exploded"}}, "PutObject"
    )

    with pytest.raises(StorageUnavailableError):
        await storage.put("opaque-key", io.BytesIO(PDF_BYTES), content_type="application/pdf")

    with pytest.raises(StorageUnavailableError):
        await storage.verify("opaque-key")


# ---------------------------------------------------------------------------
# Magic bytes and staging
# ---------------------------------------------------------------------------


def test_detect_document_mime_accepts_only_pdf_jpeg_png() -> None:
    assert detect_document_mime(PDF_BYTES) == "application/pdf"
    assert detect_document_mime(JPEG_BYTES) == "image/jpeg"
    assert detect_document_mime(PNG_BYTES) == "image/png"


def test_detect_document_mime_rejects_empty_truncated_and_unknown() -> None:
    assert detect_document_mime(b"") is None
    assert detect_document_mime(b"%PD") is None
    assert detect_document_mime(b"\xff\xd8") is None
    assert detect_document_mime(PLAIN_BYTES) is None


@pytest.mark.anyio
async def test_stage_document_reports_size_hash_and_detected_mime() -> None:
    staged = await stage_document(make_upload(PDF_BYTES, "laudo.pdf"))

    assert staged.mime == "application/pdf"
    assert staged.size_bytes == len(PDF_BYTES)
    assert staged.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert staged.file_object.read() == PDF_BYTES
    staged.file_object.close()


@pytest.mark.anyio
async def test_stage_document_accepts_exactly_ten_megabytes() -> None:
    payload = b"\xff\xd8\xff" + b"a" * (MAX_DOCUMENT_BYTES - 3)

    staged = await stage_document(make_upload(payload, "foto.jpg"))

    assert staged.mime == "image/jpeg"
    assert staged.size_bytes == MAX_DOCUMENT_BYTES
    staged.file_object.close()


@pytest.mark.anyio
async def test_stage_document_rejects_more_than_ten_megabytes() -> None:
    payload = b"%PDF-" + b"a" * (MAX_DOCUMENT_BYTES - 3)

    with pytest.raises(PayloadTooLargeError):
        await stage_document(make_upload(payload, "grande.pdf"))


@pytest.mark.anyio
async def test_stage_document_rejects_empty_file() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        await stage_document(make_upload(b"", "vazio.pdf"))


@pytest.mark.anyio
async def test_stage_document_rejects_forged_magic_bytes_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        await stage_document(make_upload(PLAIN_BYTES, "disfarcado.pdf"))


def test_sanitize_filename_keeps_only_a_safe_basename() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\pasta\\laudo.pdf") == "laudo.pdf"
    assert sanitize_filename('laudo"quebrado\r\n.pdf') == "laudoquebrado.pdf"
    assert sanitize_filename("   ") == "documento"
    assert sanitize_filename(None) == "documento"
    assert len(sanitize_filename("a" * 400)) == 255


def test_content_disposition_is_an_attachment_with_encoded_filename() -> None:
    header = content_disposition("laudo çãó.pdf")

    assert header.startswith('attachment; filename="laudo____.pdf"')
    assert "filename*=UTF-8''laudo%20%C3%A7%C3%A3%C3%B3.pdf" in header
    assert "\r" not in header and "\n" not in header
