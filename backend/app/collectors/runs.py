"""수집 실행 기록(collect_runs) 저장 (기획 3-6).

행사 수집(runner.collect)과 KOPIS 통계 수집(kopis_stats.collect)이 끝날 때 한 줄씩 남긴다.
기록에 실패해도 수집 결과 자체는 돌려줘야 하므로, 여기서 나는 오류는 삼키고 경고만 찍는다.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import CollectRun, now_kst


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def record_run(
    db: Session | None,
    kind: str,
    started_at: datetime,
    summary: dict,
    *,
    trigger: str = "api",
    dry_run: bool = False,
    window_from=None,
    window_to=None,
    collected: int = 0,
    inserted: int = 0,
    updated: int = 0,
    unchanged: int = 0,
    skipped: int = 0,
    error_count: int = 0,
) -> int | None:
    """collect_runs에 한 줄 저장하고 id를 돌려준다. db가 없으면(테스트·dry_run CLI) 아무것도 안 한다."""
    if db is None:
        return None
    try:
        run = CollectRun(
            kind=kind,
            trigger=trigger,
            dry_run=dry_run,
            started_at=started_at,
            finished_at=now_kst(),
            window_from=_to_date(window_from),
            window_to=_to_date(window_to),
            collected=collected,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            skipped=skipped,
            error_count=error_count,
            ok=error_count == 0,
            details=json.dumps(summary, ensure_ascii=False, default=str),
        )
        db.add(run)
        db.commit()
        return run.id
    except Exception as exc:  # noqa: BLE001 - 기록 실패가 수집 결과를 막으면 안 된다
        db.rollback()
        print(f"[collect_runs] 기록 실패: {exc}")
        return None


def run_to_dict(run: CollectRun) -> dict:
    """분석 API 응답용. details(JSON 문자열)는 풀어서 넣는다."""
    try:
        details = json.loads(run.details) if run.details else None
    except ValueError:
        details = None
    seconds = None
    if run.started_at and run.finished_at:
        seconds = round((run.finished_at - run.started_at).total_seconds(), 1)
    return {
        "id": run.id,
        "kind": run.kind,
        "trigger": run.trigger,
        "dry_run": run.dry_run,
        "started_at": run.started_at.isoformat(timespec="seconds") if run.started_at else None,
        "finished_at": run.finished_at.isoformat(timespec="seconds") if run.finished_at else None,
        "seconds": seconds,
        "window": {
            "from": run.window_from.isoformat() if run.window_from else None,
            "to": run.window_to.isoformat() if run.window_to else None,
        },
        "collected": run.collected,
        "inserted": run.inserted,
        "updated": run.updated,
        "unchanged": run.unchanged,
        "skipped": run.skipped,
        "error_count": run.error_count,
        "ok": run.ok,
        "results": (details or {}).get("results") if isinstance(details, dict) else None,
    }
