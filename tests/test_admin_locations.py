from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import hash_secret
from app.core.totp import generate_totp_secret
from app.models.city import City
from app.models.location import Location, LocationHours, LocationItemType
from app.models.staff import LocationLoginToken, StaffMember
from app.models.user import User


async def _create_admin_and_login(client, db, email="admin@haihui.ro") -> None:
    import pyotp

    secret = generate_totp_secret()
    admin = User(
        email=email,
        is_admin=True,
        admin_password_hash=hash_secret("supersecret1"),
        admin_totp_secret=secret,
        admin_totp_confirmed_at=datetime.now(UTC),
    )
    db.add(admin)
    await db.commit()

    login = await client.post(
        "/admin/auth/login", json={"email": email, "password": "supersecret1"}
    )
    assert login.status_code == 200
    verify = await client.post("/admin/auth/totp/verify", json={"code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200


NIL_UUID = "00000000-0000-0000-0000-000000000000"


async def _seed_city(db, slug="brasov") -> City:
    city = City(slug=slug, name_ro="Brașov", name_en="Brasov")
    db.add(city)
    await db.commit()
    return city


def _create_payload(city_slug="brasov", name="Suvenire Test"):
    return {
        "name": name,
        "city_slug": city_slug,
        "address": "Str. Test 1",
        "lat": 45.6,
        "lng": 25.6,
        "item_types": [
            {"item_type": "bag", "daily_capacity": 20},
            {"item_type": "trolley", "daily_capacity": 10},
        ],
        "owner_name": "Owner Test",
        "owner_pin": "1234",
    }


async def test_create_location_requires_admin_session(client):
    resp = await client.post("/admin/locations", json=_create_payload())
    assert resp.status_code == 401


async def test_create_location_happy_path(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    resp = await client.post("/admin/locations", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "suvenire-test"
    assert len(body["location_login_token"]) >= 16

    result = await db.execute(select(Location).where(Location.slug == "suvenire-test"))
    location = result.scalar_one()
    assert location.revenue_share_pct == 40  # default

    item_types = (
        (
            await db.execute(
                select(LocationItemType).where(LocationItemType.location_id == location.id)
            )
        )
        .scalars()
        .all()
    )
    assert {i.item_type.value for i in item_types} == {"bag", "trolley"}

    hours = (
        (await db.execute(select(LocationHours).where(LocationHours.location_id == location.id)))
        .scalars()
        .all()
    )
    assert len(hours) == 7  # default weekly template

    login_token = (
        await db.execute(
            select(LocationLoginToken).where(LocationLoginToken.location_id == location.id)
        )
    ).scalar_one()
    assert login_token.revoked_at is None

    owner = (
        await db.execute(select(StaffMember).where(StaffMember.location_id == location.id))
    ).scalar_one()
    assert owner.role.value == "owner"
    assert owner.name == "Owner Test"


async def test_create_location_rejects_unknown_city(client, db):
    await _create_admin_and_login(client, db)

    resp = await client.post("/admin/locations", json=_create_payload(city_slug="nowhere"))
    assert resp.status_code == 400


async def test_create_location_rejects_duplicate_item_type(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    payload = _create_payload()
    payload["item_types"] = [
        {"item_type": "bag", "daily_capacity": 10},
        {"item_type": "bag", "daily_capacity": 20},
    ]
    resp = await client.post("/admin/locations", json=payload)
    assert resp.status_code == 422


async def test_create_location_slug_collision_gets_suffixed(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)

    first = await client.post("/admin/locations", json=_create_payload())
    assert first.status_code == 201
    assert first.json()["slug"] == "suvenire-test"

    second = await client.post("/admin/locations", json=_create_payload())
    assert second.status_code == 201
    assert second.json()["slug"] == "suvenire-test-2"


async def test_list_locations_requires_admin_session(client):
    resp = await client.get("/admin/locations")
    assert resp.status_code == 401


async def test_list_locations_returns_created_locations(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    await client.post("/admin/locations", json=_create_payload())

    resp = await client.get("/admin/locations")
    assert resp.status_code == 200
    names = [loc["name"] for loc in resp.json()]
    assert "Suvenire Test" in names


async def test_add_staff_requires_admin_session(client):
    resp = await client.post(
        f"/admin/locations/{NIL_UUID}/staff",
        json={"name": "New Staff", "pin": "5678"},
    )
    assert resp.status_code == 401


async def test_add_staff_happy_path_and_can_log_in(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    resp = await client.post(
        f"/admin/locations/{created['id']}/staff",
        json={"name": "New Staff", "pin": "5678"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Staff"
    assert body["role"] == "staff"

    roster = await client.post(
        "/partner/auth/roster", json={"location_token": created["location_login_token"]}
    )
    names = [s["name"] for s in roster.json()["staff"]]
    assert "New Staff" in names
    assert "Owner Test" in names

    login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": body["staff_id"],
            "pin": "5678",
        },
    )
    assert login.status_code == 200


async def test_add_staff_rejects_unknown_location(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.post(
        f"/admin/locations/{NIL_UUID}/staff",
        json={"name": "New Staff", "pin": "5678"},
    )
    assert resp.status_code == 404


async def test_reset_pin_requires_admin_session(client):
    resp = await client.post(
        f"/admin/staff/{NIL_UUID}/reset-pin",
        json={"new_pin": "4321"},
    )
    assert resp.status_code == 401


async def test_reset_pin_lets_staff_log_in_with_new_pin(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == created["id"]))
    owner = result.scalar_one()

    resp = await client.post(
        f"/admin/staff/{owner.id}/reset-pin", json={"new_pin": "4321"}
    )
    assert resp.status_code == 204

    old_pin_login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert old_pin_login.status_code == 401

    new_pin_login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "4321",
        },
    )
    assert new_pin_login.status_code == 200


async def test_reset_pin_clears_staff_lockout_but_not_location_lockout(client, db):
    """Reset-pin is a narrow, staff-scoped admin action (§3.2). In this
    single-staff scenario, 5 fails also trip the shared location-token
    counter (same root cause as the earlier scope-priority fix) -- that's a
    separate signal reset-pin deliberately does not touch, since a PIN reset
    for one person shouldn't silently clear a location-wide lockout that may
    be catching unrelated activity. Full recovery needs rotate-token too.
    """
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == created["id"]))
    owner = result.scalar_one()

    for _ in range(5):
        await client.post(
            "/partner/auth/login",
            json={
                "location_token": created["location_login_token"],
                "staff_id": str(owner.id),
                "pin": "9999",
            },
        )
    locked_check = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert locked_check.status_code == 423

    reset = await client.post(f"/admin/staff/{owner.id}/reset-pin", json={"new_pin": "1234"})
    assert reset.status_code == 204

    await db.refresh(owner)
    assert owner.failed_pin_attempts == 0
    assert owner.locked_until is None

    # Location-level lock is untouched by reset-pin -- login is still 423.
    still_locked = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert still_locked.status_code == 423
    assert still_locked.json()["detail"]["scope"] == "location"

    # Full recovery: admin also rotates the location token.
    rotated = await client.post(f"/admin/locations/{created['id']}/rotate-token")
    assert rotated.status_code == 200

    login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": rotated.json()["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert login.status_code == 200


async def test_rotate_token_requires_admin_session(client):
    resp = await client.post(f"/admin/locations/{NIL_UUID}/rotate-token")
    assert resp.status_code == 401


async def test_rotate_token_invalidates_old_and_issues_new(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()
    old_token = created["location_login_token"]

    resp = await client.post(f"/admin/locations/{created['id']}/rotate-token")
    assert resp.status_code == 200
    new_token = resp.json()["location_login_token"]
    assert new_token != old_token

    old_roster = await client.post("/partner/auth/roster", json={"location_token": old_token})
    assert old_roster.status_code == 401

    new_roster = await client.post("/partner/auth/roster", json={"location_token": new_token})
    assert new_roster.status_code == 200


async def test_admin_location_bookings_requires_admin_session(client):
    resp = await client.get(f"/admin/locations/{NIL_UUID}/bookings")
    assert resp.status_code == 401


async def test_admin_location_bookings_rejects_unknown_location(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.get(f"/admin/locations/{NIL_UUID}/bookings")
    assert resp.status_code == 404


async def test_admin_location_bookings_returns_created_booking(client, db):
    from datetime import date, timedelta

    from app.core.security import generate_opaque_token
    from app.models.location import PriceListEntry
    from app.models.magic_link import MagicLinkToken

    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    db.add(PriceListEntry(item_type="bag", price_ron=16.0, valid_from=date.today()))
    await db.commit()

    raw, hashed = generate_opaque_token()
    db.add(
        MagicLinkToken(
            email="traveler@example.com",
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    await db.commit()
    await client.post("/auth/magic-link/verify", json={"token": raw})

    booking = await client.post(
        "/bookings",
        json={
            "location_slug": "suvenire-test",
            "storage_date": (date.today() + timedelta(days=1)).isoformat(),
            "items": [{"item_type": "bag", "qty": 1}],
            "guest_phone": "+40700000000",
        },
    )
    assert booking.status_code == 201

    resp = await client.get(f"/admin/locations/{created['id']}/bookings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["code"] == booking.json()["code"]


async def test_rotate_token_rejects_unknown_location(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.post(f"/admin/locations/{NIL_UUID}/rotate-token")
    assert resp.status_code == 404


async def test_admin_overrides_requires_admin_session(client):
    from datetime import date, timedelta

    target = date.today() + timedelta(days=5)
    resp = await client.post(
        f"/admin/locations/{NIL_UUID}/overrides", json={"date": target.isoformat(), "closed": True}
    )
    assert resp.status_code == 401


async def test_admin_overrides_rejects_unknown_location(client, db):
    from datetime import date, timedelta

    await _create_admin_and_login(client, db)
    target = date.today() + timedelta(days=5)
    resp = await client.post(
        f"/admin/locations/{NIL_UUID}/overrides", json={"date": target.isoformat(), "closed": True}
    )
    assert resp.status_code == 404


async def test_admin_can_set_list_and_delete_override(client, db):
    from datetime import date, timedelta

    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()
    target = date.today() + timedelta(days=5)

    resp = await client.post(
        f"/admin/locations/{created['id']}/overrides",
        json={"date": target.isoformat(), "closed": True},
    )
    assert resp.status_code == 201
    assert resp.json()["created_by"] == "admin"

    listing = await client.get(f"/admin/locations/{created['id']}/overrides")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    override_url = f"/admin/locations/{created['id']}/overrides/{target.isoformat()}"
    deleted = await client.delete(override_url)
    assert deleted.status_code == 204

    listing_after = await client.get(f"/admin/locations/{created['id']}/overrides")
    assert listing_after.json() == []


async def test_update_location_requires_admin_session(client):
    resp = await client.patch(f"/admin/locations/{NIL_UUID}", json={"name": "New Name"})
    assert resp.status_code == 401


async def test_update_location_rejects_unknown_location(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.patch(f"/admin/locations/{NIL_UUID}", json={"name": "New Name"})
    assert resp.status_code == 404


async def test_update_location_rejects_empty_body(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    resp = await client.patch(f"/admin/locations/{created['id']}", json={})
    assert resp.status_code == 400


async def test_update_location_changes_only_given_fields(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    resp = await client.patch(
        f"/admin/locations/{created['id']}", json={"name": "Renamed Shop", "revenue_share_pct": 55}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed Shop"
    assert body["revenue_share_pct"] == 55
    # address wasn't touched -- still the value from creation
    assert body["address"] == "Str. Test 1"
    assert len(body["item_types"]) == 2


async def test_update_location_replaces_item_types(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    resp = await client.patch(
        f"/admin/locations/{created['id']}",
        json={"item_types": [{"item_type": "oversized", "daily_capacity": 3}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["item_types"]) == 1
    assert body["item_types"][0]["item_type"] == "oversized"
    assert body["item_types"][0]["daily_capacity"] == 3


async def test_update_location_can_delist(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    resp = await client.patch(f"/admin/locations/{created['id']}", json={"status": "delisted"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "delisted"

    # delisted locations disappear from public listing/detail
    public = await client.get(f"/locations/{created['slug']}")
    assert public.status_code == 404


async def test_update_location_replaces_hours(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    new_hours = [
        {"weekday": w, "open_time": "09:00:00", "close_time": "18:00:00"} for w in range(5)
    ]
    resp = await client.patch(f"/admin/locations/{created['id']}", json={"hours": new_hours})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hours"]) == 5
    assert body["hours"][0]["open_time"] == "09:00:00"


async def test_list_staff_requires_admin_session(client):
    resp = await client.get(f"/admin/locations/{NIL_UUID}/staff")
    assert resp.status_code == 401


async def test_list_staff_rejects_unknown_location(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.get(f"/admin/locations/{NIL_UUID}/staff")
    assert resp.status_code == 404


async def test_list_staff_returns_roster(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()
    await client.post(
        f"/admin/locations/{created['id']}/staff", json={"name": "New Staff", "pin": "5678"}
    )

    resp = await client.get(f"/admin/locations/{created['id']}/staff")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"]: s for s in body}
    assert set(names) == {"Owner Test", "New Staff"}
    assert names["Owner Test"]["is_active"] is True


async def test_deactivate_staff_requires_admin_session(client):
    resp = await client.post(f"/admin/staff/{NIL_UUID}/deactivate")
    assert resp.status_code == 401


async def test_deactivate_staff_rejects_unknown_staff(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.post(f"/admin/staff/{NIL_UUID}/deactivate")
    assert resp.status_code == 404


async def test_deactivate_staff_blocks_login_and_roster(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == created["id"]))
    owner = result.scalar_one()

    resp = await client.post(f"/admin/staff/{owner.id}/deactivate")
    assert resp.status_code == 204

    roster = await client.post(
        "/partner/auth/roster", json={"location_token": created["location_login_token"]}
    )
    assert roster.json()["staff"] == []

    login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert login.status_code == 401


async def test_deactivate_staff_revokes_an_existing_session_immediately(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == created["id"]))
    owner = result.scalar_one()

    login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert login.status_code == 200

    me_before = await client.get("/partner/me")
    assert me_before.status_code == 200

    await client.post(f"/admin/staff/{owner.id}/deactivate")

    me_after = await client.get("/partner/me")
    assert me_after.status_code == 401


async def test_reactivate_staff_requires_admin_session(client):
    resp = await client.post(f"/admin/staff/{NIL_UUID}/reactivate")
    assert resp.status_code == 401


async def test_reactivate_staff_rejects_unknown_staff(client, db):
    await _create_admin_and_login(client, db)
    resp = await client.post(f"/admin/staff/{NIL_UUID}/reactivate")
    assert resp.status_code == 404


async def test_reactivate_staff_restores_login(client, db):
    await _seed_city(db)
    await _create_admin_and_login(client, db)
    created = (await client.post("/admin/locations", json=_create_payload())).json()

    result = await db.execute(select(StaffMember).where(StaffMember.location_id == created["id"]))
    owner = result.scalar_one()

    await client.post(f"/admin/staff/{owner.id}/deactivate")
    reactivate = await client.post(f"/admin/staff/{owner.id}/reactivate")
    assert reactivate.status_code == 204

    login = await client.post(
        "/partner/auth/login",
        json={
            "location_token": created["location_login_token"],
            "staff_id": str(owner.id),
            "pin": "1234",
        },
    )
    assert login.status_code == 200
