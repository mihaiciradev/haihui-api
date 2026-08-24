import uuid

from app.core.storage import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    StorageNotConfigured,
    delete_object,
    presigned_get_urls,
    upload_bytes,
)
from app.models.location import Location
from app.schemas.location_photo import LocationPhotoOut

MAX_PHOTOS_PER_LOCATION = 12


def to_photo_outs(location: Location) -> list[LocationPhotoOut]:
    keys = list(location.photos)
    urls = presigned_get_urls(keys)
    return [LocationPhotoOut(key=k, url=u) for k, u in zip(keys, urls, strict=True)]


def public_photo_urls(location: Location) -> list[str]:
    """For public browse/search/detail responses. A transient R2 outage
    shouldn't take down location listings entirely -- degrades to no photos
    rather than a 503.
    """
    try:
        return presigned_get_urls(list(location.photos))
    except StorageNotConfigured:
        return []


async def add_location_photo(location: Location, content_type: str | None, data: bytes) -> str:
    ext = ALLOWED_IMAGE_TYPES.get(content_type or "")
    if ext is None:
        raise ValueError("Photo must be JPEG, PNG, or WEBP")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Photo must be under 8MB")
    if len(location.photos) >= MAX_PHOTOS_PER_LOCATION:
        raise ValueError(f"A location can have at most {MAX_PHOTOS_PER_LOCATION} photos")

    key = f"locations/{location.id}/{uuid.uuid4()}.{ext}"
    upload_bytes(key, data, content_type or "application/octet-stream")
    # Reassigned (not appended in place) so SQLAlchemy's change tracking on
    # the ARRAY column actually picks up the mutation.
    location.photos = [*location.photos, key]
    return key


def remove_location_photo(location: Location, key: str) -> bool:
    if key not in location.photos:
        return False
    location.photos = [k for k in location.photos if k != key]
    try:
        delete_object(key)
    except StorageNotConfigured:
        pass
    return True
