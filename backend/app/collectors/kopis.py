"""KOPIS(공연예술통합전산망) 공연 수집.

지역마다 이렇게 부른다.
1. 공연목록 pblprfr        : 장르별로, 수집 기간과 겹치는 공연을 받는다.
2. 공연상세 pblprfr/{mt20id} : 공연시간, 관람료, 공연시설 ID(mt10id), 예매처.
3. 공연시설상세 prfplc/{mt10id}: 주소(→ 구), 위도·경도. 같은 시설은 한 번만 부른다.

응답은 XML이다. <dbs><db>...</db></dbs>
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

from app.collectors.common import (
    AREAS,
    CollectError,
    SourceReport,
    clip,
    end_of,
    gu_from_address,
    https,
    join_parts,
    overlaps,
    parse_ymd,
    start_of,
    to_float,
)

SOURCE = "KOPIS"
BASE_URL = "https://kopis.or.kr/openApi/restful"
PAGE_URL = "https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={id}"
ATTRIBUTION = "출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)"

# shcate 장르코드
GENRES = {
    "AAAA": "연극",
    "GGGA": "뮤지컬",
    "CCCA": "서양음악(클래식)",
    "CCCC": "한국음악(국악)",
    "CCCD": "대중음악",
    "BBBC": "무용",
    "BBBE": "대중무용",
    "EEEB": "서커스/마술",
    "EEEA": "복합",
}

MAX_ROWS = 100  # 목록 한 번에 받을 수 있는 최대 건수
MAX_WINDOW_DAYS = 31  # 한 번에 묻는 기간은 31일 이하로 나눈다

# KOPIS는 1초에 10건쯤 넘게 부르면 HTTP 400 "Request Blocked"로 잠깐 막는다 (2026-10-11 실제 키로 확인, 1초 뒤 풀림).
MIN_INTERVAL = 0.25  # 요청 사이 간격(초). 1초에 4건
MAX_TRIES = 4
RETRY_WAIT = 1.5  # 다시 부르기 전 쉬는 시간(초). 시도할수록 길어진다


def parse_dbs(content: bytes | str) -> list[ET.Element]:
    """<dbs><db>…</db></dbs> 응답에서 db 요소들을 꺼낸다. 오류 응답이면 CollectError."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectError("KOPIS 응답을 읽지 못했어요 (XML이 아님). 잠시 후 다시 시도하세요.") from exc

    for el in root.iter():
        tag = el.tag.lower()
        text = (el.text or "").strip()
        if tag in {"errmsg", "errormsg", "error", "returnauthmsg"} and text:
            raise CollectError(f"KOPIS 오류: {text} (인증키를 확인하세요)")
        if tag == "returncode" and text and text not in {"00", "0"}:
            raise CollectError(f"KOPIS 오류 코드 {text} (인증키를 확인하세요)")
    if root.tag != "dbs":
        raise CollectError(f"KOPIS 응답 형식이 예상과 달라요 (<{root.tag}>).")
    return root.findall("db")


def fields(db: ET.Element) -> dict[str, str]:
    """db 요소의 한 단계 아래 값들을 dict로. 하위 목록(relates 등)은 따로 읽는다."""
    return {child.tag: (child.text or "").strip() for child in db if len(child) == 0}


