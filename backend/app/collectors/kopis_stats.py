"""KOPIS(공연예술통합전산망) 공연 통계 수집 → kopis_stats 테이블.

행사 목록(activities)과 달리 전국 단위 집계다. 분석 페이지의 공연 시장 지표(A 지역, B 장르, C 요일)에 쓴다.

| 종류(kind) | KOPIS API      | 한 줄                     |
|------------|----------------|---------------------------|
| area       | prfstsArea     | 시·도 (권역 소계, 합계 포함) |
| genre      | prfstsCate     | 장르 9개                   |
| day        | prfstsTotal    | 날짜 (ststype=day)         |

알아둘 점 (2026-10-11 영선 키로 실제 응답 확인, 2026년 9월분)
- 응답은 <prfsts><prfst>…</prfst></prfsts>.
- 지역별에는 시·도 줄과 함께 권역 소계(경기/인천, 경상도, 충청도, 전라도)와 '합계' 줄이 섞여 온다.
  소계 = 아래 시·도의 합이라, 시·도 줄만 더하거나 합계 줄로 나눠야 비중이 맞는다. level 칸으로 구분해 저장한다.
- 같은 이름이 API마다 뜻이 다르다.
    지역별: nmrs = 예매 수(취소 포함), nmrcancl = 취소 수, totnmrs = 순 관객 수 (nmrs - nmrcancl)
    일별  : ntssnmrs = 예매 수, cancelnmrs = 취소 수, nmrs = 순 관객 수 (ntssnmrs - cancelnmrs)
    장르별: nmrs만 있고 취소 수가 없다. 원본 값을 audience에 그대로 둔다. 비중(nmrsshr, amountshr)이 함께 온다.
- ststype=dayWeek는 요일별로 묶어 주지 않고 일별과 같은 줄에 요일 이름만 붙인다. 그래서 일별만 받고 요일은 날짜로 계산한다.
- 한 번에 31일까지 물을 수 있어서 달마다 따로 부른다.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.collectors import kopis
from app.collectors.common import CollectError, today_kst
from app.models import KopisStat

SOURCE = "KOPIS 통계"
KINDS = {"area": "prfstsArea", "genre": "prfstsCate", "day": "prfstsTotal"}
KIND_LABELS = {"area": "지역별", "genre": "장르별", "day": "일별"}
REGION_GROUPS = ("경기/인천", "경상도", "충청도", "전라도")  # 권역 소계 줄
TOTAL_LABEL = "합계"
NOTICE = (
    "집계대상: 모든 공연 데이터 전송기관 / 집계 데이터는 공연예술통합전산망 연계기관의 티켓판매시스템에서 "
    "발권된 분량 기준이므로 해당 공연의 전체 관객 수와 차이가 있을 수 있습니다."
)
ATTRIBUTION = "출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)"


def parse_prfsts(content: bytes | str) -> list[dict[str, str]]:
    """<prfsts><prfst>…</prfst></prfsts> → 줄마다 {항목: 값}. 오류 응답이면 CollectError."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectError("KOPIS 통계 응답을 읽지 못했어요 (XML이 아님). 잠시 후 다시 시도하세요.") from exc
    for el in root.iter():
        tag = el.tag.lower()
        text = (el.text or "").strip()
        if tag in {"errmsg", "errormsg", "error", "returnauthmsg"} and text:
            raise CollectError(f"KOPIS 오류: {text} (인증키를 확인하세요)")
        if tag == "returncode" and text and text not in {"00", "0"}:
            raise CollectError(f"KOPIS 오류 코드 {text} (인증키를 확인하세요)")
    if root.tag == "dbs" and len(root) == 0:
        return []
    if root.tag != "prfsts":
        raise CollectError(f"KOPIS 통계 응답 형식이 예상과 달라요 (<{root.tag}>).")
    return [{child.tag: (child.text or "").strip() for child in row} for row in root]


