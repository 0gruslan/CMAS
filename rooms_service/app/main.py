from __future__ import annotations

from datetime import date
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from prometheus_fastapi_instrumentator import Instrumentator

from cmas_shared.observability import CorrelationIdMiddleware, configure_logging

from .database import get_db
from .models import FloorORM, ResidenceORM, RoomORM

configure_logging("rooms_service")

app = FastAPI(
    title="Rooms Service",
    description="Сервис управления комнатами и проживанием",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)
app.add_middleware(CorrelationIdMiddleware, service_name="rooms_service")

Instrumentator().instrument(app).expose(app)


class RoomStatus(str, Enum):
    free = "free"
    partial = "partial"
    repair = "repair"


class Floor(BaseModel):
    id: int
    number: int = Field(..., ge=1)
    dormitory: str = Field(..., min_length=1)


class FloorCreate(BaseModel):
    number: int = Field(..., ge=1)
    dormitory: str = Field(..., min_length=1)


class Room(BaseModel):
    id: int
    number: str = Field(..., min_length=1)
    floor_id: int
    capacity: int = Field(..., ge=1)
    free_places: int = Field(..., ge=0)
    status: RoomStatus


class Residence(BaseModel):
    id: int
    student_id: int
    room_id: int
    check_in_date: date
    check_out_date: date | None = None


class RoomAssignIn(BaseModel):
    student_id: int
    room_id: int
    check_in_date: date | None = None


class RoomCreate(BaseModel):
    number: str = Field(..., min_length=1)
    floor_id: int
    capacity: int = Field(..., ge=1)
    free_places: int | None = Field(default=None, ge=0)
    status: RoomStatus | None = None


class RoomEvictIn(BaseModel):
    student_id: int
    room_id: int
    check_out_date: date | None = None


class FloorStats(BaseModel):
    floor_id: int
    total_rooms: int
    total_capacity: int
    total_free_places: int
    occupied_places: int
    occupancy_percent: float


def _calculate_status(room: RoomORM) -> RoomStatus:
    if room.status == RoomStatus.repair.value:
        return RoomStatus.repair
    if room.free_places >= room.capacity:
        return RoomStatus.free
    return RoomStatus.partial


def _room_to_out(room: RoomORM) -> Room:
    return Room(
        id=room.id,
        number=room.number,
        floor_id=room.floor_id,
        capacity=room.capacity,
        free_places=room.free_places,
        status=RoomStatus(room.status),
    )


def _residence_to_out(residence: ResidenceORM) -> Residence:
    return Residence(
        id=residence.id,
        student_id=residence.student_id,
        room_id=residence.room_id,
        check_in_date=residence.check_in_date,
        check_out_date=residence.check_out_date,
    )


@app.get("/")
async def root():
    return {"service": "Rooms Service", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/rooms", response_model=list[Room])
async def list_rooms(db: Session = Depends(get_db)) -> list[Room]:
    rooms = db.query(RoomORM).order_by(RoomORM.id.asc()).all()
    return [_room_to_out(room) for room in rooms]


@app.post("/floors", response_model=Floor, status_code=201)
async def create_floor(payload: FloorCreate, db: Session = Depends(get_db)) -> Floor:
    floor = FloorORM(number=payload.number, dormitory=payload.dormitory)
    db.add(floor)
    db.commit()
    db.refresh(floor)
    return Floor(id=floor.id, number=floor.number, dormitory=floor.dormitory)


@app.post("/rooms", response_model=Room, status_code=201)
async def create_room(payload: RoomCreate, db: Session = Depends(get_db)) -> Room:
    floor = db.query(FloorORM).filter(FloorORM.id == payload.floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")

    free_places = payload.free_places if payload.free_places is not None else payload.capacity
    if free_places > payload.capacity:
        raise HTTPException(status_code=400, detail="free_places cannot exceed capacity")

    room = RoomORM(
        number=payload.number,
        floor_id=payload.floor_id,
        capacity=payload.capacity,
        free_places=free_places,
        status=(payload.status or RoomStatus.free).value,
    )
    room.status = _calculate_status(room).value
    db.add(room)
    db.commit()
    db.refresh(room)
    return _room_to_out(room)


@app.get("/rooms/{room_id}", response_model=Room)
async def get_room(room_id: int, db: Session = Depends(get_db)) -> Room:
    room = db.query(RoomORM).filter(RoomORM.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return _room_to_out(room)


@app.post("/rooms/assign", response_model=Residence)
async def assign_room(payload: RoomAssignIn, db: Session = Depends(get_db)) -> Residence:
    room = db.query(RoomORM).filter(RoomORM.id == payload.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status == RoomStatus.repair.value:
        raise HTTPException(status_code=400, detail="Room is under repair")
    if room.free_places <= 0:
        raise HTTPException(status_code=400, detail="No free places in room")

    residence = ResidenceORM(
        student_id=payload.student_id,
        room_id=payload.room_id,
        check_in_date=payload.check_in_date or date.today(),
        check_out_date=None,
    )
    db.add(residence)

    room.free_places -= 1
    room.status = _calculate_status(room).value

    db.commit()
    db.refresh(residence)
    return _residence_to_out(residence)


@app.post("/rooms/evict", response_model=Residence)
async def evict_room(payload: RoomEvictIn, db: Session = Depends(get_db)) -> Residence:
    room = db.query(RoomORM).filter(RoomORM.id == payload.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    residence = (
        db.query(ResidenceORM)
        .filter(
            ResidenceORM.student_id == payload.student_id,
            ResidenceORM.room_id == payload.room_id,
            ResidenceORM.check_out_date.is_(None),
        )
        .order_by(ResidenceORM.id.asc())
        .first()
    )
    if not residence:
        raise HTTPException(status_code=404, detail="Active residence not found")

    residence.check_out_date = payload.check_out_date or date.today()
    room.free_places += 1
    room.status = _calculate_status(room).value

    db.commit()
    db.refresh(residence)
    return _residence_to_out(residence)


@app.get("/floors/{floor_id}/stats", response_model=FloorStats)
async def floor_stats(floor_id: int, db: Session = Depends(get_db)) -> FloorStats:
    floor = db.query(FloorORM).filter(FloorORM.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")

    floor_rooms = db.query(RoomORM).filter(RoomORM.floor_id == floor_id).all()
    total_rooms = len(floor_rooms)
    total_capacity = sum(room.capacity for room in floor_rooms)
    total_free_places = sum(room.free_places for room in floor_rooms)
    occupied_places = total_capacity - total_free_places
    occupancy_percent = (occupied_places / total_capacity) * 100 if total_capacity > 0 else 0.0

    return FloorStats(
        floor_id=floor.id,
        total_rooms=total_rooms,
        total_capacity=total_capacity,
        total_free_places=total_free_places,
        occupied_places=occupied_places,
        occupancy_percent=occupancy_percent,
    )
