def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_otp_request_and_verify_roundtrip(client):
    r = client.post("/api/v1/auth/otp", json={"phone": "+254700000001"})
    assert r.status_code == 200
    # dev_hint_code is only present because no real SMS provider is configured
    code = r.json()["dev_hint_code"]

    r2 = client.post("/api/v1/auth/verify", json={"phone": "+254700000001", "code": code})
    assert r2.status_code == 200
    tokens = r2.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    # refresh token should mint a fresh access token
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r3.status_code == 200
    assert "access_token" in r3.json()


def test_otp_verify_rejects_wrong_code(client):
    client.post("/api/v1/auth/otp", json={"phone": "+254700000099"})
    r = client.post("/api/v1/auth/verify", json={"phone": "+254700000099", "code": "000000"})
    assert r.status_code == 400


def test_otp_verify_without_request_fails(client):
    r = client.post("/api/v1/auth/verify", json={"phone": "+254799999999", "code": "123456"})
    assert r.status_code == 400


def test_users_me_requires_auth(client):
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401


def test_users_me_returns_profile_after_login(client):
    otp_resp = client.post("/api/v1/auth/otp", json={"phone": "+254700000002"}).json()
    code = otp_resp["dev_hint_code"]
    tokens = client.post("/api/v1/auth/verify", json={"phone": "+254700000002", "code": code}).json()

    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200
    assert r.json()["phone"] == "+254700000002"
