from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from prometheus_fastapi_instrumentator import Instrumentator

from cmas_shared.observability import CorrelationIdMiddleware, configure_logging

from .database import get_db
from .models import CommentORM, MaintenanceRequestORM

configure_logging("requests_service")

app = FastAPI(
    title="Requests Service",
    description="Сервис управления заявками и обслуживанием",
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
app.add_middleware(CorrelationIdMiddleware, service_name="requests_service")

Instrumentator().instrument(app).expose(app)


class RequestStatus(str, Enum):
    created = "created"
    in_progress = "in_progress"
    done = "done"


class RequestCreate(BaseModel):
    student_id: int = Field(..., ge=1)
    room_id: int = Field(..., ge=1)
    category: str = Field(..., min_length=2)
    description: str = Field(..., min_length=5)


class RequestStatusUpdate(BaseModel):
    status: RequestStatus
    assignee_id: int | None = Field(default=None, ge=1)


class CommentCreate(BaseModel):
    author_id: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)


class Comment(BaseModel):
    id: int
    request_id: int
    author_id: int
    text: str
    created_at: datetime


class MaintenanceRequest(BaseModel):
    id: int
    student_id: int
    room_id: int
    category: str
    description: str
    status: RequestStatus
    assignee_id: int | None = None
    created_at: datetime
    updated_at: datetime


class MaintenanceRequestDetails(MaintenanceRequest):
    comments: list[Comment] = Field(default_factory=list)


def _request_to_out(request_item: MaintenanceRequestORM) -> MaintenanceRequest:
    return MaintenanceRequest(
        id=request_item.id,
        student_id=request_item.student_id,
        room_id=request_item.room_id,
        category=request_item.category,
        description=request_item.description,
        status=RequestStatus(request_item.status),
        assignee_id=request_item.assignee_id,
        created_at=request_item.created_at,
        updated_at=request_item.updated_at,
    )


def _comment_to_out(comment: CommentORM) -> Comment:
    return Comment(
        id=comment.id,
        request_id=comment.request_id,
        author_id=comment.author_id,
        text=comment.text,
        created_at=comment.created_at,
    )


def _get_request_or_404(db: Session, request_id: int) -> MaintenanceRequestORM:
    request_item = (
        db.query(MaintenanceRequestORM)
        .filter(MaintenanceRequestORM.id == request_id)
        .first()
    )
    if not request_item:
        raise HTTPException(status_code=404, detail="Request not found")
    return request_item


def _request_to_details(
    db: Session, request_item: MaintenanceRequestORM
) -> MaintenanceRequestDetails:
    comments = (
        db.query(CommentORM)
        .filter(CommentORM.request_id == request_item.id)
        .order_by(CommentORM.id.asc())
        .all()
    )
    return MaintenanceRequestDetails(
        **_request_to_out(request_item).model_dump(),
        comments=[_comment_to_out(comment) for comment in comments],
    )


@app.get("/")
async def root():
    return {"service": "Requests Service", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/requests", response_model=list[MaintenanceRequest])
async def list_requests(
    status: RequestStatus | None = Query(default=None),
    student_id: int | None = Query(default=None, ge=1),
    room_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> list[MaintenanceRequest]:
    query = db.query(MaintenanceRequestORM)
    if status is not None:
        query = query.filter(MaintenanceRequestORM.status == status.value)
    if student_id is not None:
        query = query.filter(MaintenanceRequestORM.student_id == student_id)
    if room_id is not None:
        query = query.filter(MaintenanceRequestORM.room_id == room_id)

    items = query.order_by(MaintenanceRequestORM.id.asc()).all()
    return [_request_to_out(item) for item in items]


@app.get("/requests/{request_id}", response_model=MaintenanceRequestDetails)
async def get_request(
    request_id: int, db: Session = Depends(get_db)
) -> MaintenanceRequestDetails:
    request_item = _get_request_or_404(db, request_id)
    return _request_to_details(db, request_item)


@app.post("/requests", response_model=MaintenanceRequestDetails, status_code=201)
async def create_request(
    payload: RequestCreate, db: Session = Depends(get_db)
) -> MaintenanceRequestDetails:
    now = datetime.now(timezone.utc)
    request_item = MaintenanceRequestORM(
        student_id=payload.student_id,
        room_id=payload.room_id,
        category=payload.category,
        description=payload.description,
        status=RequestStatus.created.value,
        assignee_id=None,
        created_at=now,
        updated_at=now,
    )
    db.add(request_item)
    db.commit()
    db.refresh(request_item)
    return _request_to_details(db, request_item)


@app.put("/requests/{request_id}/status", response_model=MaintenanceRequestDetails)
async def update_request_status(
    request_id: int,
    payload: RequestStatusUpdate,
    db: Session = Depends(get_db),
) -> MaintenanceRequestDetails:
    request_item = _get_request_or_404(db, request_id)
    request_item.status = payload.status.value
    if payload.assignee_id is not None:
        request_item.assignee_id = payload.assignee_id
    request_item.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(request_item)
    return _request_to_details(db, request_item)


@app.get("/requests/room/{room_id}", response_model=list[MaintenanceRequest])
async def list_requests_by_room(
    room_id: int, db: Session = Depends(get_db)
) -> list[MaintenanceRequest]:
    items = (
        db.query(MaintenanceRequestORM)
        .filter(MaintenanceRequestORM.room_id == room_id)
        .order_by(MaintenanceRequestORM.id.asc())
        .all()
    )
    return [_request_to_out(item) for item in items]


@app.delete("/requests/{request_id}")
async def delete_request(request_id: int, db: Session = Depends(get_db)):
    request_item = _get_request_or_404(db, request_id)
    db.delete(request_item)
    db.commit()
    return {"ok": True}


@app.post("/requests/{request_id}/comments", response_model=MaintenanceRequestDetails)
async def add_comment(
    request_id: int, payload: CommentCreate, db: Session = Depends(get_db)
) -> MaintenanceRequestDetails:
    request_item = _get_request_or_404(db, request_id)
    comment = CommentORM(
        request_id=request_id,
        author_id=payload.author_id,
        text=payload.text,
        created_at=datetime.now(timezone.utc),
    )
    db.add(comment)
    request_item.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(request_item)
    return _request_to_details(db, request_item)
