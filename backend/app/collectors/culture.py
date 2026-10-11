"""한국문화정보원 '한눈에보는문화정보조회서비스' 전시 수집.

분야별 조회(realm2)에서 전시(realmCode=D000)만 받는다. 목록에 장소·구·좌표·기간·썸네일이 있어서
상세 조회(detail2) 없이 저장한다. 관람료는 목록에 없어서 비워 둔다.

알아둘 점 (2026-10 실측)
- 응답은 XML. 지역은 시도 이름("서울", "대전")을 sido에 그대로 넣는다.
- from~to는 그 기간과 겹치는 전시를 돌려준다.
- sigungu가 구 이름("종로구")이고, gpsX가 경도, gpsY가 위도다.
- 파라미터 이름 대소문자가 섞여 있다 (PageNo, numOfrows). 다르게 쓰면 기본값으로 돌아간다.
- 인증키는 공공데이터포털 키. TourAPI와 같은 계정이면 같은 키를 쓰되 이 API 활용신청을 따로 해야 한다.
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import date

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
from app.collectors.tourapi import normalize_key

SOURCE = "한국문화정보원"
BASE_URL = "https://apis.data.go.kr/B553457/cultureinfo/realm2"
ATTRIBUTION = "출처: 한국문화정보원 한눈에보는문화정보"
REALM_EXHIBITION = "D000"
PAGE_SIZE = 100
MAX_PAGES = 10  # 지역당 최대 1,000건까지 넘겨 본다

_ERROR_HINTS = {
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "인증키가 등록되지 않았어요. 활용신청 승인 직후라면 1~2시간 뒤에 다시 해 보고, 공공데이터포털의 'Decoding' 키를 넣었는지 확인하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "오늘 호출 한도를 넘었어요. 내일 다시 하세요.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 인증키로 '한국문화정보원_한눈에보는문화정보조회서비스' 활용신청이 안 되어 있어요. 공공데이터포털에서 활용신청을 확인하세요.",
}


def _text(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    found = el.find(tag)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def parse_page(text: str) -> tuple[list[dict], int]:
    """응답 본문 → (item 목록, totalCount). 오류면 CollectError."""
    body_text = text.strip()
    if not body_text.startswith("<"):
        raise CollectError("문화정보원 응답을 읽지 못했어요 (XML이 아님).")
    try:
        root = ET.fromstring(body_text)
    except ET.ParseError as exc:
        raise CollectError("문화정보원 응답을 읽지 못했어요 (XML 형식 오류).") from exc

    # 인증 오류: <OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>…
    auth_msg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
    if root.tag == "OpenAPI_ServiceResponse" or auth_msg:
        msg = (auth_msg or "오류 응답").strip()
        raise CollectError(f"문화정보원 오류: {msg}. {_ERROR_HINTS.get(msg, '인증키와 활용신청 상태를 확인하세요.')}")

    code = (root.findtext(".//header/resultCode") or "").strip()
    if code not in ("", "00", "0000"):
        msg = (root.findtext(".//header/resultMsg") or "").strip()
        raise CollectError(f"문화정보원 오류 {code}: {msg}")

    total_raw = (root.findtext(".//totalCount") or "0").strip()
    total = int(total_raw) if total_raw.isdigit() else 0
    items = []
    for el in root.iter("item"):
        items.append({child.tag: (child.text or "").strip() for child in el})
    return items, total


def to_row(item: dict, area: str, window_from: date, window_to: date, max_span_days: int, report: SourceReport) -> dict | None:
    seq = (item.get("seq") or "").strip()
    title = (item.get("title") or "").strip()
    if not seq or not title:
        report.skip("ID·제목 없음")
        return None
    start = parse_ymd(item.get("startDate"))
    if not start:
        report.skip("날짜 없음")
        return None
    end = parse_ymd(item.get("endDate")) or start
    if not overlaps(start, end, window_from, window_to):
        report.skip("기간 밖")
        return None
    if max_span_days and (end - start).days + 1 > max_span_days:
        report.skip(f"{max_span_days}일 넘는 장기 전시")
        return None

    info = AREAS[area]
    sido = (item.get("area") or "").strip()
    if sido and not any(sido.startswith(name) for name in info["city_names"]):
        report.skip("다른 지역")
        return None
    sigungu = (item.get("sigungu") or "").strip()
    gu = sigungu if sigungu in info["gu"] else gu_from_address(f"{sido} {sigungu}".strip(), area)
    if not gu:
        report.skip("구를 알 수 없음")
        return None

    period = start.strftime("%Y.%m.%d") + ("" if end == start else " ~ " + end.strftime("%Y.%m.%d"))
    realm = (item.get("realmName") or "").strip() or "전시"
    return {
        "external_id": f"CULTURE:{seq}",
        "activity_type": "전시",
        "title": clip(title, "title"),
        "place": clip(item.get("place"), "place"),
        "region": gu,
        "starts_at": start_of(start),
        "ends_at": end_of(end),
        "cost": None,
        "description": join_parts(realm, f"기간 {period}", ATTRIBUTION),
        "source": SOURCE,
        "lat": to_float(item.get("gpsY")),
        "lng": to_float(item.get("gpsX")),
        "source_url": None,
        "image_url": clip(https(item.get("thumbnail")), "image_url"),
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
    """한 지역의 전시를 activities 행(dict) 목록으로 돌려준다."""
    rows: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        params = {
            "serviceKey": normalize_key(key),
            "PageNo": page,
            "numOfrows": PAGE_SIZE,
            "sido": area,
            "from": window_from.strftime("%Y%m%d"),
            "to": window_to.strftime("%Y%m%d"),
            "realmCode": REALM_EXHIBITION,
            "serviceTp": "A",
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
            problem = f"문화정보원에 연결하지 못했어요 ({type(exc).__name__})"
            continue
        if res.status_code >= 500:
            problem = f"문화정보원 서버 오류 (HTTP {res.status_code})"
            continue
        body = res.text
        if res.status_code >= 400 and not body.lstrip().startswith("<"):
            hint = "인증키(Decoding 키)와 활용신청 승인 여부를 확인하세요." if res.status_code in (401, 403) else ""
            # 본문에 키가 섞여 나올 수 있어 앞부분만, 그리고 키처럼 긴 문자열은 가린다
            snippet = re.sub(r"[A-Za-z0-9%+/=]{30,}", "***", body.strip()[:80])
            raise CollectError(f"문화정보원 요청 실패 (HTTP {res.status_code}) {snippet} {hint}".strip())
        return body
    raise CollectError(problem)
