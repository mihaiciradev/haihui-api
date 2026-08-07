from app.core.security import generate_opaque_token, hash_secret
from app.models.city import City
from app.models.enums import LocationStatus, StaffRole
from app.models.location import Location
from app.models.staff import LocationLoginToken, StaffMember


async def _seed_location_with_staff(db, pin="1234"):
    city = City(slug="brasov", name_ro="Brașov", name_en="Brasov")
    db.add(city)
    await db.flush()

    location = Location(
        city_id=city.id,
        name="Test Host",
        slug="test-host",
        address="Str. Test 1",
        lat=45.0,
        lng=25.0,
        status=LocationStatus.active,
        utm_code="test1234",
    )
    db.add(location)
    await db.flush()

    raw_token, token_hash = generate_opaque_token()
    db.add(LocationLoginToken(location_id=location.id, token_hash=token_hash))

    staff = StaffMember(
        location_id=location.id, name="Ana", pin_hash=hash_secret(pin), role=StaffRole.staff
    )
    db.add(staff)
    await db.flush()
    await db.commit()
    return raw_token, staff


async def test_staff_roster_lists_active_staff(client, db):
    raw_token, staff = await _seed_location_with_staff(db)

    resp = await client.post("/partner/auth/roster", json={"location_token": raw_token})
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["staff"]]
    assert "Ana" in names


async def test_staff_login_happy_path(client, db):
    raw_token, staff = await _seed_location_with_staff(db, pin="1234")

    resp = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "1234"},
    )
    assert resp.status_code == 200
    assert "hh_staff_session" in resp.cookies


async def test_staff_login_wrong_pin_rejected(client, db):
    raw_token, staff = await _seed_location_with_staff(db, pin="1234")

    resp = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "9999"},
    )
    assert resp.status_code == 401


async def test_staff_login_locks_out_after_five_failures(client, db):
    raw_token, staff = await _seed_location_with_staff(db, pin="1234")

    for _ in range(5):
        resp = await client.post(
            "/partner/auth/login",
            json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "9999"},
        )
        assert resp.status_code == 401

    # 6th attempt, even with the correct PIN, must be locked out.
    resp = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "1234"},
    )
    assert resp.status_code == 423


async def test_staff_login_rejects_unknown_location_token(client):
    resp = await client.post(
        "/partner/auth/login",
        json={
            "location_token": "bogus-token-value",
            "staff_id": "00000000-0000-0000-0000-000000000000",
            "pin": "1234",
        },
    )
    assert resp.status_code == 401


async def test_partner_me_requires_session(client):
    resp = await client.get("/partner/me")
    assert resp.status_code == 401


async def test_partner_me_returns_identity_after_login(client, db):
    raw_token, staff = await _seed_location_with_staff(db, pin="1234")

    login = await client.post(
        "/partner/auth/login",
        json={"location_token": raw_token, "staff_id": str(staff.id), "pin": "1234"},
    )
    assert login.status_code == 200

    me = await client.get("/partner/me")
    assert me.status_code == 200
    body = me.json()
    assert body["staff_id"] == str(staff.id)
    assert body["name"] == "Ana"
    assert body["role"] == "staff"
