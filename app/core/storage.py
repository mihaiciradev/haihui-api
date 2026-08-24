import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings


class StorageNotConfigured(Exception):
    pass


ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _client():
    settings = get_settings()
    if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
        raise StorageNotConfigured("R2 credentials are not configured")
    endpoint = settings.r2_endpoint_url or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    if not settings.r2_bucket:
        raise StorageNotConfigured("R2 bucket is not configured")
    try:
        _client().put_object(
            Bucket=settings.r2_bucket, Key=key, Body=data, ContentType=content_type
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageNotConfigured(f"R2 upload failed: {exc}") from exc


def presigned_get_url(key: str, expires_seconds: int = 3600) -> str:
    settings = get_settings()
    if not settings.r2_bucket:
        raise StorageNotConfigured("R2 bucket is not configured")
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    except (ClientError, BotoCoreError) as exc:
        raise StorageNotConfigured(f"R2 presign failed: {exc}") from exc


def presigned_get_urls(keys: list[str], expires_seconds: int = 604800) -> list[str]:
    """Location photos are public-facing (unlike bag photos), so they're
    presigned for the maximum SigV4 lifetime (7 days) instead of 1 hour --
    the frontend re-fetches the location on each page load anyway. Short-
    circuits on an empty list so locations without photos yet (the common
    case) never need R2 configured to be listed/viewed.
    """
    if not keys:
        return []
    return [presigned_get_url(key, expires_seconds) for key in keys]


def delete_object(key: str) -> None:
    settings = get_settings()
    if not settings.r2_bucket:
        raise StorageNotConfigured("R2 bucket is not configured")
    try:
        _client().delete_object(Bucket=settings.r2_bucket, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise StorageNotConfigured(f"R2 delete failed: {exc}") from exc
