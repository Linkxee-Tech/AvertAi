def _login(client, phone):
    otp = client.post("/api/v1/auth/otp", json={"phone": phone}).json()
    tokens = client.post("/api/v1/auth/verify", json={"phone": phone, "code": otp["dev_hint_code"]}).json()
    return tokens["access_token"]


def test_update_preferences(client):
    token = _login(client, "+254700000400")
    r = client.put("/api/v1/users/preferences", json={
        "language": "sw", "notif_push": True, "notif_sms": False, "notif_voice": True,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "sw"
    assert body["notif_sms"] is False
    assert body["notif_voice"] is True


def test_admin_list_requires_superadmin(client):
    viewer_token = _login(client, "+254700000401")
    r = client.get("/api/v1/users/admin", headers={"Authorization": f"Bearer {viewer_token}"})
    assert r.status_code == 403  # default role on OTP signup is Viewer, not SuperAdmin


def test_admin_list_works_for_superadmin(client, admin_token):
    r = client.get("/api/v1/users/admin", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert "items" in r.json()


def test_block_and_role_change(client, admin_token, db_session):
    from app.db.models import User
    target = User(phone="+254700000402", role="Viewer", status="Active")
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)

    headers = {"Authorization": f"Bearer {admin_token}"}
    block = client.put(f"/api/v1/users/block/{target.id}", headers=headers)
    assert block.status_code == 200
    assert block.json()["status"] == "Blocked"

    role = client.put(f"/api/v1/users/role/{target.id}", json={"role": "Moderator"}, headers=headers)
    assert role.status_code == 200
    assert role.json()["role"] == "Moderator"


def test_delete_own_account(client):
    token = _login(client, "+254700000403")
    r = client.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # subsequent calls with the same token should fail — user no longer exists
    r2 = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401
