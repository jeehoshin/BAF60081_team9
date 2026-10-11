"""
공공 API(KOPIS 공연 · 한국관광공사 TourAPI 축제·행사) → activities 테이블 적재.

Render의 Swagger에서 POST /collect로 해도 결과는 같다. 이 스크립트는 로컬에서 돌릴 때 쓴다.

준비:
1. 프로젝트 루트 .env 에 KOPIS_API_KEY, TOUR_API_KEY, DATABASE_URL (+ USE_MEMORY=0)
2. pip install -r backend/requirements.txt

실행 예:
  python scripts/collect_activities.py --dry-run          # 저장 없이 무엇을 받는지만 확인
  python scripts/collect_activities.py                    # 서울+대전, 오늘부터 30일, 저장
  python scripts/collect_activities.py --sources kopis --areas 대전 --days 14
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="공공 API 행사 수집 → activities")
    parser.add_argument("--sources", default="kopis,tour", help="kopis, tour 중 쉼표로 (기본: 둘 다)")
    parser.add_argument("--areas", default="서울,대전", help="서울, 대전 중 쉼표로 (기본: 둘 다)")
    parser.add_argument("--days", type=int, default=30, help="오늘부터 며칠 뒤까지 (기본 30)")
    parser.add_argument("--per-genre", type=int, default=6, help="KOPIS 장르마다 지역별 최대 건수 (기본 6)")
    parser.add_argument("--max-span-days", type=int, default=90, help="이보다 긴 장기 행사 제외, 0=제한 없음 (기본 90)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    args = parser.parse_args()

    from app.collectors import CollectOptions, collect
    from app.config import get_settings

    settings = get_settings()
    try:
        opts = CollectOptions(
            sources=args.sources,
            areas=args.areas,
            days=args.days,
            kopis_per_genre=args.per_genre,
            max_span_days=args.max_span_days,
        )
    except ValueError as exc:
        print(f"[옵션 오류] {exc}")
        return 2

    db = None
    if not args.dry_run:
        if settings.memory_mode:
            print("[중단] 지금 설정은 메모리 DB(USE_MEMORY=1 또는 DATABASE_URL 없음)라 저장해도 사라져요.")
            print("       .env에 DATABASE_URL을 넣고 USE_MEMORY=0으로 하거나, --dry-run으로 확인만 하세요.")
            return 2
        from app.database import SessionLocal, init_db

        init_db()  # 테이블·새 칸(ends_at, external_id 등)이 없으면 만든다
        db = SessionLocal()

    try:
        result = collect(
            db,
            opts,
            kopis_key=settings.kopis_api_key or os.getenv("KOPIS_API_KEY", ""),
            tour_key=settings.tour_api_key or os.getenv("TOUR_API_KEY", ""),
            dry_run=args.dry_run,
        )
    finally:
        if db is not None:
            db.close()

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    failed = [r for r in result["results"] if r["error"]]
    for r in failed:
        print(f"[실패] {r['source']} {r['area']}: {r['error']}")
    print(
        f"done: 수집 {result['collected']}건 · 새로 {result['inserted']} · 갱신 {result['updated']}"
        + (" (dry-run: 저장 안 함)" if args.dry_run else "")
    )
    return 1 if failed and not result["collected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
