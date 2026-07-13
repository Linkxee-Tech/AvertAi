def test_resources_nearby_is_public(client):
    r = client.get("/api/v1/resources/nearby", params={"lat": 1.0, "lon": 40.0})
    assert r.status_code == 200
    assert "items" in r.json()


def test_resources_admin_requires_auth(client):
    r = client.get("/api/v1/resources/admin")
    assert r.status_code == 401


def test_add_and_list_resource(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    add = client.post("/api/v1/resources/admin", json={
        "name": "Test Water Truck", "type": "Water",
        "lat": 1.0, "lon": 40.0, "capacity": "4000L", "contact_phone": "+254700000004",
    }, headers=headers)
    assert add.status_code == 200

    listed = client.get("/api/v1/resources/admin", headers=headers)
    assert listed.status_code == 200
    names = [r["name"] for r in listed.json()["items"]]
    assert "Test Water Truck" in names


def test_resources_nearby_sorted_by_distance(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/v1/resources/admin", json={
        "name": "Far Resource", "type": "Food", "lat": 10.0, "lon": 50.0,
        "capacity": "1t", "contact_phone": "+254700000005",
    }, headers=headers)
    client.post("/api/v1/resources/admin", json={
        "name": "Near Resource", "type": "Food", "lat": 1.01, "lon": 40.01,
        "capacity": "1t", "contact_phone": "+254700000006",
    }, headers=headers)

    r = client.get("/api/v1/resources/nearby", params={"lat": 1.0, "lon": 40.0})
    items = r.json()["items"]
    assert items[0]["name"] == "Near Resource"
    assert items[0]["distance_km"] < items[-1]["distance_km"]
