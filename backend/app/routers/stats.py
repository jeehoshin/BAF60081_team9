import re
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.kopis_stats import ATTRIBUTION as KOPIS_ATTRIBUTION
from app.collectors.kopis_stats import NOTICE as KOPIS_NOTICE
from app import population as pop
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
        # 인구 10만 명당 (집계기간 합계 기준). "서울은 사람이 많아서 그런 것 아니냐"에 답하는 지표
        people = pop.population_of(a["key"])
        a["population"] = people
        a["amount_per_100k"] = pop.per_100k(a["amount"], people)
        a["performance_per_100k"] = pop.per_100k(a["performance_count"], people)
        a["audience_per_100k"] = pop.per_100k(a["audience"], people)

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
            "seoul_amount_per_100k": seoul.get("amount_per_100k"),
            "daejeon_amount_per_100k": daejeon.get("amount_per_100k"),
            "seoul_performance_per_100k": seoul.get("performance_per_100k"),
            "daejeon_performance_per_100k": daejeon.get("performance_per_100k"),
            "seoul_audience_per_100k": seoul.get("audience_per_100k"),
            "daejeon_audience_per_100k": daejeon.get("audience_per_100k"),
            "national_amount_per_100k": pop.per_100k(total_amount, pop.NATIONAL_TOTAL),
            "national_performance_per_100k": pop.per_100k(total_perf, pop.NATIONAL_TOTAL),
        },
        "population_basis": {
            "source": pop.SOURCE,
            "url": pop.SOURCE_URL,
            "month": pop.BASIS_MONTH,
            "note": "인구 10만 명당 값은 집계기간 전체 합계를 시·도 주민등록 인구로 나눈 값",
        },
        "notice": (
            f"집계기간: {period_from:%Y.%m.%d} ~ {period_to:%Y.%m.%d} "
            f"(최종집계 {collected_at:%Y.%m.%d}) / {KOPIS_NOTICE}"
        ),
        "attribution": KOPIS_ATTRIBUTION,
    }


# ---------------------------------------------------------------------------
# 데이터 품질: 출처별 수집 건수, 빈 칸 비율, 진행 상태, 출처 간 중복 후보
# ---------------------------------------------------------------------------

PUBLIC_SOURCES = ("KOPIS", "한국관광공사", "한국문화정보원")
# [대전], (10월)처럼 지역·회차를 적은 괄호만 지운다. 《전시명》·〈작품명〉은 제목이라 남긴다.
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_NOISE = re.compile(r"20\d\d|제\s*\d+\s*회|[^0-9a-z가-힣]")


def normalize_title(title: str | None) -> str:
    """중복 비교용 제목: [지역]·(회차) 괄호, 연도, '제N회', 공백·기호를 지우고 소문자로."""
    if not title:
        return ""
    t = _BRACKETS.sub(" ", title.lower())
    return _NOISE.sub("", t)


def _same_title(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and short in long_


def _overlaps(a: Activity, b: Activity) -> bool:
    if not a.starts_at or not b.starts_at:
        return False
    a_end = a.ends_at or a.starts_at
    b_end = b.ends_at or b.starts_at
    return a.starts_at.date() <= b_end.date() and b.starts_at.date() <= a_end.date()


def find_cross_source_duplicates(rows: list[Activity]) -> list[dict]:
    """서로 다른 공공 API 출처에서 같은 행사로 보이는 짝.

    기준: 정리한 제목이 같거나 한쪽이 다른 쪽을 포함(4글자 이상) + 기간이 하루라도 겹침
    + 구(region)가 같음(둘 다 있을 때). 사람이 최종 확인하도록 '후보'로 돌려준다.
    """
    items = [(r, normalize_title(r.title)) for r in rows if r.source in PUBLIC_SOURCES]
    pairs = []
    for i, (a, ta) in enumerate(items):
        for b, tb in items[i + 1:]:
            if a.source == b.source:
                continue
            if a.region and b.region and a.region != b.region:
                continue
            if _same_title(ta, tb) and _overlaps(a, b):
                pairs.append({
                    "a": {"activity_id": a.activity_id, "source": a.source, "title": a.title, "region": a.region},
                    "b": {"activity_id": b.activity_id, "source": b.source, "title": b.title, "region": b.region},
                })
    return pairs


def _status(a: Activity, now: datetime) -> str:
    if not a.starts_at:
        return "unknown"
    end = a.ends_at or a.starts_at
    if end.date() < now.date():
        return "ended"
    if a.starts_at.date() > now.date():
        return "upcoming"
    return "ongoing"


@router.get("/quality")
def data_quality(db: Session = Depends(get_db)):
    """데이터 품질 지표 (분석 페이지·발표용).

    - 출처별 수집 건수, 이미지·좌표·장소가 빈 비율
    - 진행 중·예정·종료 행사 비율 (오늘 기준)
    - 서로 다른 공공 API 출처 간 중복 후보 건수와 목록
    """
    rows = db.query(Activity).all()
    from app.models import now_kst
    now = now_kst()

    def summarize(items: list[Activity]) -> dict:
        n = len(items)
        status_counts = {"ongoing": 0, "upcoming": 0, "ended": 0, "unknown": 0}
        for a in items:
            status_counts[_status(a, now)] += 1
        no_image = sum(1 for a in items if not a.image_url)
        no_coord = sum(1 for a in items if a.lat is None or a.lng is None)
        no_place = sum(1 for a in items if not a.place)
        return {
            "count": n,
            "image_missing": no_image,
            "image_missing_pct": _pct(no_image, n),
            "coord_missing": no_coord,
            "coord_missing_pct": _pct(no_coord, n),
            "place_missing": no_place,
            "place_missing_pct": _pct(no_place, n),
            "status": status_counts,
            "status_pct": {k: _pct(v, n) for k, v in status_counts.items()},
        }

    by_source: dict[str, list[Activity]] = {}
    for a in rows:
        by_source.setdefault(a.source or "미상", []).append(a)
    sources = [
        {"source": name, **summarize(items)}
        for name, items in sorted(by_source.items(), key=lambda kv: len(kv[1]), reverse=True)
    ]
    legacy = [s["source"] for s in sources if s["source"] not in PUBLIC_SOURCES and s["source"] != "user"]

    duplicates = find_cross_source_duplicates(rows)
    public_count = sum(1 for a in rows if a.source in PUBLIC_SOURCES)
    return {
        "as_of": now.isoformat(timespec="minutes"),
        "total": summarize(rows),
        "by_source": sources,
        "cross_source_duplicates": {
            "count": len(duplicates),
            "public_total": public_count,
            "pct_of_public": _pct(len(duplicates), public_count),
            "rule": "제목([ ]·( ) 괄호·연도·기호 제외)이 같거나 포함 관계(4글자 이상) + 기간 겹침 + 같은 구",
            "pairs": duplicates[:30],
        },
        "legacy_sources": legacy,
        "notes": (
            [f"{', '.join(legacy)} 출처는 공공 API·사용자 등록이 아닌 예전 시드 자료라 정리 대상 (docs/cleanup_test_data.sql)"]
            if legacy else []
        ),
    }
