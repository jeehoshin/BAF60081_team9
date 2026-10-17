import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.common import AREAS, DAEJEON_LAT_MAX, SEOUL_LAT_MIN
from app.collectors.kopis_stats import ATTRIBUTION as KOPIS_ATTRIBUTION
from app.collectors.kopis_stats import NOTICE as KOPIS_NOTICE
from app.collectors.runs import run_to_dict
from app import population as pop
from app.database import get_db
from app.models import Activity, CollectRun, KopisStat, Meetup, Participant, User
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


SINCE_HELP = (
    "이 시각(한국 시간, 예: 2026-10-21T13:00:00) 이후에 생긴 것만 센다. "
    "발표 때 '오늘 QR로 들어온 청중만' 보기용. 비우면 전체."
)


@router.get("/meetups")
def meetup_stats(
    since: datetime | None = Query(None, description=SINCE_HELP),
    db: Session = Depends(get_db),
):
    """모임 수·참여 인원·충원율. since를 주면 그 이후 만든 모임과 그 이후 참여만 센다."""
    meetup_q = db.query(Meetup)
    participant_q = db.query(Participant)
    if since:
        meetup_q = meetup_q.filter(Meetup.created_at >= since)
        participant_q = participant_q.filter(Participant.joined_at >= since)
    meetup_count = meetup_q.count()
    participant_count = participant_q.count()
    capacities = [c[0] for c in meetup_q.with_entities(Meetup.capacity).all()]
    total_capacity = sum(capacities) or 0
    # 충원율은 '그 기간에 만든 모임'의 정원 대비 '그 모임들에 들어온 사람' 비율
    if since and meetup_count:
        ids = [m.meetup_id for m in meetup_q.with_entities(Meetup.meetup_id).all()]
        filled = db.query(Participant).filter(Participant.meetup_id.in_(ids)).count()
    else:
        filled = participant_count
    fill_rate = round(filled / total_capacity * 100, 1) if total_capacity else 0.0
    return {
        "since": since.isoformat(timespec="seconds") if since else None,
        "open_meetups": meetup_count,
        "participants": participant_count,
        "avg_fill_rate_percent": fill_rate,
    }


@router.get("/users")
def user_stats(
    since: datetime | None = Query(None, description=SINCE_HELP),
    db: Session = Depends(get_db),
):
    """이용자 연령대·성별 분포. since를 주면 그 이후 등록한 이용자만 센다."""
    q = db.query(User)
    if since:
        q = q.filter(User.created_at >= since)
    by_age = q.with_entities(User.age_group, func.count(User.user_id)).group_by(User.age_group).all()
    by_gender = q.with_entities(User.gender, func.count(User.user_id)).group_by(User.gender).all()
    return {
        "since": since.isoformat(timespec="seconds") if since else None,
        "total": q.count(),
        "by_age_group": [StatsBucket(key=k or "미상", count=c) for k, c in by_age],
        "by_gender": [StatsBucket(key=k or "미상", count=c) for k, c in by_gender],
    }


# ---------------------------------------------------------------------------
# 지표 G: 구별 인구 10만 명당 활동 수 (서울 vs 대전)
# ---------------------------------------------------------------------------

def city_of(activity: Activity) -> str | None:
    """활동이 서울인지 대전인지. 구 이름으로 정하고, 두 도시에 다 있는 '중구'는 좌표·장소 글자로 가른다."""
    gu = (activity.region or "").strip()
    if not gu:
        return None
    in_seoul = gu in AREAS["서울"]["gu"]
    in_daejeon = gu in AREAS["대전"]["gu"]
    if in_seoul and not in_daejeon:
        return "서울"
    if in_daejeon and not in_seoul:
        return "대전"
    if not in_seoul and not in_daejeon:
        return None
    if activity.lat is not None:
        if activity.lat >= SEOUL_LAT_MIN:
            return "서울"
        if activity.lat <= DAEJEON_LAT_MAX:
            return "대전"
    text = f"{activity.place or ''} {activity.description or ''}"
    if "대전" in text:
        return "대전"
    if "서울" in text:
        return "서울"
    return None


