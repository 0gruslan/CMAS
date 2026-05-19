from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


REQUEST_DATA = {
    "student_id": 1,
    "room_id": 10,
    "category": "Сантехника",
    "description": "Течёт кран в ванной комнате",
}


def _create_request(client: TestClient, data: dict | None = None) -> dict:
    return client.post("/requests", json=data or REQUEST_DATA).json()


class TestHealth:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestCreateRequest:
    def test_success(self, client):
        resp = client.post("/requests", json=REQUEST_DATA)
        assert resp.status_code == 201
        body = resp.json()
        assert body["student_id"] == REQUEST_DATA["student_id"]
        assert body["room_id"] == REQUEST_DATA["room_id"]
        assert body["category"] == REQUEST_DATA["category"]
        assert body["status"] == "created"
        assert body["comments"] == []

    def test_short_description(self, client):
        data = {**REQUEST_DATA, "description": "кран"}
        resp = client.post("/requests", json=data)
        assert resp.status_code == 422

    def test_short_category(self, client):
        data = {**REQUEST_DATA, "category": "A"}
        resp = client.post("/requests", json=data)
        assert resp.status_code == 422

    def test_invalid_student_id(self, client):
        data = {**REQUEST_DATA, "student_id": 0}
        resp = client.post("/requests", json=data)
        assert resp.status_code == 422


class TestListRequests:
    def test_empty(self, client):
        resp = client.get("/requests")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_all(self, client):
        _create_request(client)
        _create_request(client)
        resp = client.get("/requests")
        assert len(resp.json()) == 2

    def test_filter_by_status(self, client):
        _create_request(client)
        resp = client.get("/requests?status=created")
        assert len(resp.json()) == 1

        resp = client.get("/requests?status=done")
        assert resp.json() == []

    def test_filter_by_student(self, client):
        _create_request(client, {**REQUEST_DATA, "student_id": 1})
        _create_request(client, {**REQUEST_DATA, "student_id": 2})
        resp = client.get("/requests?student_id=1")
        assert len(resp.json()) == 1
        assert resp.json()[0]["student_id"] == 1

    def test_filter_by_room(self, client):
        _create_request(client, {**REQUEST_DATA, "room_id": 10})
        _create_request(client, {**REQUEST_DATA, "room_id": 20})
        resp = client.get("/requests?room_id=20")
        assert len(resp.json()) == 1
        assert resp.json()[0]["room_id"] == 20


class TestGetRequest:
    def test_get_with_comments(self, client):
        req = _create_request(client)
        resp = client.get(f"/requests/{req['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == req["id"]
        assert "comments" in resp.json()

    def test_not_found(self, client):
        resp = client.get("/requests/9999")
        assert resp.status_code == 404


class TestUpdateStatus:
    def test_update_to_in_progress(self, client):
        req = _create_request(client)
        resp = client.put(
            f"/requests/{req['id']}/status",
            json={"status": "in_progress", "assignee_id": 42},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "in_progress"
        assert body["assignee_id"] == 42

    def test_update_to_done(self, client):
        req = _create_request(client)
        resp = client.put(f"/requests/{req['id']}/status", json={"status": "done"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_invalid_status(self, client):
        req = _create_request(client)
        resp = client.put(f"/requests/{req['id']}/status", json={"status": "unknown"})
        assert resp.status_code == 422

    def test_not_found(self, client):
        resp = client.put("/requests/9999/status", json={"status": "done"})
        assert resp.status_code == 404


class TestComments:
    def test_add_comment(self, client):
        req = _create_request(client)
        resp = client.post(
            f"/requests/{req['id']}/comments",
            json={"author_id": 5, "text": "Принято в работу"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["comments"]) == 1
        assert body["comments"][0]["text"] == "Принято в работу"
        assert body["comments"][0]["author_id"] == 5

    def test_multiple_comments(self, client):
        req = _create_request(client)
        client.post(f"/requests/{req['id']}/comments", json={"author_id": 1, "text": "Первый комментарий"})
        client.post(f"/requests/{req['id']}/comments", json={"author_id": 2, "text": "Второй комментарий"})
        resp = client.get(f"/requests/{req['id']}")
        assert len(resp.json()["comments"]) == 2

    def test_empty_comment(self, client):
        req = _create_request(client)
        resp = client.post(f"/requests/{req['id']}/comments", json={"author_id": 1, "text": ""})
        assert resp.status_code == 422

    def test_comment_request_not_found(self, client):
        resp = client.post("/requests/9999/comments", json={"author_id": 1, "text": "Текст"})
        assert resp.status_code == 404


class TestDeleteRequest:
    def test_delete(self, client):
        req = _create_request(client)
        resp = client.delete(f"/requests/{req['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_deleted_not_found(self, client):
        req = _create_request(client)
        client.delete(f"/requests/{req['id']}")
        resp = client.get(f"/requests/{req['id']}")
        assert resp.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/requests/9999")
        assert resp.status_code == 404


class TestListByRoom:
    def test_list_by_room(self, client):
        _create_request(client, {**REQUEST_DATA, "room_id": 10})
        _create_request(client, {**REQUEST_DATA, "room_id": 20})
        resp = client.get("/requests/room/10")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["room_id"] == 10
