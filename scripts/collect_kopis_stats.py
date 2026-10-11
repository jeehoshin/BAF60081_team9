"""
KOPIS 공연 통계(시·도별 · 장르별 · 일별, 전국) → kopis_stats 테이블.

Render의 Swagger에서 POST /collect/kopis-stats로 해도 결과는 같다. 이 스크립트는 로컬에서 돌릴 때 쓴다.

준비:
1. 프로젝트 루트 .env 에 KOPIS_API_KEY, DATABASE_URL (+ USE_MEMORY=0)
2. pip install -r backend/requirements.txt

실행 예:
  python scripts/collect_kopis_stats.py --dry-run          # 저장 없이 무엇을 받는지만 확인
  python scripts/collect_kopis_stats.py                    # 지난 3개월 저장
  python scripts/collect_kopis_stats.py --months 1 --dry-run
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
    parser = argparse.ArgumentParser(description="KOPIS 공연 통계 수집 → kopis_stats")
    parser.add_argument("--months", type=int, default=3, help="지난달부터 거꾸로 몇 달 (기본 3, 이번 달 제외)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    args = parser.parse_args()

    from app.collectors import kopis_stats
    from app.collectors.common import CollectError
    from app.config import get_settings

    settings = get_settings()
    key = settings.kopis_api_key or os.getenv("KOPIS_API_KEY", "")

    db = None
    if not args.dry_run:
        if settings.memory_mode:
            print("[중단] 지금 설정은 메모리 DB(USE_MEMORY=1 또는 DATABASE_URL 없음)라 저장해도 사라져요.")
            print("       .env에 DATABASE_URL을 넣고 USE_MEMORY=0으로 하거나, --dry-run으로 확인만 하세요.")
            return 2
        from app.database import SessionLocal, init_db

        init_db()  # kopis_stats 테이블이 없으면 만든다
        db = SessionLocal()

    try:
        result = kopis_stats.collect(db, key, months=args.months, dry_run=args.dry_run)
    except (CollectError, ValueError) as exc:
        print(f"[오류] {exc}")
        return 2
    finally:
        if db is not None:
            db.close()

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    failed = [r for r in result["results"] if r["error"]]
    for r in failed:
        print(f"[실패] {r['label']} {r['period']}: {r['error']}")
    share = result["check"]["seoul_amount_share_percent"]
    print(
        f"done: {result['period']['from']} ~ {result['period']['to']} · 받은 줄 {result['collected']} · 저장 {result['saved']}"
        + (f" · 서울 판매액 비중 {share}%" if share is not None else "")
        + (" (dry-run: 저장 안 함)" if args.dry_run else "")
    )
    return 1 if failed and not result["collected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
