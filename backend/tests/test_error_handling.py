from fastapi.testclient import TestClient

from app.main import app


def test_not_found_error_uses_unified_shape():
    with TestClient(app) as client:
        response = client.get("/api/conversations/999/messages")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert payload["error"]["message"] == "conversation_id 不存在"
    assert payload["detail"] == "conversation_id 不存在"


def test_validation_error_uses_unified_shape():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert "message 不能为空" in payload["error"]["message"]
