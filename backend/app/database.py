from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
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
    ensure_schema()


# 나중에 추가한 칸. create_all은 이미 있는 테이블에 칸을 더하지 않아서,
# Supabase에 예전 테이블이 있으면 여기서 채워 넣는다 (없을 때만, 데이터는 그대로).
_ADDED_COLUMNS = {
    "activities": {
        "ends_at": "TIMESTAMP",
        "external_id": "VARCHAR(64)",
        "source_url": "VARCHAR(512)",
        "image_url": "VARCHAR(512)",
    },
}


def ensure_schema(bind=None) -> list[str]:
    """빠진 칸과 인덱스를 추가하고, 추가한 칸 이름을 돌려준다."""
    bind = bind or engine
    added: list[str] = []
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    with bind.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
        if "activities" in tables:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_activities_external_id "
                    "ON activities (external_id)"
                )
            )
        # Render(UTC)에서 저장된 기존 created_at/joined_at 시각을 KST(+9시간)로 1회 보정
        if bind.dialect.name == "postgresql":
            conn.execute(text("CREATE TABLE IF NOT EXISTS _schema_migrations (name VARCHAR(64) PRIMARY KEY)"))
            done = conn.execute(
                text("SELECT 1 FROM _schema_migrations WHERE name = 'kst_timestamps_v1'")
            ).first()
            if not done:
                for tbl, col in (
                    ("messages", "created_at"),
                    ("participants", "joined_at"),
                    ("users", "created_at"),
                    ("meetups", "created_at"),
                ):
                    if tbl in tables:
                        conn.execute(
                            text(
                                f"UPDATE {tbl} SET {col} = {col} + INTERVAL '9 hours' "
                                f"WHERE {col} <= (NOW() AT TIME ZONE 'UTC') + INTERVAL '5 minutes'"
                            )
                        )
                conn.execute(text("INSERT INTO _schema_migrations (name) VALUES ('kst_timestamps_v1')"))
    if added:
        print(f"[db] 칸 추가: {', '.join(added)}")
    return added
