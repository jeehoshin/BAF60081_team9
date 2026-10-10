from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.routers import activities, live, map as map_router, meetups, stats, users
from app.seed import seed_demo_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        # Supabase/로컬 모두: 테이블이 비어 있을 때만 시연용 시드
        seed_demo_data(db)
    finally:
        db.close()
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description=(
        "같이 갈래? — 활동 탐색·모임·채팅·라이브 보드 API. "
        "DB: Supabase(PostgreSQL) · 배포: Render. 클라우드컴퓨팅실습 9조"
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# 로컬 시연·Vercel 프리뷰 호스트 대응: 목록 + 와일드카드
_origins = settings.cors_origin_list
if settings.memory_mode and "*" not in _origins:
    _origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(activities.router)
app.include_router(meetups.router)
app.include_router(stats.router)
app.include_router(live.router)
app.include_router(map_router.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "mode": "memory" if settings.memory_mode else "database",
    }


@app.get("/")
def root():
    return {
        "message": "같이 갈래? API",
        "docs": "/docs",
        "health": "/health",
    }