@router.get("/regions")
def region_stats(
    include_ended: bool = Query(True, description="false면 오늘 기준 끝난 행사는 빼고 센다"),
    db: Session = Depends(get_db),
):
    """지표 G. 구별 활동 수를 주민등록 인구로 나눠 '인구 10만 명당 활동 수'로 서울·대전을 비교한다.

    "서울에 많은 건 사람이 많아서"라는 반론에 답하는 지표. 활동 수는 수집된 공연·축제·전시와
    사용자 러닝을 모두 센다. 구를 모르는 활동(region 없음)은 뺀다.
    """
    rows = db.query(Activity).all()
    from app.models import now_kst
    now = now_kst()
    if not include_ended:
        rows = [a for a in rows if _status(a, now) != "ended"]

    counts: dict[str, dict[str, int]] = {"서울": {}, "대전": {}}
    unknown = 0
    for a in rows:
        city = city_of(a)
        if not city:
            unknown += 1
            continue
        counts[city][a.region] = counts[city].get(a.region, 0) + 1

    cities = []
    for city in ("서울", "대전"):
        people = pop.population_of(city)
        total = sum(counts[city].values())
        districts = []
        for gu, gu_pop in pop.DISTRICTS[city].items():
            n = counts[city].get(gu, 0)
            districts.append({"key": gu, "count": n, "population": gu_pop, "per_100k": pop.per_100k(n, gu_pop)})
        districts.sort(key=lambda d: (d["per_100k"] or 0, d["count"]), reverse=True)
        with_any = [d for d in districts if d["count"]]
        cities.append({
            "city": city,
            "population": people,
            "activities": total,
            "per_100k": pop.per_100k(total, people),
            "districts": districts,
            "districts_with_activity": len(with_any),
            "district_total": len(districts),
            "top_district": with_any[0]["key"] if with_any else None,
            # 상위 3개 구에 몇 %가 몰려 있나 (집중도)
            "top3_share": _pct(sum(d["count"] for d in with_any[:3]), total),
        })
    seoul, daejeon = cities
    ratio = (
        round(seoul["per_100k"] / daejeon["per_100k"], 2)
        if seoul["per_100k"] and daejeon["per_100k"] else None
    )
    return {
        "as_of": now.isoformat(timespec="minutes"),
        "include_ended": include_ended,
        "counted": len(rows) - unknown,
        "unknown_region": unknown,
        "cities": cities,
        "highlights": {
            "seoul_per_100k": seoul["per_100k"],
            "daejeon_per_100k": daejeon["per_100k"],
            "seoul_vs_daejeon_ratio": ratio,
            "seoul_total": seoul["activities"],
            "daejeon_total": daejeon["activities"],
        },
        "population_basis": {
            "source": pop.SOURCE,
            "url": pop.SOURCE_URL,
            "month": pop.BASIS_MONTH,
            "note": "구별 활동 수를 그 구의 주민등록 인구로 나눈 값 (외국인 제외). '중구'는 좌표로 서울·대전을 가른다",
        },
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


def collect_run_summary(db: Session, recent: int = 10) -> dict:
    """수집 기록 요약: 종류별 마지막 '실제 저장' 실행과 최근 실행 목록.

    마지막 실행의 출처·지역별 결과(받은 수·남긴 수·뺀 이유별 수·오류)가 데이터 품질 표의 근거가 된다.
    """
    runs = db.query(CollectRun).order_by(CollectRun.started_at.desc(), CollectRun.id.desc()).limit(200).all()
    last: dict[str, dict] = {}
    for r in runs:
        if r.dry_run or r.kind in last:
            continue
        last[r.kind] = run_to_dict(r)
    return {
        "total": db.query(CollectRun).count(),
        "last_activities": last.get("activities"),
        "last_kopis_stats": last.get("kopis_stats"),
        "recent": [run_to_dict(r) for r in runs[:recent]],
    }


@router.get("/collect-runs")
def collect_runs(
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """수집 실행 기록 (기획 3-6). 최근 것부터. 출처·지역별 받은 수·뺀 이유·오류가 들어 있다."""
    return collect_run_summary(db, recent=limit)


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
        "collect_runs": collect_run_summary(db),
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
