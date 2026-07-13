def test_broadcast_send_requires_auth(client):
    r = client.post("/api/v1/broadcast/send", json={"message": "hi", "channels": ["SMS"]})
    assert r.status_code == 401


def test_broadcast_send_and_history(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    send = client.post("/api/v1/broadcast/send", json={
        "message": "Code RED: evacuate now",
        "channels": ["SMS", "Push"],
        "target_filter": "risk_level:RED",
    }, headers=headers)
    assert send.status_code == 200

    history = client.get("/api/v1/broadcast/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["total"] >= 1
    assert history.json()["items"][0]["message_text"] == "Code RED: evacuate now"


def test_scheduled_broadcast_has_zero_delivery_counts(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post("/api/v1/broadcast/send", json={
        "message": "Future alert",
        "channels": ["SMS"],
        "target_filter": "all",
        "scheduled_at": "2099-01-01T10:00:00",
    }, headers=headers)
    assert r.status_code == 200
    history = client.get("/api/v1/broadcast/history", headers=headers).json()
    scheduled = next(b for b in history["items"] if b["message_text"] == "Future alert")
    assert scheduled["status"] == "scheduled"
    assert scheduled["sent_via_sms_count"] == 0
