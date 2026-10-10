"""
공공 API → activities 테이블 적재 스크립트 골격.

사용 전:
1. 프로젝트 루트에 .env 작성 (TOUR_API_KEY, KOPIS_API_KEY, CULTURE_API_KEY, DATABASE_URL)
2. docs/db_schema.sql 로 테이블 생성
3. 후보 API 호출 테스트 후 파싱 로직을 채운다

실행 예:
  python scripts/collect_activities.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")


def fetch_tour_api() -> list[dict]:
    """한국관광공사 행사정보 등 — 호출 테스트 후 구현."""
    key = os.getenv("TOUR_API_KEY", "")
    if not key:
        print("[skip] TOUR_API_KEY 없음")
        return []
    # TODO: apis.data.go.kr/B551011/KorService2 호출·파싱
    return []


def fetch_kopis() -> list[dict]:
    key = os.getenv("KOPIS_API_KEY", "")
    if not key:
        print("[skip] KOPIS_API_KEY 없음")
        return []
    # TODO: KOPIS XML 파싱
    return []


def fetch_culture() -> list[dict]:
    key = os.getenv("CULTURE_API_KEY", "")
    if not key:
        print("[skip] CULTURE_API_KEY 없음")
        return []
    # TODO: 한국문화정보원 cultureinfo 파싱
    return []


def upsert_activities(rows: list[dict]) -> int:
    """DATABASE_URL이 있으면 Supabase에 적재. 없으면 건수만 출력."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print(f"[dry-run] {len(rows)}건 (DATABASE_URL 없음)")
        return 0

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Activity
    from app.database import Base

    engine = create_engine(db_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    n = 0
    try:
        for row in rows:
            db.add(Activity(**row, source="API"))
            n += 1
        db.commit()
    finally:
        db.close()
    return n


def main() -> None:
    rows: list[dict] = []
    rows.extend(fetch_tour_api())
    rows.extend(fetch_kopis())
    rows.extend(fetch_culture())
    saved = upsert_activities(rows)
    print(f"done: collected={len(rows)}, saved={saved}")


if __name__ == "__main__":
    main()
