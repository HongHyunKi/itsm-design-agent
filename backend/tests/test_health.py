from fastapi.testclient import TestClient

from app.main import create_app


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert len(res.headers["X-Request-ID"]) == 8


def test_request_id_is_echoed(client):
    res = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"


def test_unhandled_error_returns_json_500():
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal secret")

    res = TestClient(app, raise_server_exceptions=False).get("/boom", headers={"X-Request-ID": "rid500"})
    assert res.status_code == 500
    assert res.json() == {"code": "internal_error", "message": "Internal server error", "detail": None}
    assert res.headers["X-Request-ID"] == "rid500"
