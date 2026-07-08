import enum


class Locale(str, enum.Enum):
    ro = "ro"
    en = "en"


class LocationStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    delisted = "delisted"


class ItemType(str, enum.Enum):
    bag = "bag"
    trolley = "trolley"
    oversized = "oversized"


class StaffRole(str, enum.Enum):
    staff = "staff"
    owner = "owner"


class BookingStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    stored = "stored"
    released = "released"
    closed = "closed"
    expired = "expired"
    cancelled = "cancelled"
    no_show = "no_show"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class RefundReason(str, enum.Enum):
    traveler_cancel = "traveler_cancel"
    host_closed = "host_closed"
    system_unstored = "system_unstored"
    admin_manual = "admin_manual"
    goodwill = "goodwill"


class TicketStatus(str, enum.Enum):
    open = "open"
    pending = "pending"
    closed = "closed"


class TicketAuthor(str, enum.Enum):
    traveler = "traveler"
    admin = "admin"


class ActorType(str, enum.Enum):
    system = "system"
    user = "user"
    staff = "staff"
    admin = "admin"


class EmailStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    bounced = "bounced"
    failed = "failed"