def booking_sites(db: ET.Element) -> list[str]:
    names = []
    for relate in db.findall("./relates/relate"):
        name = (relate.findtext("relatenm") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def windows(window_from: date, window_to: date) -> list[tuple[date, date]]:
    out = []
    cur = window_from
    while cur <= window_to:
        end = min(window_to, cur + timedelta(days=MAX_WINDOW_DAYS - 1))
        out.append((cur, end))
        cur = end + timedelta(days=1)
    return out


def ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


class _Fetcher:
    def __init__(self, client: httpx.AsyncClient, key: str, concurrency: int = 5):
        self.client = client
        self.key = key
        self.sem = asyncio.Semaphore(concurrency)
        self.pace = asyncio.Lock()
        self.next_at = 0.0

    async def _wait_turn(self) -> None:
        """요청 사이를 MIN_INTERVAL만큼 띄운다."""
        async with self.pace:
            loop = asyncio.get_running_loop()
            delay = self.next_at - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self.next_at = loop.time() + MIN_INTERVAL

    async def get(self, path: str, params: dict | None = None) -> list[ET.Element]:
        """실패하면(연결 오류·5xx·요청 차단) 잠깐 쉬고 다시 부른다."""
        query = {"service": self.key, **(params or {})}
        problem = ""
        for attempt in range(MAX_TRIES):
            if attempt:
                await asyncio.sleep(RETRY_WAIT * attempt)
            try:
                async with self.sem:
                    await self._wait_turn()
                    res = await self.client.get(f"{BASE_URL}/{path}", params=query)
            except httpx.HTTPError as exc:
                problem = f"KOPIS에 연결하지 못했어요 ({type(exc).__name__})"
                continue
            if res.status_code >= 500:
                problem = f"KOPIS 서버 오류 (HTTP {res.status_code})"
                continue
            if res.status_code == 400 and b"Request Blocked" in res.content:
                problem = "KOPIS가 요청이 너무 잦다고 잠깐 막았어요 (Request Blocked). 1~2분 뒤 다시 시도하세요."
                continue
            if res.status_code >= 400:
                raise CollectError(f"KOPIS 요청 실패 (HTTP {res.status_code}). 인증키를 확인하세요.")
            return parse_dbs(res.content)
        raise CollectError(problem)


async def fetch_area(
    client: httpx.AsyncClient,
    key: str,
    area: str,
    window_from: date,
    window_to: date,
    report: SourceReport,
    per_genre: int = 6,
    max_span_days: int = 90,
) -> list[dict]:
    """한 지역의 공연을 activities 행(dict) 목록으로 돌려준다."""
    fetcher = _Fetcher(client, key)
    code = AREAS[area]["code"]

    # 1) 장르별 목록
    picked: dict[str, dict[str, str]] = {}
    for genre in GENRES:
        kept_in_genre = 0
        for seg_from, seg_to in windows(window_from, window_to):
            if kept_in_genre >= per_genre:
                break
            dbs = await fetcher.get(
                "pblprfr",
                {
                    "stdate": ymd(seg_from),
                    "eddate": ymd(seg_to),
                    "cpage": 1,
                    "rows": min(MAX_ROWS, per_genre * 3),
                    "shcate": genre,
                    "signgucode": code,
                },
            )
            for db in dbs:
                if kept_in_genre >= per_genre:
                    break
                item = fields(db)
                report.fetched += 1
                pid = item.get("mt20id")
                if not pid or pid in picked:
                    report.skip("중복·ID 없음")
                    continue
                start, end = parse_ymd(item.get("prfpdfrom")), parse_ymd(item.get("prfpdto"))
                if not start:
                    report.skip("날짜 없음")
                    continue
                end = end or start
                if not overlaps(start, end, window_from, window_to):
                    report.skip("기간 밖")
                    continue
                if item.get("openrun") == "Y":
                    report.skip("오픈런(상시 공연)")
                    continue
                if max_span_days and (end - start).days + 1 > max_span_days:
                    report.skip(f"{max_span_days}일 넘는 장기 공연")
                    continue
                item["_start"], item["_end"] = start.isoformat(), end.isoformat()
                picked[pid] = item
                kept_in_genre += 1

    # 2) 상세 + 3) 시설 (시설은 캐시)
    facility_cache: dict[str, asyncio.Task] = {}

    async def facility(mt10id: str) -> dict[str, str]:
        if mt10id not in facility_cache:
            facility_cache[mt10id] = asyncio.ensure_future(fetcher.get(f"prfplc/{mt10id}"))
        dbs = await facility_cache[mt10id]
        return fields(dbs[0]) if dbs else {}

    async def build(pid: str, item: dict[str, str]) -> dict | None:
        try:
            detail_dbs = await fetcher.get(f"pblprfr/{pid}")
        except CollectError:
            report.skip("상세 조회 실패")
            return None
        if not detail_dbs:
            report.skip("상세 없음")
            return None
        detail = fields(detail_dbs[0])
        sites = booking_sites(detail_dbs[0])

        place_info: dict[str, str] = {}
        if detail.get("mt10id"):
            try:
                place_info = await facility(detail["mt10id"])
            except CollectError:
                place_info = {}
        gu = gu_from_address(place_info.get("adres"), area)
        if not gu:
            report.skip("구를 알 수 없음")
            return None

        start = date.fromisoformat(item["_start"])
        end = date.fromisoformat(item["_end"])
        price = detail.get("pcseguidance")
        description = join_parts(
            item.get("genrenm") or detail.get("genrenm"),
            detail.get("dtguidance") and f"공연시간 {detail['dtguidance']}",
            price and f"관람료 {price}",
            detail.get("prfage") and f"관람연령 {detail['prfage']}",
            detail.get("prfruntime") and f"러닝타임 {detail['prfruntime']}",
            sites and f"예매 {', '.join(sites[:3])}",
            ATTRIBUTION,
        )
        return {
            "external_id": f"KOPIS:{pid}",
            "activity_type": "공연",
            "title": clip(item.get("prfnm") or detail.get("prfnm"), "title"),
            "place": clip(item.get("fcltynm") or place_info.get("fcltynm"), "place"),
            "region": gu,
            "starts_at": start_of(start),
            "ends_at": end_of(end),
            "cost": clip(price, "cost"),
            "description": description,
            "source": SOURCE,
            "lat": to_float(place_info.get("la")),
            "lng": to_float(place_info.get("lo")),
            "source_url": clip(PAGE_URL.format(id=pid), "source_url"),
            "image_url": clip(https(item.get("poster") or detail.get("poster")), "image_url"),
        }

    rows = await asyncio.gather(*(build(pid, item) for pid, item in picked.items()))
    out = [r for r in rows if r and r["title"]]
    report.kept += len(out)
    return out
