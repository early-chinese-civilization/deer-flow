"""Configuration for uploads storage."""

from typing import Literal

from pydantic import BaseModel, Field

UploadsBackend = Literal["local", "oss"]


class OSSUploadsConfig(BaseModel):
    """Configuration for OSS-backed workspace uploads."""

    endpoint: str | None = Field(
        default=None,
        description="OSS endpoint hostname, e.g. oss-cn-shanghai.aliyuncs.com",
    )
    bucket: str | None = Field(
        default=None,
        description="OSS bucket name",
    )
    access_key_id: str | None = Field(
        default=None,
        description="OSS access key ID",
    )
    access_key_secret: str | None = Field(
        default=None,
        description="OSS access key secret",
    )
    region: str | None = Field(
        default=None,
        description="OSS region override. If omitted, derived from endpoint when possible.",
    )
    signed_url_expires_seconds: int = Field(
        default=3600,
        ge=60,
        le=604800,
        description="Default signed URL lifetime in seconds",
    )


class UploadsConfig(BaseModel):
    """Top-level uploads configuration."""

    backend: UploadsBackend = Field(
        default="local",
        description="Uploads storage backend. 'local' keeps legacy behaviour; 'oss' stores canonical files in OSS.",
    )
    oss: OSSUploadsConfig = Field(
        default_factory=OSSUploadsConfig,
        description="OSS uploads configuration",
    )
