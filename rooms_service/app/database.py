from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    host = os.getenv("ROOMS_DB_HOST", "localhost")
    port = os.getenv("ROOMS_DB_PORT", "5432")
    name = os.getenv("ROOMS_DB_NAME", "rooms_db")
    user = os.getenv("ROOMS_DB_USER", "postgres")
    password = os.getenv("ROOMS_DB_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = get_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
