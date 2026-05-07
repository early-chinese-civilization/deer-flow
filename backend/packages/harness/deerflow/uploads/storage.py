"""Storage helpers for canonical workspace uploads."""

from __future__ import annotations

import datetime as dt
import mimetypes
import re
from dataclasses import dataclass

from alibabacloud_oss_v2 import (
    Client,
    Config,
    DeleteObjectRequest,
    GetObjectRequest,
    ListObjectsV2Request,
    PutObjectRequest,
)
from alibabacloud_oss_v2.credentials import StaticCredentialsProvider

from deerflow.config import get_app_config


@dataclass(frozen=True)
class OSSObjectInfo:
    """Normalized object metadata returned from OSS listings."""

    key: str
    size: int
    last_modified: dt.datetime | None
    content_type: str | None = None


def workspace_root_prefix(workspace_id: str) -> str:
    """Build the canonical OSS root prefix for a workspace."""
    return f"workspaces/{workspace_id}"


def workspace_object_key(root_prefix: str, filename: str, subdir: str | None = None) -> str:
    """Build a canonical object key under a workspace prefix.

    Args:
        root_prefix: Workspace root prefix (e.g., "workspaces/workspace_id")
        filename: File name
        subdir: Optional subdirectory (e.g., "uploads" or "outputs")

    Returns:
        Full object key (e.g., "workspaces/workspace_id/uploads/file.txt")
    """
    if subdir:
        return f"{root_prefix.rstrip('/')}/{subdir.strip('/')}/{filename}"
    return f"{root_prefix.rstrip('/')}/{filename}"


def oss_root_path(bucket: str, root_prefix: str) -> str:
    """Build an OSS URI-like display path for a workspace prefix."""
    return f"oss://{bucket}/{root_prefix.rstrip('/')}/"


def _derive_region(endpoint: str) -> str | None:
    """Extract the region name from a standard OSS endpoint hostname."""
    normalized = endpoint.removeprefix("https://").removeprefix("http://")
    match = re.match(r"^oss-([^.]+)\.", normalized)
    if match:
        return match.group(1)
    return None


class OSSStorageBackend:
    """Thin wrapper around Alibaba Cloud OSS Python SDK V2."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        access_key_secret: str,
        region: str | None = None,
        signed_url_expires_seconds: int = 3600,
    ) -> None:
        if not endpoint:
            raise ValueError("OSS endpoint is required")
        if not bucket:
            raise ValueError("OSS bucket is required")
        if not access_key_id or not access_key_secret:
            raise ValueError("OSS access key credentials are required")

        resolved_region = region or _derive_region(endpoint)
        if not resolved_region:
            raise ValueError(f"Unable to derive OSS region from endpoint {endpoint!r}")

        self.bucket = bucket
        self.signed_url_expires_seconds = signed_url_expires_seconds
        self._client = Client(
            Config(
                region=resolved_region,
                endpoint=endpoint,
                credentials_provider=StaticCredentialsProvider(
                    access_key_id,
                    access_key_secret,
                ),
            )
        )

    @classmethod
    def from_app_config(cls) -> OSSStorageBackend:
        """Build the OSS storage backend from the current app config."""
        uploads_config = get_app_config().uploads
        if uploads_config.backend != "oss":
            raise ValueError("Uploads backend is not configured for OSS")
        return cls(
            endpoint=uploads_config.oss.endpoint or "",
            bucket=uploads_config.oss.bucket or "",
            access_key_id=uploads_config.oss.access_key_id or "",
            access_key_secret=uploads_config.oss.access_key_secret or "",
            region=uploads_config.oss.region,
            signed_url_expires_seconds=uploads_config.oss.signed_url_expires_seconds,
        )

    def put_object(self, *, key: str, content: bytes, content_type: str | None = None) -> None:
        """Upload an object to OSS."""
        self._client.put_object(
            PutObjectRequest(
                bucket=self.bucket,
                key=key,
                body=content,
                content_length=len(content),
                content_type=content_type or mimetypes.guess_type(key)[0],
            )
        )

    def put_object_stream(self, *, key: str, stream, content_length: int | None = None, content_type: str | None = None) -> None:
        """Upload an object to OSS from a stream (file-like object)."""
        self._client.put_object(
            PutObjectRequest(
                bucket=self.bucket,
                key=key,
                body=stream,
                content_length=content_length,
                content_type=content_type or mimetypes.guess_type(key)[0],
            )
        )

    def get_object_bytes(self, *, key: str) -> bytes:
        """Download an OSS object into memory."""
        result = self._client.get_object(
            GetObjectRequest(
                bucket=self.bucket,
                key=key,
            )
        )
        return result.body.read()

    def open_object(self, *, key: str):
        """Open an OSS object as a readable stream."""
        result = self._client.get_object(
            GetObjectRequest(
                bucket=self.bucket,
                key=key,
            )
        )
        return result.body

    def delete_object(self, *, key: str) -> None:
        """Delete an object from OSS."""
        self._client.delete_object(
            DeleteObjectRequest(
                bucket=self.bucket,
                key=key,
            )
        )

    def list_objects(self, *, prefix: str) -> list[OSSObjectInfo]:
        """List all non-directory objects under an OSS prefix."""
        continuation_token: str | None = None
        objects: list[OSSObjectInfo] = []

        while True:
            result = self._client.list_objects_v2(
                ListObjectsV2Request(
                    bucket=self.bucket,
                    prefix=prefix.rstrip("/") + "/",
                    continuation_token=continuation_token,
                    max_keys=1000,
                )
            )
            for item in result.contents or []:
                if not item.key or item.key.endswith("/"):
                    continue
                objects.append(
                    OSSObjectInfo(
                        key=item.key,
                        size=int(item.size or 0),
                        last_modified=item.last_modified,
                    )
                )

            if not result.is_truncated:
                break
            continuation_token = result.next_continuation_token

        return objects

    def presign_get_object(
        self,
        *,
        key: str,
        expires_seconds: int | None = None,
    ) -> tuple[str, dt.datetime | None]:
        """Generate a signed GET URL for an OSS object."""
        result = self._client.presign(
            GetObjectRequest(
                bucket=self.bucket,
                key=key,
            ),
            expires=dt.timedelta(seconds=expires_seconds or self.signed_url_expires_seconds),
        )
        return result.url, result.expiration

    def presign_put_object(
        self,
        *,
        key: str,
        content_type: str | None = None,
        content_length: int | None = None,
        expires_seconds: int | None = None,
    ) -> tuple[str, dt.datetime | None, dict[str, str]]:
        """Generate a signed PUT URL for an OSS object."""
        result = self._client.presign(
            PutObjectRequest(
                bucket=self.bucket,
                key=key,
                content_type=content_type or mimetypes.guess_type(key)[0],
                content_length=content_length,
            ),
            expires=dt.timedelta(seconds=expires_seconds or self.signed_url_expires_seconds),
        )
        headers = dict(result.signed_headers or {})
        return result.url, result.expiration, headers
