def test_submit_feedback_parses_intent(client):
    r = client.post("/api/v1/feedback/submit", json={
        "phone": "+254700000300",
        "lat": 1.75, "lon": 40.05,
        "raw_text": "FLOOD 2.5km North of Wajir",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["parsed_intent"] == "flood_sighting"
    assert body["status"] == "Pending"
    assert body["reference"].startswith("RPT-")


def test_submit_feedback_crop_ok(client):
    r = client.post("/api/v1/feedback/submit", json={
        "phone": "+254700000301", "lat": 1.0, "lon": 40.0,
        "raw_text": "CROP OK",
    })
    assert r.status_code == 200
    assert r.json()["parsed_intent"] == "crop_status_ok"


def test_feedback_admin_list_requires_auth(client):
    r = client.get("/api/v1/feedback/admin")
    assert r.status_code == 401


def test_feedback_admin_list_and_verify_flow(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    submit = client.post("/api/v1/feedback/submit", json={
        "phone": "+254700000302", "lat": 1.0, "lon": 40.0, "raw_text": "DROUGHT severe near Marsabit",
    }).json()

    listed = client.get("/api/v1/feedback/admin", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    verified = client.put(f"/api/v1/feedback/verify/{submit['id']}", headers=headers)
    assert verified.status_code == 200
    assert verified.json()["status"] == "Verified"


def test_mark_spam(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    submit = client.post("/api/v1/feedback/submit", json={
        "phone": "+254700000303", "lat": 1.0, "lon": 40.0, "raw_text": "random unrelated text",
    }).json()
    r = client.delete(f"/api/v1/feedback/spam/{submit['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Spam"
