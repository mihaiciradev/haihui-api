from app.models.city import City


async def test_list_cities_returns_only_active(client, db):
    db.add(City(slug="brasov", name_ro="Brașov", name_en="Brasov"))
    db.add(City(slug="hidden", name_ro="Ascuns", name_en="Hidden", is_active=False))
    await db.commit()

    resp = await client.get("/cities")
    assert resp.status_code == 200
    slugs = [c["slug"] for c in resp.json()]
    assert "brasov" in slugs
    assert "hidden" not in slugs


async def test_list_cities_requires_no_auth(client):
    resp = await client.get("/cities")
    assert resp.status_code == 200
