"""Storage abstraction: business logic depends on StorageBackend, never boto3.

Local filesystem for development/tests, Neon Object Storage (S3-compatible,
via boto3) for production. Selection comes from Settings; the database stores
only the opaque storage key, never absolute paths or credentials.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger("app.storage")


class StorageError(Exception):
    """Raised for storage failures. Treated as *transient* by the pipeline
    (network/service blips) unless the backend reports a missing object."""


class ObjectNotFoundError(StorageError):
    """The key does not exist — permanent for a processing run."""


class StorageBackend(Protocol):
    def save(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str: ...
    def load(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def url_for(self, key: str) -> str: ...


def _check_key(key: str) -> str:
    """Reject anything that is not a tight relative object key.

    Keys are always generated server-side (see app.documents.keys), but defense
    in depth: no absolute paths, no parent traversal, no control characters.
    """
    if not key or not isinstance(key, str):
        raise StorageError("Invalid storage key.")
    if (
        key.startswith("/")
        or ".." in key.split("/")
        or "\\" in key
        or any(ord(c) < 32 for c in key)
    ):
        raise StorageError(f"Rejected unsafe storage key: {key!r}")
    if len(key) > 512:
        raise StorageError("Storage key too long.")
    return key


class LocalStorage(StorageBackend):
    def __init__(self, root: str = "./storage") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._resolved_root = self.root.resolve()

    def _path(self, key: str) -> Path:
        _check_key(key)
        # Belt and suspenders: resolve and confirm containment after _check_key.
        candidate = (self._resolved_root / key).resolve()
        if candidate != self._resolved_root and self._resolved_root not in candidate.parents:
            raise StorageError(f"Storage key escapes root: {key!r}")
        return candidate

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        try:
            p = self._path(key)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        except StorageError:
            raise
        except OSError as e:
            raise StorageError(f"Local write failed for {key!r}: {e}") from e
        return key

    def load(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except StorageError:
            raise
        except FileNotFoundError as e:
            raise ObjectNotFoundError(f"Object not found: {key!r}") from e
        except OSError as e:
            raise StorageError(f"Local read failed for {key!r}: {e}") from e

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except StorageError:
            raise
        except OSError as e:
            raise StorageError(f"Local delete failed for {key!r}: {e}") from e

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except StorageError:
            return False

    def url_for(self, key: str) -> str:
        return f"local://{key}"


class NeonObjectStorage(StorageBackend):
    """Neon Object Storage via the S3-compatible API. Constructed only when the
    ``neon`` backend is selected *and* endpoint/credentials are present;
    otherwise raises a clear error instead of failing obscurely inside boto3.

    The endpoint is always explicit (copied from the Neon console) — no
    provider-specific URL is ever derived here."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        region: str = "",
    ) -> None:
        if not all([endpoint, access_key_id, secret_access_key, bucket_name]):
            raise StorageError(
                "Neon Object Storage selected but endpoint/credentials/bucket are not configured."
            )
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as e:  # pragma: no cover - boto3 is a hard dependency
            raise StorageError(f"boto3 is required for Neon Object Storage: {e}") from e
        self._ClientError = ClientError
        self._BotoCoreError = BotoCoreError
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        self._bucket = bucket_name

    def _wrap(self, action: str, key: str, error: Exception) -> StorageError:
        if isinstance(error, self._ClientError):
            code = error.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "NotFound", "404"):
                return ObjectNotFoundError(f"Object not found: {key!r}")
            # 5xx / request timeouts / throttling are transient; 4xx are not.
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if isinstance(status, int) and 500 <= status < 600:
                return StorageError(f"Neon storage {action} transient failure for {key!r}: {error}")
            return StorageError(f"Neon storage {action} failed for {key!r}: {error}")
        return StorageError(f"Neon storage {action} failed for {key!r}: {error}")

    def save(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        _check_key(key)
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as e:  # noqa: BLE001 - normalized by _wrap
            raise self._wrap("upload", key, e) from e
        return key

    def load(self, key: str) -> bytes:
        _check_key(key)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read()
        except Exception as e:  # noqa: BLE001 - normalized by _wrap
            raise self._wrap("download", key, e) from e

    def delete(self, key: str) -> None:
        _check_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as e:  # noqa: BLE001 - normalized by _wrap
            raise self._wrap("delete", key, e) from e

    def exists(self, key: str) -> bool:
        _check_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as e:  # noqa: BLE001 - normalized by _wrap
            if isinstance(e, ObjectNotFoundError):
                return False
            err = self._wrap("head", key, e)
            if isinstance(err, ObjectNotFoundError):
                return False
            raise err from e

    def url_for(self, key: str) -> str:
        # Never a signed URL here: objects are fetched server-side only, and
        # credentials must not leak toward the frontend. The key itself is
        # internal; routes must not expose it (schemas already hide it).
        return f"neon://{self._bucket}/{key}"


class StorageService:
    """Thin facade over the configured backend: put/get/delete/exists.

    Routes and services talk to this, never to ``LocalStorage``/
    ``NeonObjectStorage`` or boto3 directly. ``provider`` is informational
    (logs, Material rows).
    """

    def __init__(self, backend: StorageBackend, *, provider: str) -> None:
        self._backend = backend
        self.provider = provider

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        return self._backend.save(key, data, content_type)

    def get(self, key: str) -> bytes:
        return self._backend.load(key)

    def delete(self, key: str) -> None:
        self._backend.delete(key)

    def exists(self, key: str) -> bool:
        return self._backend.exists(key)


def get_storage() -> StorageBackend:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.storage_backend == "neon":
        # Production must never silently fall back to local disk: missing
        # Neon configuration raises here, at startup/wiring time.
        return NeonObjectStorage(
            endpoint=settings.neon_storage_endpoint,
            access_key_id=settings.neon_storage_access_key_id,
            secret_access_key=settings.neon_storage_secret_access_key,
            bucket_name=settings.neon_storage_bucket_name,
            region=settings.neon_storage_region,
        )
    return LocalStorage(root=settings.local_storage_dir)


def get_storage_service() -> StorageService:
    """Preferred entrypoint for services and tasks."""
    from app.core.config import get_settings

    settings = get_settings()
    backend = get_storage()
    return StorageService(backend, provider=settings.storage_backend)
