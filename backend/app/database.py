from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(url: str) -> str:
    """Supabase URI에 sslmode가 없으면 붙인다."""
    if not url:
        return url
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _make_engine():
    settings = get_settings()
    if settings.memory_mode or not settings.database_url:
        # 로컬 단독 시연용. 팀 공유·발표는 Supabase(DATABASE_URL) 사용.
        if not settings.memory_mode and not settings.database_url:
            print("[warn] DATABASE_URL 없음 → 인메모리 모드로 기동. 팀 시연 전 Supabase URI를 넣으세요.")
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    url = _normalize_database_url(settings.database_url)
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
