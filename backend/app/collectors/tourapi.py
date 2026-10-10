"""한국관광공사 TourAPI(국문 관광정보 서비스_GW, KorService2) 행사정보 수집.

searchFestival2(행사정보조회) 한 가지만 쓴다. 목록에 주소·좌표·기간·대표이미지가 다 있어서
상세 조회 없이 저장할 수 있다 (개발계정 일 1,000건 한도를 아끼려는 것).

알아둘 점 (2026-09 기준 실측 사례)
- 지역 필터는 areaCode가 아니라 lDongRegnCd(법정동 시도코드)로 건다. 법정동 체계로 옮겨 가면서
  areacode가 빈 값인 콘텐츠가 많아져, areaCode로 거르면 상당수가 조용히 빠진다.
- 분류는 cat2보다 lclsSystm2(EV01 축제 / EV02 공연 / EV03 행사)가 채워져 온다.
- 인증키가 틀리면 JSON이 아니라 XML 오류가 온다. 0건이면 items가 빈 문자열("")이다.
- mapx가 경도, mapy가 위도다.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, timedelta
from urllib.parse import unquote

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

SOURCE = "한국관광공사"
BASE_URL = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
ATTRIBUTION = "출처: 한국관광공사 TourAPI"
PAGE_SIZE = 100
MAX_PAGES = 15  # 지역당 최대 1,500건까지 넘겨 본다 (하루 1,000건 한도 안에서 넉넉함)

_ERROR_HINTS = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "인증키가 등록되지 않았어요. 활용신청 승인 직후라면 1~2시간 뒤에 다시 해 보고, 공공데이터포털의 'Decoding' 키를 넣었는지 확인하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "오늘 호출 한도(개발계정 1,000건)를 넘었어요. 내일 다시 하세요.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 인증키로 'KorService2' 활용신청이 안 되어 있어요. 공공데이터포털에서 활용신청을 확인하세요.",
}

_EXHIBITION_WORDS = ("전시", "展", "아트페어", "비엔날레", "특별전", "기획전", "사진전", "미술전", "초대전", "개인전")


def normalize_key(key: str) -> str:
    """'Encoding' 키(%2B 등)를 넣어도 동작하게 한 번 풀어 둔다. httpx가 다시 인코딩한다."""
    key = key.strip()
    return unquote(key) if "%" in key else key


def parse_page(text: str) -> tuple[list[dict], int]:
    """응답 본문 → (item 목록, totalCount). 오류면 CollectError."""
    body_text = text.strip()
    if body_text.startswith("<"):
        found = re.search(r"<returnAuthMsg>([^<]+)</returnAuthMsg>", body_text) or re.search(
            r"<errMsg>([^<]+)</errMsg>", body_text
        )
        msg = found.group(1).strip() if found else "XML 오류 응답"
        raise CollectError(f"TourAPI 오류: {msg}. {_ERROR_HINTS.get(msg, '인증키와 활용신청 상태를 확인하세요.')}")
    try:
        data = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise CollectError("TourAPI 응답을 읽지 못했어요 (JSON이 아님).") from exc

    if "response" not in data:  # 파라미터 오류는 감싸지 않은 JSON으로 온다
        raise CollectError(f"TourAPI 오류 {data.get('resultCode')}: {data.get('resultMsg')}")
    header = data["response"].get("header") or {}
    if header.get("resultCode") not in (None, "0000", "00"):
        raise CollectError(f"TourAPI 오류 {header.get('resultCode')}: {header.get('resultMsg')}")

    body = data["response"].get("body") or {}
    total = int(body.get("totalCount") or 0)
    items = body.get("items")
    if not items or isinstance(items, str):
        return [], total
    item = items.get("item") or []
    if isinstance(item, dict):
        item = [item]
    return item, total


def activity_type_of(item: dict) -> str:
    """우리 유형(공연·축제·전시·러닝) 중 하나로 바꾼다. 행사(EV03)는 전시가 아니면 축제로 둔다."""
    lcls2 = (item.get("lclsSystm2") or "").strip()
    cat2 = (item.get("cat2") or "").strip()
    cat3 = (item.get("cat3") or "").strip()
    title = item.get("title") or ""
    if lcls2 == "EV02" or (not lcls2 and cat2 == "A0208" and cat3 != "A02080500"):
        return "공연"
    if cat3 == "A02080500" or any(word in title for word in _EXHIBITION_WORDS):
        return "전시"
    return "축제"


def _label(item: dict) -> str | None:
    return {"EV01": "축제", "EV02": "공연", "EV03": "행사"}.get((item.get("lclsSystm2") or "").strip())


def _plain(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", text).split()) or None


def to_row(item: dict, area: str, window_from: date, window_to: date, max_span_days: int, report: SourceReport) -> dict | None:
    content_id = (item.get("contentid") or "").strip()
    title = (item.get("title") or "").strip()
    if not content_id or not title:
        report.skip("ID·제목 없음")
        return None
    start = parse_ymd(item.get("eventstartdate"))
    if not start:
        report.skip("날짜 없음")
        return None
    end = parse_ymd(item.get("eventenddate")) or start
    if not overlaps(start, end, window_from, window_to):
        report.skip("기간 밖")
        return None
    if max_span_days and (end - start).days + 1 > max_span_days:
        report.skip(f"{max_span_days}일 넘는 장기 행사")
        return None

    info = AREAS[area]
    regn = (item.get("lDongRegnCd") or "").strip()
    if regn and regn != info["code"]:
        report.skip("다른 지역")
        return None
    gu = gu_from_address(item.get("addr1"), area) or info["ldong_signgu"].get((item.get("lDongSignguCd") or "").strip())
    if not gu:
        report.skip("구를 알 수 없음")
        return None

    period = start.strftime("%Y.%m.%d") + ("" if end == start else " ~ " + end.strftime("%Y.%m.%d"))
    tel = _plain(item.get("tel"))
    return {
        "external_id": f"TOUR:{content_id}",
        "activity_type": activity_type_of(item),
        "title": clip(title, "title"),
        "place": clip(join_parts(item.get("addr1"), item.get("addr2"), sep=" "), "place"),
        "region": gu,
        "starts_at": start_of(start),
        "ends_at": end_of(end),
        "cost": None,
        "description": join_parts(_label(item), f"기간 {period}", tel and f"문의 {tel}", ATTRIBUTION),
        "source": SOURCE,
        "lat": to_float(item.get("mapy")),
        "lng": to_float(item.get("mapx")),
        "source_url": None,
        "image_url": clip(https(item.get("firstimage") or item.get("firstimage2")), "image_url"),
    }


async def fetch_area(
    client: httpx.AsyncClient,
    key: str,
    area: str,
    window_from: date,
    window_to: date,
    report: SourceReport,
    max_span_days: int = 90,
) -> list[dict]:
    """한 지역의 행사를 activities 행(dict) 목록으로 돌려준다."""
    code = AREAS[area]["code"]
    # 이미 시작해서 진행 중인 행사도 받으려고, 시작일 조건을 '긴 행사 기준'만큼 앞당긴다.
    since = window_from - timedelta(days=max_span_days or 60)
    rows: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        params = {
            "serviceKey": normalize_key(key),
            "MobileOS": "ETC",
            "MobileApp": "gachigalae",
            "_type": "json",
            "arrange": "A",
            "numOfRows": PAGE_SIZE,
            "pageNo": page,
            "eventStartDate": since.strftime("%Y%m%d"),
            "lDongRegnCd": code,
        }
        text = await _get(client, params)
        items, total = parse_page(text)
        report.fetched += len(items)
        for item in items:
            row = to_row(item, area, window_from, window_to, max_span_days, report)
            if row and row["external_id"] not in rows:
                rows[row["external_id"]] = row
        if len(items) < PAGE_SIZE or page * PAGE_SIZE >= total:
            break
    report.kept += len(rows)
    return list(rows.values())


async def _get(client: httpx.AsyncClient, params: dict) -> str:
    problem = ""
    for attempt in range(2):
        if attempt:
            await asyncio.sleep(0.7)
        try:
            res = await client.get(BASE_URL, params=params)
        except httpx.HTTPError as exc:
            problem = f"TourAPI에 연결하지 못했어요 ({type(exc).__name__})"
            continue
        if res.status_code >= 500:
            problem = f"TourAPI 서버 오류 (HTTP {res.status_code})"
            continue
        body = res.text
        # 인증 오류는 XML 본문으로 오기도 해서, XML·JSON이면 parse_page가 사유를 읽는다
        if res.status_code >= 400 and not body.lstrip().startswith(("<", "{")):
            hint = "인증키(Decoding 키)와 활용신청 승인 여부를 확인하세요." if res.status_code in (401, 403) else ""
            raise CollectError(f"TourAPI 요청 실패 (HTTP {res.status_code}) {body.strip()[:80]} {hint}".strip())
        return body
    raise CollectError(problem)
