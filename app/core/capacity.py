from collections.abc import Iterator
from datetime import date, timedelta

MAX_STORAGE_SPAN_DAYS = 13  # inclusive span cap: storage_date .. storage_date+13 (14 days total)
MAX_DAYS_AHEAD = 31  # how far in advance storage_date may be


def date_range(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def daily_usage(rows: list[tuple[date, date, int]], start: date, end: date) -> dict[date, int]:
    """rows are (booking.storage_date, booking.pickup_date, item_qty) for
    existing bookings that could overlap [start, end]. Returns qty reserved
    per calendar day in that window -- a booking occupies capacity on every
    day it spans, not just its drop-off day.
    """
    usage: dict[date, int] = {}
    for row_start, row_end, qty in rows:
        overlap_start = max(row_start, start)
        overlap_end = min(row_end, end)
        for d in date_range(overlap_start, overlap_end):
            usage[d] = usage.get(d, 0) + qty
    return usage
