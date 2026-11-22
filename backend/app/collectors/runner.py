"""공공 API → activities 테이블 수집 실행.

Swagger(POST /collect)와 로컬 스크립트(scripts/collect_activities.py)가 같은 함수를 쓴다.
같은 행사는 external_id('KOPIS:PF302715', 'TOUR:2786391')로 알아보고, 다시 수집하면 새로 만들지 않고 고쳐 쓴다.

상세 설명(detail_text)과 관람 조건(min_age_months·runtime_min)
- KOPIS는 원래 부르던 공연상세에서 함께 꺼낸다 (추가 호출 없음).
- TourAPI·문화정보원은 상세를 따로 불러야 해서, 새 행사이거나 DETAIL_RECHECK_DAYS 안에 확인하지 않은 행사만 부른다.
  매일 자동 수집이 돌아도 호출 수가 거의 늘지 않는다. detail="all"이면 전부 다시, "off"면 상세를 부르지 않는다.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import httpx
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.collectors import culture, kopis, tourapi
from app.collectors.common import AREAS, DEFAULT_AREAS, CollectError, SourceReport, today_kst
from app.collectors.runs import record_run
from app.models import Activity, now_kst

SOURCES = {"kopis": kopis.SOURCE, "tour": tourapi.SOURCE, "culture": culture.SOURCE}

# 다시 수집할 때 고쳐 쓰는 칸
UPDATABLE = (
    "activity_type", "title", "place", "region", "starts_at", "ends_at", "cost",
    "description", "source", "lat", "lng", "source_url", "image_url",
    "min_age_months", "runtime_min",
)
# 상세 조회로 채우는 칸. 이번 수집에서 상세를 부른 행에만 들어 있어서, 없으면 저장된 값을 그대로 둔다
DETAIL_FIELDS = ("detail_text", "detail_source", "text_hash", "intro_images", "detail_checked_at")
DETAIL_MODES = ("new", "all", "off")
DETAIL_RECHECK_DAYS = 30  # 이 기간 안에 확인한 행사는 상세를 다시 부르지 않는다


@dataclass
class CollectOptions:
    sources: tuple[str, ...] = tuple(SOURCES)
    areas: tuple[str, ...] = DEFAULT_AREAS
    days: int = 30  # 오늘부터 며칠 뒤까지
    kopis_per_genre: int = 6  # KOPIS 장르(9개)마다 지역별로 몇 건까지
    max_span_days: int = 90  # 이보다 긴 장기·상설 행사는 뺀다 (0이면 제한 없음)
    # 한국문화정보원 전시만 따로 적용. 전시는 상설·장기 전시도 지금 볼 수 있는 행사라 기본은 제한 없음(0).
    # 홈 화면이 기간 90일 넘는 행사를 "곧 시작하는 행사" 뒤로 보내므로 새 행사를 가리지 않는다.
    culture_max_span_days: int = 0
    # 상세 설명: new = 새 행사·오래 확인 안 한 행사만 (기본), all = 전부 다시, off = 부르지 않음
    detail: str = "new"

    def __post_init__(self) -> None:
        self.sources = parse_choices(self.sources, SOURCES, "sources")
        self.areas = parse_choices(self.areas, AREAS, "areas")
        if not 1 <= self.days <= 60:
            raise ValueError("days는 1~60 사이여야 해요.")
        if not 1 <= self.kopis_per_genre <= 30:
            raise ValueError("kopis_per_genre는 1~30 사이여야 해요.")
        if self.max_span_days < 0:
            raise ValueError("max_span_days는 0 이상이어야 해요.")
        if self.culture_max_span_days < 0:
            raise ValueError("culture_max_span_days는 0 이상이어야 해요.")
        if self.detail not in DETAIL_MODES:
            raise ValueError(f"detail에 쓸 수 있는 값: {', '.join(DETAIL_MODES)} (받은 값: {self.detail})")


def parse_choices(raw, allowed, label: str) -> tuple[str, ...]:
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    picked = tuple(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    unknown = [i for i in picked if i not in allowed]
    if unknown or not picked:
        raise ValueError(f"{label}에 쓸 수 있는 값: {', '.join(allowed)} (받은 값: {raw})")
    return picked


async def gather_rows(
    opts: CollectOptions,
    kopis_key: str = "",
    tour_key: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
    culture_key: str = "",
    fetch_details: bool = False,
    detail_skip: set[str] | None = None,
) -> tuple[list[dict], list[SourceReport], date, date]:
    """fetch_details면 TourAPI·문화정보원 상세 설명도 부른다 (detail_skip에 든 행사는 빼고)."""
    window_from = today_kst()
    window_to = window_from + timedelta(days=opts.days)
    keys = {"kopis": kopis_key.strip(), "tour": tour_key.strip(), "culture": culture_key.strip()}
    env_names = {"kopis": "KOPIS_API_KEY", "tour": "TOUR_API_KEY", "culture": "CULTURE_API_KEY"}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        transport=transport,
        headers={"User-Agent": "gachi-galae-collector/1.0"},
        follow_redirects=True,
    ) as client:

        async def run_source(source: str) -> tuple[list[dict], list[SourceReport]]:
            rows: list[dict] = []
            reports: list[SourceReport] = []
            for area in opts.areas:  # 지역은 차례로 (같은 API에 한꺼번에 몰리지 않게)
                report = SourceReport(source=SOURCES[source], area=area)
                reports.append(report)
                if not keys[source]:
                    report.error = f"{env_names[source]}가 없어서 건너뛰었어요."
                    continue
                try:
                    if source == "kopis":
                        rows += await kopis.fetch_area(
                            client, keys[source], area, window_from, window_to, report,
                            per_genre=opts.kopis_per_genre, max_span_days=opts.max_span_days,
                        )
                    elif source == "culture":
                        rows += await culture.fetch_area(
                            client, keys[source], area, window_from, window_to, report,
                            max_span_days=opts.culture_max_span_days,
                            fetch_details=fetch_details, detail_skip=detail_skip,
                        )
                    else:
                        rows += await tourapi.fetch_area(
                            client, keys[source], area, window_from, window_to, report,
                            max_span_days=opts.max_span_days,
                            fetch_details=fetch_details, detail_skip=detail_skip,
                        )
                except CollectError as exc:
                    report.error = str(exc)
            return rows, reports

        results = await asyncio.gather(*(run_source(s) for s in opts.sources))

    rows: dict[str, dict] = {}
    reports: list[SourceReport] = []
    for source_rows, source_reports in results:
        reports += source_reports
        for row in source_rows:
            rows.setdefault(row["external_id"], row)
    return list(rows.values()), reports, window_from, window_to


def upsert(db: Session, rows: list[dict]) -> tuple[int, int]:
    """(새로 넣은 수, 고친 수). 이미 있는 행사는 id를 그대로 두고 내용만 바꾼다 (모임이 걸려 있을 수 있음)."""
    if not rows:
        return 0, 0
    ids = [r["external_id"] for r in rows]
    existing: dict[str, Activity] = {}
    for i in range(0, len(ids), 500):
        for activity in db.query(Activity).filter(Activity.external_id.in_(ids[i : i + 500])):
            existing[activity.external_id] = activity

    inserted = updated = 0
    for row in rows:
        activity = existing.get(row["external_id"])
        if activity is None:
            db.add(Activity(**row))
            inserted += 1
            continue
        changed = False
        for name in UPDATABLE:
            if getattr(activity, name) != row.get(name):
                setattr(activity, name, row.get(name))
                changed = True
        for name in DETAIL_FIELDS:
            if name in row and name != "detail_checked_at" and getattr(activity, name) != row[name]:
                setattr(activity, name, row[name])
                changed = True
        if "detail_checked_at" in row:
            activity.detail_checked_at = row["detail_checked_at"]  # 확인 시각만 바뀐 건 '고침'으로 세지 않는다
        updated += int(changed)
    db.commit()
    return inserted, updated


def collect(
    db: Session | None,
    opts: CollectOptions,
    kopis_key: str = "",
    tour_key: str = "",
    dry_run: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    culture_key: str = "",
    trigger: str = "api",
) -> dict:
    """수집해서 저장하고 요약을 돌려준다. dry_run이면 저장하지 않는다.

    db가 있으면 dry_run이어도 collect_runs에 실행 기록을 남긴다 (기획 3-6).
    """
    started_at = now_kst()
    fetch_details = opts.detail != "off"
    detail_skip = recently_checked(db) if (fetch_details and opts.detail == "new" and db is not None) else set()
    rows, reports, window_from, window_to = asyncio.run(
        gather_rows(
            opts, kopis_key=kopis_key, tour_key=tour_key, transport=transport, culture_key=culture_key,
            fetch_details=fetch_details, detail_skip=detail_skip,
        )
    )
    inserted = updated = 0
    if not dry_run:
        if db is None:
            raise ValueError("저장하려면 DB 세션이 필요해요.")
        inserted, updated = upsert(db, rows)

    summary = _summary(rows, reports, opts, window_from, window_to, dry_run, inserted, updated)
    if db is not None:
        summary["text_coverage"] = text_coverage(db)
    summary["run_id"] = record_run(
        db, "activities", started_at, summary,
        trigger=trigger, dry_run=dry_run, window_from=window_from, window_to=window_to,
        collected=len(rows), inserted=inserted, updated=updated, unchanged=summary["unchanged"],
        skipped=sum(sum(r.skipped.values()) for r in reports),
        error_count=sum(1 for r in reports if r.error),
    )
    return summary


def recently_checked(db: Session, days: int = DETAIL_RECHECK_DAYS) -> set[str]:
    """최근 days일 안에 상세를 확인한 행사의 external_id."""
    since = now_kst() - timedelta(days=days)
    q = db.query(Activity.external_id).filter(
        Activity.external_id.isnot(None), Activity.detail_checked_at.isnot(None), Activity.detail_checked_at >= since
    )
    return {eid for (eid,) in q}


def text_coverage(db: Session) -> list[dict]:
    """출처별로 설명이 있는 행사 수 (DB 전체). 매일 수집 요약에 남겨 '큰 기관 편향' 같은 변화를 본다."""
    def count_if(cond):
        return func.sum(case((cond, 1), else_=0))

    q = (
        db.query(
            Activity.source,
            func.count(Activity.activity_id),
            count_if(Activity.detail_text.isnot(None)),
            count_if(func.length(Activity.detail_text) >= 200),
            count_if(Activity.min_age_months.isnot(None)),
        )
        .filter(Activity.source != "user")
        .group_by(Activity.source)
        .order_by(Activity.source)
    )
    return [
        {"source": s, "total": int(n), "with_text": int(t or 0), "over_200": int(o or 0), "with_age": int(a or 0)}
        for s, n, t, o, a in q
    ]


def _summary(rows, reports, opts, window_from, window_to, dry_run, inserted, updated) -> dict:
    return {
        "window": {"from": window_from.isoformat(), "to": window_to.isoformat()},
        "options": asdict(opts),
        "dry_run": dry_run,
        "collected": len(rows),
        "inserted": inserted,
        "updated": updated,
        "unchanged": 0 if dry_run else len(rows) - inserted - updated,
        "results": [r.as_dict() for r in reports],
        "sample": [
            {
                "source": r["source"],
                "type": r["activity_type"],
                "region": r["region"],
                "title": r["title"],
                "period": f"{r['starts_at']:%m/%d} ~ {r['ends_at']:%m/%d}",
            }
            for r in sorted(rows, key=lambda r: r["starts_at"])[:10]
        ],
    }
