def test_predict_current_requires_seeded_grid(client):
    r = client.get("/api/v1/predict/current", params={"lat": 1.0, "lon": 40.0})
    assert r.status_code == 404  # no grid cells seeded yet in this test


def test_predict_current_returns_action_code(client, seeded_grid):
    r = client.get("/api/v1/predict/current", params={"lat": 1.0, "lon": 40.0})
    assert r.status_code == 200
    body = r.json()
    assert body["action_code"] in ("GREEN", "YELLOW", "RED")
    assert 0.0 <= body["flood_prob"] <= 1.0
    assert 0.0 <= body["drought_prob"] <= 1.0
    assert body["village_name"] == "TestVille"


def test_predict_current_is_deterministic_per_grid(client, seeded_grid):
    """Same grid cell + same day offset should return the same numbers —
    this stands in for a real trained model until one is plugged in."""
    r1 = client.get("/api/v1/predict/current", params={"lat": 1.0, "lon": 40.0}).json()
    r2 = client.get("/api/v1/predict/current", params={"lat": 1.0, "lon": 40.0}).json()
    assert r1["flood_prob"] == r2["flood_prob"]
    assert r1["action_code"] == r2["action_code"]


def test_predict_week_returns_seven_days(client, seeded_grid):
    r = client.get("/api/v1/predict/week", params={"lat": 1.0, "lon": 40.0})
    assert r.status_code == 200
    assert len(r.json()["forecast"]) == 7


def test_predict_grid_history_404_for_unknown_id(client):
    r = client.get("/api/v1/predict/grid/does-not-exist")
    assert r.status_code == 404


def test_predict_mosaic_returns_cells(client, seeded_grid):
    r = client.get("/api/v1/predict/grids", params={"window": "3-day"})
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert len(cells) >= 1
    assert all(c["action_code"] in ("GREEN", "YELLOW", "RED") for c in cells)
