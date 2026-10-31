from __future__ import annotations


def test_delete_target_and_credential(logged_in_client):
    credential = logged_in_client.post(
        "/api/v1/credentials",
        json={"name": "delete-me", "kind": "http_bearer", "secret": "secret", "metadata": {}},
    )
    assert credential.status_code == 201, credential.text
    credential_body = credential.json()

    target = logged_in_client.post(
        "/api/v1/execution-targets",
        json={
            "name": "delete-target",
            "type": "http",
            "config": {"base_url": "http://127.0.0.1:9999"},
            "credential_id": credential_body["id"],
        },
    )
    assert target.status_code == 201, target.text
    target_body = target.json()

    deleted_target = logged_in_client.delete(
        f"/api/v1/execution-targets/{target_body['id']}",
        headers={"If-Match": str(target_body["version"])},
    )
    assert deleted_target.status_code == 204

    deleted_credential = logged_in_client.delete(
        f"/api/v1/credentials/{credential_body['id']}",
        headers={"If-Match": str(credential_body["version"])},
    )
    assert deleted_credential.status_code == 204
