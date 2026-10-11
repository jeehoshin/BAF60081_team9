from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.kopis_stats import ATTRIBUTION as KOPIS_ATTRIBUTION
from app.collectors.kopis_stats import NOTICE as KOPIS_NOTICE
from app.database import get_db
from app.models import Activity, KopisStat, Meetup, Participant, User
from app.schemas import StatsBucket

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/activities")
def activity_stats(db: Session = Depends(get_db)):
    by_region = (
        db.query(Activity.region, func.count(Activity.activity_id))
        .group_by(Activity.region)
        .all()
    )
    by_type = (
        db.query(Activity.activity_type, func.count(Activity.activity_id))
        .group_by(Activity.activity_type)
        .all()
    )
    by_source = (
        db.query(Activity.source, func.count(Activity.activity_id))
        .group_by(Activity.source)
        .all()
    )
    return {
        "total": db.query(Activity).count(),
        "by_region": [StatsBucket(key=k or "미상", count=c) for k, c in by_region],
        "by_type": [StatsBucket(key=k or "미상", count=c) for k, c in by_type],
        "by_source": [StatsBucket(key=k or "미상", count=c) for k, c in by_source],
    }


@router.get("/meetups")
def meetup_stats(db: Session = Depends(get_db)):
    meetup_count = db.query(Meetup).count()
    participant_count = db.query(Participant).count()
    capacities = db.query(Meetup.capacity).all()
    total_capacity = sum(c[0] for c in capacities) or 0
    fill_rate = round(participant_count / total_capacity * 100, 1) if total_capacity else 0.0
    return {
        "open_meetups": meetup_count,
        "participants": participant_count,
        "avg_fill_rate_percent": fill_rate,
    }


@router.get("/users")
def user_stats(db: Session = Depends(get_db)):
    by_age = db.query(User.age_group, func.count(User.user_id)).group_by(User.age_group).all()
    by_gender = db.query(User.gender, func.count(User.user_id)).group_by(User.gender).all()
    return {
        "total": db.query(User).count(),
        "by_age_group": [StatsBucket(key=k or "미상", count=c) for k, c in by_age],
        "by_gender": [StatsBucket(key=k or "미상", count=c) for k, c in by_gender],
    }


WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


@router.get("/kopis")
def kopis_stats(db: Session = Depends(get_db)):
    """KOPIS 공연 통계 (전국). 분석 페이지 지표 A(시·도별), B(장르별), C(요일별).

    여러 달을 받았으면 합쳐서 보여 준다. 비중은 합계 줄(또는 장르 합)로 나눈 값이다.
    """
    rows = db.query(KopisStat).all()
    if not rows:
        return {"available": False, "message": "KOPIS 통계가 아직 없어요. POST /collect/kopis-stats로 받아 주세요."}

    period_from = min(r.period_from for r in rows)
    period_to = max(r.period_to for r in rows)
    collected_at = max(r.collected_at for r in rows if r.collected_at)

    # A. 시·도별: 시도 줄만 더하고, 비중은 합계 줄로 나눈다
    total_amount = sum(r.amount or 0 for r in rows if r.kind == "area" and r.level == "합계")
    total_perf = sum(r.performance_count or 0 for r in rows if r.kind == "area" and r.level == "합계")
    areas: dict[str, dict] = {}
    for r in rows:
        if r.kind != "area" or r.level != "시도":
            continue
        a = areas.setdefault(r.label, {"key": r.label, "amount": 0, "performance_count": 0, "audience": 0})
        a["amount"] += r.amount or 0
        a["performance_count"] += r.performance_count or 0
        a["audience"] += r.audience or 0
    by_area = sorted(areas.values(), key=lambda a: a["amount"], reverse=True)
    for a in by_area:
        a["amount_share"] = _pct(a["amount"], total_amount)
        a["performance_share"] = _pct(a["performance_count"], total_perf)

    # B. 장르별: 상연 횟수 비중과 판매액 비중을 나란히
    genres: dict[str, dict] = {}
    for r in rows:
        if r.kind != "genre":
            continue
        g = genres.setdefault(r.label, {"key": r.label, "amount": 0, "performance_count": 0})
        g["amount"] += r.amount or 0
        g["performance_count"] += r.performance_count or 0
    g_amount = sum(g["amount"] for g in genres.values())
    g_perf = sum(g["performance_count"] for g in genres.values())
    by_genre = sorted(genres.values(), key=lambda g: g["amount"], reverse=True)
    for g in by_genre:
        g["amount_share"] = _pct(g["amount"], g_amount)
        g["performance_share"] = _pct(g["performance_count"], g_perf)

    # C. 요일별: 일별 줄을 요일로 묶어 하루 평균
    days: dict[int, list[KopisStat]] = {}
    for r in rows:
        if r.kind != "day":
            continue
        try:
            wd = date.fromisoformat(r.label).weekday()
        except ValueError:
            continue
        days.setdefault(wd, []).append(r)
    by_weekday = []
    for wd in range(7):
        items = days.get(wd, [])
        n = len(items)
        by_weekday.append({
            "key": WEEKDAYS[wd],
            "days": n,
            "avg_performance_count": round(sum(i.performance_count or 0 for i in items) / n, 1) if n else 0,
            "avg_audience": round(sum(i.audience or 0 for i in items) / n) if n else 0,
            "avg_amount": round(sum(i.amount or 0 for i in items) / n) if n else 0,
        })
    day_audience = sum(r.audience or 0 for r in rows if r.kind == "day")
    weekend_audience = sum(i.audience or 0 for wd in (5, 6) for i in days.get(wd, []))

    seoul = areas.get("서울", {})
    daejeon = areas.get("대전", {})
    return {
        "available": True,
        "period": {"from": period_from.isoformat(), "to": period_to.isoformat()},
        "collected_at": collected_at.isoformat() if collected_at else None,
        "by_area": by_area,
        "by_genre": by_genre,
        "by_weekday": by_weekday,
        "highlights": {
            "seoul_amount_share": seoul.get("amount_share"),
            "seoul_performance_share": seoul.get("performance_share"),
            "daejeon_amount_share": daejeon.get("amount_share"),
            "daejeon_performance_share": daejeon.get("performance_share"),
            "weekend_audience_share": _pct(weekend_audience, day_audience),
        },
        "notice": (
            f"집계기간: {period_from:%Y.%m.%d} ~ {period_to:%Y.%m.%d} "
            f"(최종집계 {collected_at:%Y.%m.%d}) / {KOPIS_NOTICE}"
        ),
        "attribution": KOPIS_ATTRIBUTION,
    }
