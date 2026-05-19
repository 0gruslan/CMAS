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


USER_DATA = {
    "full_name": "Иван Иванов",
    "phone": "+77001234567",
    "birth_date": "2000-01-15",
    "email": "ivan@example.com",
    "role": "student",
    "password": "secret123",
}


def _register(client: TestClient, data: dict | None = None) -> dict:
    return client.post("/register", json=data or USER_DATA).json()


def _login(client: TestClient, email: str = "ivan@example.com", password: str = "secret123") -> str:
    resp = client.post("/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestHealth:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestRegister:
    def test_success(self, client):
        resp = client.post("/register", json=USER_DATA)
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == USER_DATA["email"]
        assert body["role"] == "student"
        assert "id" in body

    def test_duplicate_email(self, client):
        client.post("/register", json=USER_DATA)
        resp = client.post("/register", json=USER_DATA)
        assert resp.status_code == 409

    def test_invalid_email(self, client):
        data = {**USER_DATA, "email": "not-an-email"}
        resp = client.post("/register", json=data)
        assert resp.status_code == 422

    def test_short_password(self, client):
        data = {**USER_DATA, "password": "123"}
        resp = client.post("/register", json=data)
        assert resp.status_code == 422

    def test_invalid_phone(self, client):
        data = {**USER_DATA, "phone": "abc"}
        resp = client.post("/register", json=data)
        assert resp.status_code == 422


class TestLogin:
    def test_success(self, client):
        _register(client)
        resp = client.post("/login", json={"email": USER_DATA["email"], "password": USER_DATA["password"]})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == USER_DATA["email"]

    def test_wrong_password(self, client):
        _register(client)
        resp = client.post("/login", json={"email": USER_DATA["email"], "password": "wrongpass"})
        assert resp.status_code == 401

    def test_unknown_email(self, client):
        resp = client.post("/login", json={"email": "nobody@example.com", "password": "pass"})
        assert resp.status_code == 401


class TestListUsers:
    def test_requires_auth(self, client):
        resp = client.get("/users")
        assert resp.status_code == 401

    def test_returns_users(self, client):
        _register(client)
        token = _login(client)
        resp = client.get("/users", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_room(self, client):
        _register(client)
        token = _login(client)
        resp = client.get("/users?room_id=999", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetUser:
    def test_found(self, client):
        user = _register(client)
        token = _login(client)
        resp = client.get(f"/users/{user['id']}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == user["id"]

    def test_not_found(self, client):
        _register(client)
        token = _login(client)
        resp = client.get("/users/9999", headers=_auth(token))
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/users/1")
        assert resp.status_code == 401


class TestAssignRoom:
    def test_assign_room(self, client):
        user = _register(client)
        token = _login(client)
        resp = client.put(
            f"/users/{user['id']}/room",
            json={"room_id": 5},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["room_id"] == 5

    def test_clear_room(self, client):
        user = _register(client)
        token = _login(client)
        client.put(f"/users/{user['id']}/room", json={"room_id": 5}, headers=_auth(token))
        resp = client.put(f"/users/{user['id']}/room", json={"room_id": None}, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["room_id"] is None

    def test_user_not_found(self, client):
        _register(client)
        token = _login(client)
        resp = client.put("/users/9999/room", json={"room_id": 1}, headers=_auth(token))
        assert resp.status_code == 404
