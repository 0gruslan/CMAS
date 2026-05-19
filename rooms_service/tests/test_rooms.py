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


def _create_floor(client: TestClient, number: int = 1, dormitory: str = "Общежитие 1") -> dict:
    return client.post("/floors", json={"number": number, "dormitory": dormitory}).json()


def _create_room(client: TestClient, floor_id: int, number: str = "101", capacity: int = 2) -> dict:
    return client.post("/rooms", json={"number": number, "floor_id": floor_id, "capacity": capacity}).json()


class TestHealth:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestFloors:
    def test_create_floor(self, client):
        resp = client.post("/floors", json={"number": 1, "dormitory": "Общежитие 1"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["number"] == 1
        assert body["dormitory"] == "Общежитие 1"

    def test_floor_number_required(self, client):
        resp = client.post("/floors", json={"dormitory": "Общежитие 1"})
        assert resp.status_code == 422


class TestRooms:
    def test_create_room(self, client):
        floor = _create_floor(client)
        resp = client.post("/rooms", json={"number": "101", "floor_id": floor["id"], "capacity": 3})
        assert resp.status_code == 201
        body = resp.json()
        assert body["number"] == "101"
        assert body["capacity"] == 3
        assert body["free_places"] == 3
        assert body["status"] == "free"

    def test_create_room_unknown_floor(self, client):
        resp = client.post("/rooms", json={"number": "101", "floor_id": 9999, "capacity": 2})
        assert resp.status_code == 404

    def test_free_places_cannot_exceed_capacity(self, client):
        floor = _create_floor(client)
        resp = client.post("/rooms", json={
            "number": "101", "floor_id": floor["id"], "capacity": 2, "free_places": 5
        })
        assert resp.status_code == 400

    def test_list_rooms_empty(self, client):
        resp = client.get("/rooms")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_rooms(self, client):
        floor = _create_floor(client)
        _create_room(client, floor["id"], "101")
        _create_room(client, floor["id"], "102")
        resp = client.get("/rooms")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_room(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"])
        resp = client.get(f"/rooms/{room['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == room["id"]

    def test_get_room_not_found(self, client):
        resp = client.get("/rooms/9999")
        assert resp.status_code == 404


class TestAssignEvict:
    def test_assign_student(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=2)
        resp = client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        assert resp.status_code == 200
        assert resp.json()["student_id"] == 1
        assert resp.json()["room_id"] == room["id"]

    def test_assign_reduces_free_places(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=2)
        client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        resp = client.get(f"/rooms/{room['id']}")
        assert resp.json()["free_places"] == 1

    def test_assign_full_room(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=1)
        client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        resp = client.post("/rooms/assign", json={"student_id": 2, "room_id": room["id"]})
        assert resp.status_code == 400

    def test_assign_repair_room(self, client):
        floor = _create_floor(client)
        resp = client.post("/rooms", json={
            "number": "101", "floor_id": floor["id"], "capacity": 2, "status": "repair"
        })
        room = resp.json()
        resp = client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        assert resp.status_code == 400

    def test_assign_unknown_room(self, client):
        resp = client.post("/rooms/assign", json={"student_id": 1, "room_id": 9999})
        assert resp.status_code == 404

    def test_evict_student(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=2)
        client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        resp = client.post("/rooms/evict", json={"student_id": 1, "room_id": room["id"]})
        assert resp.status_code == 200
        assert resp.json()["check_out_date"] is not None

    def test_evict_restores_free_places(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=2)
        client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        client.post("/rooms/evict", json={"student_id": 1, "room_id": room["id"]})
        resp = client.get(f"/rooms/{room['id']}")
        assert resp.json()["free_places"] == 2

    def test_evict_no_active_residence(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"])
        resp = client.post("/rooms/evict", json={"student_id": 99, "room_id": room["id"]})
        assert resp.status_code == 404


class TestFloorStats:
    def test_stats(self, client):
        floor = _create_floor(client)
        _create_room(client, floor["id"], "101", capacity=3)
        _create_room(client, floor["id"], "102", capacity=2)
        resp = client.get(f"/floors/{floor['id']}/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rooms"] == 2
        assert body["total_capacity"] == 5
        assert body["total_free_places"] == 5
        assert body["occupancy_percent"] == 0.0

    def test_stats_with_occupancy(self, client):
        floor = _create_floor(client)
        room = _create_room(client, floor["id"], capacity=2)
        client.post("/rooms/assign", json={"student_id": 1, "room_id": room["id"]})
        resp = client.get(f"/floors/{floor['id']}/stats")
        body = resp.json()
        assert body["occupied_places"] == 1
        assert body["occupancy_percent"] == 50.0

    def test_stats_floor_not_found(self, client):
        resp = client.get("/floors/9999/stats")
        assert resp.status_code == 404
