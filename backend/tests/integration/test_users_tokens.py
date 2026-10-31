from __future__ import annotations

from fastapi.testclient import TestClient


def test_user_management_and_api_token(logged_in_client):
    created = logged_in_client.post(
        "/api/v1/users",
        json={
            "username": "operator1",
            "display_name": "Operator One",
            "role": "operator",
            "password": "operatorpassword123",
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["role"] == "operator"

    listing = logged_in_client.get("/api/v1/users")
    assert listing.status_code == 200
    assert any(item["username"] == "operator1" for item in listing.json()["items"])

    updated = logged_in_client.patch(
        f"/api/v1/users/{user['id']}",
        json={"display_name": "Operator Updated"},
        headers={"If-Match": str(user["version"])},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "Operator Updated"

    reset = logged_in_client.post(f"/api/v1/users/{user['id']}/reset-password")
    assert reset.status_code == 200
    assert len(reset.json()["temporary_password"]) >= 12

    token_response = logged_in_client.post("/api/v1/auth/tokens", json={"name": "ci-token"})
    assert token_response.status_code == 201, token_response.text
    raw_token = token_response.json()["token"]
    assert raw_token.startswith("tc_")

    from task_control.main import app

    bearer_client = TestClient(app)
    bearer_client.headers["Authorization"] = f"Bearer {raw_token}"
    me = bearer_client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["username"] == "admin"

    revoke = logged_in_client.delete(f"/api/v1/auth/tokens/{token_response.json()['id']}")
    assert revoke.status_code == 204
    assert bearer_client.get("/api/v1/auth/me").status_code == 401
