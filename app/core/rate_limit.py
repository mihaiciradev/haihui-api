"""In-process fixed-window rate limiter.

Sufficient for a single `web` Fly machine (per §2.1's process layout). If the
API is ever scaled to multiple machines, swap the store below for Upstash
Redis — the call sites (`check_rate_limit`) do not need to change.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, status

_buckets: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, *, max_attempts: int, window_seconds: int) -> None:
    now = time.monotonic()
    window_start = now - window_seconds
    hits = _buckets[key]
    hits[:] = [t for t in hits if t > window_start]
    if len(hits) >= max_attempts:
        retry_after = max(1, round(window_seconds - (now - hits[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Too many requests. Please try again later.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)