def _int(raw: str | None) -> int | None:
    try:
        return int(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _float(raw: str | None) -> float | None:
    try:
        return float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def area_level(label: str) -> str:
    if label == TOTAL_LABEL:
        return "합계"
    if label in REGION_GROUPS or "/" in label:
        return "권역"
    return "시도"


def to_row(kind: str, item: dict[str, str], period_from: date, period_to: date) -> dict | None:
    """API 한 줄 → kopis_stats 한 행. 이름이 없으면 None."""
    base = {
        "kind": kind,
        "period_from": period_from,
        "period_to": period_to,
        "open_count": _int(item.get("prfprocnt")),
        "show_count": _int(item.get("prfcnt")),
        "performance_count": _int(item.get("prfdtcnt")),
        "amount": _int(item.get("amount")),
        "seats": None,
        "amount_share": None,
        "audience_share": None,
    }
    if kind == "area":
        label = (item.get("area") or "").strip()
        base.update(
            label=label,
            level=area_level(label),
            tickets=_int(item.get("nmrs")),
            cancels=_int(item.get("nmrcancl")),
            audience=_int(item.get("totnmrs")),
            seats=_int(item.get("seatcnt")),
        )
    elif kind == "genre":
        label = (item.get("cate") or "").strip()
        base.update(
            label=label,
            level=None,
            tickets=None,
            cancels=None,
            audience=_int(item.get("nmrs")),
            amount_share=_float(item.get("amountshr")),
            audience_share=_float(item.get("nmrsshr")),
        )
    else:  # day
        raw = (item.get("prfdt") or "").strip()
        try:
            label = datetime.strptime(raw, "%Y%m%d").date().isoformat()
        except ValueError:
            return None
        base.update(
            label=label,
            level=None,
            tickets=_int(item.get("ntssnmrs")),
            cancels=_int(item.get("cancelnmrs")),
            audience=_int(item.get("nmrs")),
        )
    return base if base["label"] else None


def recent_months(today: date, months: int) -> list[tuple[date, date]]:
    """이번 달을 빼고 지난달부터 거꾸로 months개월. 각 (1일, 말일). 오래된 달부터."""
    out = []
    end = today.replace(day=1) - timedelta(days=1)
    for _ in range(months):
        start = end.replace(day=1)
        out.append((start, end))
        end = start - timedelta(days=1)
    return list(reversed(out))


@dataclass
class StatsReport:
    kind: str
    period: str
    fetched: int = 0
    error: str | None = None
    levels: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": KIND_LABELS[self.kind],
            "period": self.period,
            "fetched": self.fetched,
            "levels": self.levels,
            "error": self.error,
        }


async def gather_rows(
    key: str,
    months: int = 3,
    transport: httpx.AsyncBaseTransport | None = None,
    today: date | None = None,
) -> tuple[list[dict], list[StatsReport]]:
    """최근 months개월 통계를 종류·달마다 받는다. 하나가 실패해도 나머지는 받는다."""
    periods = recent_months(today or today_kst(), months)
    rows: list[dict] = []
    reports: list[StatsReport] = []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        transport=transport,
        headers={"User-Agent": "gachi-galae-collector/1.0"},
        follow_redirects=True,
    ) as client:
        fetcher = kopis._Fetcher(client, key.strip(), concurrency=2)

        async def one(kind: str, start: date, end: date) -> None:
            report = StatsReport(kind=kind, period=f"{start:%Y-%m}")
            reports.append(report)
            params = {"stdate": kopis.ymd(start), "eddate": kopis.ymd(end)}
            if kind == "day":
                params["ststype"] = "day"
            try:
                items = await fetcher.get(KINDS[kind], params, parse=parse_prfsts)
            except CollectError as exc:
                report.error = str(exc)
                return
            for item in items:
                row = to_row(kind, item, start, end)
                if row:
                    rows.append(row)
                    report.fetched += 1
                    if row["level"]:
                        report.levels[row["level"]] = report.levels.get(row["level"], 0) + 1

        await asyncio.gather(*(one(kind, s, e) for kind in KINDS for s, e in periods))
    order = list(KINDS)
    reports.sort(key=lambda r: (order.index(r.kind), r.period))
    return rows, reports


def save(db: Session, rows: list[dict], reports: list[StatsReport]) -> int:
    """받은 종류·달은 기존 행을 지우고 새로 넣는다 (다른 테이블이 참조하지 않아서 안전). 넣은 행 수."""
    done = {(r["kind"], r["period_from"], r["period_to"]) for r in rows}
    for kind, start, end in done:
        db.query(KopisStat).filter(
            KopisStat.kind == kind, KopisStat.period_from == start, KopisStat.period_to == end
        ).delete(synchronize_session=False)
    from app.models import now_kst
    now = now_kst()
    for row in rows:
        db.add(KopisStat(**row, collected_at=now))
    db.commit()
    return len(rows)


def collect(
    db: Session | None,
    key: str,
    months: int = 3,
    dry_run: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    today: date | None = None,
) -> dict:
    """KOPIS 통계를 받아 저장하고 요약을 돌려준다."""
    if not key.strip():
        raise CollectError("KOPIS_API_KEY가 없어서 통계를 받을 수 없어요.")
    if not 1 <= months <= 12:
        raise ValueError("months는 1~12 사이여야 해요.")
    rows, reports = asyncio.run(gather_rows(key, months, transport=transport, today=today))
    saved = 0
    if not dry_run and rows:
        if db is None:
            raise ValueError("저장하려면 DB 세션이 필요해요.")
        saved = save(db, rows, reports)
    periods = sorted({(r["period_from"], r["period_to"]) for r in rows})
    seoul = [r for r in rows if r["kind"] == "area" and r["label"] == "서울"]
    total = [r for r in rows if r["kind"] == "area" and r["level"] == "합계"]
    seoul_amount = sum(r["amount"] or 0 for r in seoul)
    total_amount = sum(r["amount"] or 0 for r in total)
    return {
        "dry_run": dry_run,
        "period": {
            "from": periods[0][0].isoformat() if periods else None,
            "to": periods[-1][1].isoformat() if periods else None,
        },
        "collected": len(rows),
        "saved": saved,
        "results": [r.as_dict() for r in reports],
        "check": {
            "seoul_amount_share_percent": round(seoul_amount / total_amount * 100, 1) if total_amount else None,
        },
    }
