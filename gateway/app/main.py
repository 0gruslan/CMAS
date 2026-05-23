from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

from cmas_shared.observability import (
    CORRELATION_HEADER,
    CorrelationIdMiddleware,
    configure_logging,
    get_correlation_id,
)

configure_logging("gateway")

app = FastAPI(
    title="API Gateway",
    description="Единая точка входа для всех микросервисов",
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




app.add_middleware(CorrelationIdMiddleware, service_name="gateway")

Instrumentator().instrument(app).expose(app)

USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://users_service:8001")
ROOMS_SERVICE_URL = os.getenv("ROOMS_SERVICE_URL", "http://rooms_service:8002")
REQUESTS_SERVICE_URL = os.getenv("REQUESTS_SERVICE_URL", "http://requests_service:8003")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
bearer_scheme = HTTPBearer(auto_error=False)


class LoginIn(BaseModel):
    email: str = Field(..., examples=["student@example.com"])
    password: str = Field(..., min_length=1, examples=["password123"])


class RegisterIn(BaseModel):
    full_name: str = Field(..., min_length=2, examples=["Иванов Иван Иванович"])
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$", examples=["+79991234567"])
    birth_date: date = Field(..., examples=["2003-05-21"])
    email: str = Field(..., examples=["student@example.com"])
    password: str = Field(..., min_length=6, examples=["password123"])
    role: str = Field(default="student", examples=["student", "admin"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


STAFF_ROLES = {"commandant", "admin"}


def _auth_headers(authorization: str) -> dict[str, str]:
    return {"Authorization": authorization}


def _role(auth: dict[str, Any]) -> str:
    return auth["payload"].get("role", "")


def _current_user_id(auth: dict[str, Any]) -> int:
    return int(auth["payload"]["sub"])


def _is_staff(auth: dict[str, Any]) -> bool:
    return _role(auth) in STAFF_ROLES


def _require_staff(auth: dict[str, Any]) -> None:
    if not _is_staff(auth):
        raise HTTPException(status_code=403, detail="Доступ запрещён: требуется роль commandant или admin")


def _require_staff_or_own(auth: dict[str, Any], resource_user_id: int) -> None:
    if not _is_staff(auth) and _current_user_id(auth) != resource_user_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён: можно просматривать только свои данные")


async def _forward_request(
    method: str,
    base_url: str,
    path: str,
    
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    url = f"{base_url}{path}"
    json_payload = jsonable_encoder(json) if json is not None else None
    forward_headers = dict(headers or {})
    correlation_id = get_correlation_id()
    if correlation_id and correlation_id != "-":
        forward_headers[CORRELATION_HEADER] = correlation_id
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method=method,
                url=url,
                json=json_payload,
                params=params,
                headers=forward_headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gateway internal error: {exc}",
        )

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return response.text


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header is required")
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {
        "payload": payload,
        "authorization": f"Bearer {token}",
    }


@app.get("/")
async def root():
    return {
        "service": "API Gateway",
        "status": "running",
        "services": {
            "users": USERS_SERVICE_URL,
            "rooms": ROOMS_SERVICE_URL,
            "requests": REQUESTS_SERVICE_URL,
        },
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post(
    "/register",
    summary="Регистрация пользователя",
    description="Создаёт пользователя с указанной ролью (`student`/`admin`/`commandant`) без назначения комнаты.",
)
async def register(payload: RegisterIn):
    return await _forward_request(
        "POST",
        USERS_SERVICE_URL,
        "/register",
        json=payload.model_dump(),
    )


@app.post(
    "/login",
    response_model=TokenOut,
    summary="Получить JWT токен",
    description="После логина скопируйте `access_token` и нажмите Authorize в Swagger: `Bearer <token>`.",
)
async def login(payload: LoginIn):
    return await _forward_request(
        "POST", USERS_SERVICE_URL, "/login", json=payload.model_dump()
    )


@app.get("/users", summary="Список пользователей [commandant, admin]")
async def list_users(
    room_id: int | None = Query(default=None),
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    params = {"room_id": room_id} if room_id is not None else None
    return await _forward_request(
        "GET",
        USERS_SERVICE_URL,
        "/users",
        params=params,
        headers=_auth_headers(auth["authorization"]),
    )


@app.get("/users/{user_id}", summary="Получить пользователя [own / commandant / admin]")
async def get_user(
    user_id: int,
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff_or_own(auth, user_id)
    return await _forward_request(
        "GET",
        USERS_SERVICE_URL,
        f"/users/{user_id}",
        headers=_auth_headers(auth["authorization"]),
    )


@app.put("/users/{user_id}/room", summary="Назначить комнату пользователю [commandant, admin]")
async def assign_user_room(
    user_id: int,
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    return await _forward_request(
        "PUT",
        USERS_SERVICE_URL,
        f"/users/{user_id}/room",
        json=payload,
        headers=_auth_headers(auth["authorization"]),
    )


@app.post("/floors", summary="Создать этаж [commandant, admin]")
async def create_floor(
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    return await _forward_request("POST", ROOMS_SERVICE_URL, "/floors", json=payload)


@app.get("/rooms", summary="Список комнат [все]")
async def list_rooms(_: dict[str, Any] = Depends(get_current_user_payload)):
    return await _forward_request("GET", ROOMS_SERVICE_URL, "/rooms")


@app.post("/rooms", summary="Создать комнату [commandant, admin]")
async def create_room(
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    return await _forward_request("POST", ROOMS_SERVICE_URL, "/rooms", json=payload)


@app.get("/rooms/{room_id}", summary="Получить комнату [все]")
async def get_room(room_id: int, _: dict[str, Any] = Depends(get_current_user_payload)):
    return await _forward_request("GET", ROOMS_SERVICE_URL, f"/rooms/{room_id}")


@app.post("/rooms/assign", summary="Заселить студента [commandant, admin]")
async def room_assign(
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    residence = await _forward_request("POST", ROOMS_SERVICE_URL, "/rooms/assign", json=payload)

    # Best-effort synchronization with users service.
    try:
        await _forward_request(
            "PUT",
            USERS_SERVICE_URL,
            f"/users/{payload['student_id']}/room",
            json={"room_id": payload["room_id"]},
            headers=_auth_headers(auth["authorization"]),
        )
    except HTTPException as exc:
        if exc.status_code >= 500:
            raise

    return residence


@app.post("/rooms/evict", summary="Выселить студента [commandant, admin]")
async def room_evict(
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    residence = await _forward_request("POST", ROOMS_SERVICE_URL, "/rooms/evict", json=payload)

    try:
        await _forward_request(
            "PUT",
            USERS_SERVICE_URL,
            f"/users/{payload['student_id']}/room",
            json={"room_id": None},
            headers=_auth_headers(auth["authorization"]),
        )
    except HTTPException as exc:
        if exc.status_code >= 500:
            raise

    return residence


@app.get("/floors/{floor_id}/stats", summary="Статистика этажа [все]")
async def floor_stats(
    floor_id: int,
    _: dict[str, Any] = Depends(get_current_user_payload),
):
    return await _forward_request("GET", ROOMS_SERVICE_URL, f"/floors/{floor_id}/stats")


@app.get("/requests", summary="Список заявок [student — только свои, commandant/admin — все]")
async def list_requests(
    status_value: str | None = Query(default=None, alias="status"),
    student_id: int | None = Query(default=None),
    room_id: int | None = Query(default=None),
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    # Студент видит только свои заявки — принудительно выставляем фильтр
    if not _is_staff(auth):
        student_id = _current_user_id(auth)

    params = {
        "status": status_value,
        "student_id": student_id,
        "room_id": room_id,
    }
    params = {key: value for key, value in params.items() if value is not None}
    return await _forward_request("GET", REQUESTS_SERVICE_URL, "/requests", params=params)


@app.get("/requests/{request_id}", summary="Получить заявку [все]")
async def get_request(
    request_id: int,
    _: dict[str, Any] = Depends(get_current_user_payload),
):
    return await _forward_request("GET", REQUESTS_SERVICE_URL, f"/requests/{request_id}")


@app.delete("/requests/{request_id}", summary="Удалить заявку [commandant, admin]")
async def delete_request(
    request_id: int,
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    await _forward_request("DELETE", REQUESTS_SERVICE_URL, f"/requests/{request_id}")


@app.post("/requests", summary="Создать заявку [все]")
async def create_request(
    payload: dict[str, Any],
    _: dict[str, Any] = Depends(get_current_user_payload),
):
    return await _forward_request("POST", REQUESTS_SERVICE_URL, "/requests", json=payload)


@app.put("/requests/{request_id}/status", summary="Изменить статус заявки [commandant, admin]")
async def update_request_status(
    request_id: int,
    payload: dict[str, Any],
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff(auth)
    return await _forward_request(
        "PUT",
        REQUESTS_SERVICE_URL,
        f"/requests/{request_id}/status",
        json=payload,
    )


@app.get("/requests/room/{room_id}", summary="Заявки по комнате [все]")
async def list_requests_by_room(
    room_id: int,
    _: dict[str, Any] = Depends(get_current_user_payload),
):
    return await _forward_request("GET", REQUESTS_SERVICE_URL, f"/requests/room/{room_id}")


@app.post("/requests/{request_id}/comments", summary="Добавить комментарий [все]")
async def add_comment(
    request_id: int,
    payload: dict[str, Any],
    _: dict[str, Any] = Depends(get_current_user_payload),
):
    return await _forward_request(
        "POST",
        REQUESTS_SERVICE_URL,
        f"/requests/{request_id}/comments",
        json=payload,
    )


@app.get("/profile/{user_id}", summary="Профиль пользователя [own / commandant / admin]")
async def get_profile(
    user_id: int,
    auth: dict[str, Any] = Depends(get_current_user_payload),
):
    _require_staff_or_own(auth, user_id)
    user = await _forward_request(
        "GET",
        USERS_SERVICE_URL,
        f"/users/{user_id}",
        headers=_auth_headers(auth["authorization"]),
    )

    room = None
    room_id = user.get("room_id")
    if room_id is not None:
        room = await _forward_request("GET", ROOMS_SERVICE_URL, f"/rooms/{room_id}")

    requests = await _forward_request(
        "GET",
        REQUESTS_SERVICE_URL,
        "/requests",
        params={"student_id": user_id},
    )

    return {
        "user": user,
        "room": room,
        "requests": requests,
    }
