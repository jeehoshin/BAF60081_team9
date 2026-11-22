"""공공 API 수집에서 같이 쓰는 값과 도우미.

- 지역: 서울·대전. KOPIS 지역코드와 TourAPI 법정동 시도코드가 둘 다 11(서울)·30(대전)이다.
- 구: 주소("대전광역시 중구 선화서로 2")에서 뽑는다. 우리 activities.region은 'OO구' 형식이다.
- 날짜: 공공 API는 날짜만 준다. 시작은 그날 00:00, 끝은 그날 23:59:59로 저장한다.
- 상세 설명: 줄거리·개요·전시 설명은 태그를 빼고 글자만 detail_text에 둔다 (RAG·텍스트 분석용).
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 수집 지역. 키는 화면·CLI에서 쓰는 이름이다.
AREAS: dict[str, dict] = {
    "서울": {
        "code": "11",  # KOPIS signgucode = TourAPI lDongRegnCd
        "city_names": ("서울특별시", "서울시", "서울"),
        "gu": (
            "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
            "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
            "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
        ),
        # TourAPI lDongSignguCd(법정동 시군구 코드 뒤 3자리) → 구. 주소가 비었을 때만 쓴다.
        "ldong_signgu": {
            "110": "종로구", "140": "중구", "170": "용산구", "200": "성동구", "215": "광진구",
            "230": "동대문구", "260": "중랑구", "290": "성북구", "305": "강북구", "320": "도봉구",
            "350": "노원구", "380": "은평구", "410": "서대문구", "440": "마포구", "470": "양천구",
            "500": "강서구", "530": "구로구", "545": "금천구", "560": "영등포구", "590": "동작구",
            "620": "관악구", "650": "서초구", "680": "강남구", "710": "송파구", "740": "강동구",
        },
    },
    "대전": {
        "code": "30",
        "city_names": ("대전광역시", "대전시", "대전"),
        "gu": ("대덕구", "동구", "서구", "유성구", "중구"),
        "ldong_signgu": {"110": "동구", "140": "중구", "170": "서구", "200": "유성구", "230": "대덕구"},
    },
}

DEFAULT_AREAS = ("서울", "대전")

# 두 도시에 다 있는 '중구'를 좌표로 가르는 기준. 서울은 북위 37.4~37.7, 대전은 36.2~36.5.
SEOUL_LAT_MIN = 37.3
DAEJEON_LAT_MAX = 37.0

# activities 컬럼 길이 (models.py와 맞춘다). Postgres는 길이를 넘으면 저장이 실패한다.
MAX_LEN = {
    "title": 255,
    "place": 255,
    "region": 64,
    "cost": 64,
    "external_id": 64,
    "source_url": 512,
    "image_url": 512,
}


DETAIL_MAX_CHARS = 4000  # 설명 글자 수 상한. 임베딩·프롬프트에 넣기 좋은 길이로 자른다
DETAIL_MAX_PER_AREA = 150  # 한 번 수집에서 출처·지역마다 상세를 부르는 최대 수 (TourAPI 개발계정 하루 1,000건 한도 보호)
DETAIL_CONCURRENCY = 4  # 상세를 동시에 몇 건까지 부를지


class CollectError(Exception):
    """API가 오류를 돌려줬을 때. 메시지는 화면(Swagger)에 그대로 보여준다."""


@dataclass
class SourceReport:
    """출처·지역 하나를 수집한 결과."""

    source: str
    area: str
    fetched: int = 0  # API에서 받은 건수
    kept: int = 0  # 저장 대상으로 남은 건수
    skipped: dict[str, int] = field(default_factory=dict)  # 버린 이유별 건수
    error: str | None = None
    # 상세 설명 조회: 부른 수 / 설명이 있던 수 / 실패 / 다음으로 미룬 수 / 최근에 확인해서 건너뛴 수
    details: dict[str, int] = field(
        default_factory=lambda: {"fetched": 0, "with_text": 0, "failed": 0, "deferred": 0, "skipped_recent": 0}
    )

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "area": self.area,
            "fetched": self.fetched,
            "kept": self.kept,
            "skipped": self.skipped,
            "error": self.error,
            "details": self.details,
        }


def today_kst() -> date:
    # Windows에서는 zoneinfo에 tzdata가 따로 필요해서 고정 오프셋을 쓴다 (한국은 서머타임 없음).
    return datetime.now(KST).date()


def start_of(d: date) -> datetime:
    return datetime.combine(d, time(0, 0))


def end_of(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59))


def parse_ymd(raw: str | None) -> date | None:
    """'20261014', '2026.10.14', '2026-10-14' → date. 형식이 틀리면 None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw.strip())
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError:
        return None


def overlaps(start: date, end: date, window_from: date, window_to: date) -> bool:
    return start <= window_to and end >= window_from


_SIDO_PREFIXES = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
    "충청", "충북", "충남", "전라", "전북", "전남", "경상", "경북", "경남", "제주",
)


def gu_from_address(address: str | None, area: str) -> str | None:
    """주소에서 그 지역의 구를 찾는다. 다른 시·도 주소이거나 구가 없으면 None.

    '대전광역시 중구 선화서로 2 (대흥동)' → '중구'
    '서울 마포구 월드컵북로 400' → '마포구'
    """
    if not address:
        return None
    info = AREAS[area]
    rest = " ".join(address.split())
    for name in sorted(info["city_names"], key=len, reverse=True):
        if rest.startswith(name):
            rest = rest[len(name):].lstrip()
            break
    else:
        if rest.startswith(_SIDO_PREFIXES):
            return None  # 다른 시·도 주소
    first = re.split(r"[\s,()]", rest, maxsplit=1)[0] if rest else ""
    return first if first in info["gu"] else None


def clip(value: str | None, column: str) -> str | None:
    """컬럼 길이에 맞게 자른다. 빈 문자열은 None."""
    if value is None:
        return None
    value = " ".join(str(value).split())
    if not value:
        return None
    limit = MAX_LEN.get(column)
    if limit and len(value) > limit:
        value = value[: limit - 1] + "…"
    return value


def https(url: str | None) -> str | None:
    """Vercel(https) 화면에서 http 이미지가 막히지 않게 바꾼다."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url if url.startswith("https://") else None


def to_float(raw: str | None) -> float | None:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value != 0 else None


def join_parts(*parts: str | None, sep: str = " · ") -> str | None:
    cleaned = [" ".join(p.split()) for p in parts if p and p.strip()]
    return sep.join(cleaned) if cleaned else None


# ---------- 상세 설명 · 관람 조건 ----------

def plain_text(raw: str | None, limit: int = DETAIL_MAX_CHARS) -> str | None:
    """HTML 태그·엔티티를 걷어 낸 글자. 비었으면 None.

    '<p>가족&nbsp;연극</p><br>' → '가족 연극'. 엔티티가 두 번 감싸여 오는 경우(&amp;lt;p&amp;gt;)도 푼다.
    """
    if not raw:
        return None
    text = raw
    for _ in range(2):
        text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.replace("\xa0", " ").split())
    if not text:
        return None
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def text_hash(text: str | None) -> str | None:
    """설명이 바뀌었는지 보는 지문 (sha256). 같은 글이면 같은 값이라 임베딩을 다시 만들지 않아도 된다."""
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 학년 표현은 만 나이로 본다 (초등 1학년 = 만 7세, 중학생 = 만 12세, 고등학생 = 만 15세, 청소년 관람불가 = 만 19세)
_AGE_WORDS = (("청소년 관람불가", 19 * 12), ("청소년관람불가", 19 * 12), ("성인", 19 * 12),
              ("고등학생", 15 * 12), ("중학생", 12 * 12), ("초등학생", 7 * 12), ("초등", 7 * 12))


def parse_age_months(raw: str | None) -> int | None:
    """관람연령 → 볼 수 있는 최소 나이(개월). 알 수 없으면 None.

    '전체 관람가' → 0, '24개월 이상' → 24, '만 7세 이상' → 84, '12세 이상' → 144, '초등학생 이상' → 84
    """
    if not raw:
        return None
    text = " ".join(raw.split())
    if "전체" in text:
        return 0
    found = re.search(r"(\d+)\s*개월", text)
    if found:
        return int(found.group(1))
    found = re.search(r"(\d+)\s*세", text)
    if found:
        return int(found.group(1)) * 12
    for word, months in _AGE_WORDS:
        if word in text:
            return months
    return None


def parse_runtime_min(raw: str | None) -> int | None:
    """러닝타임 → 분. '1시간 30분' → 90, '90분' → 90, '1시간 30분(인터미션 15분 포함)' → 90. 모르면 None."""
    if not raw:
        return None
    text = re.sub(r"[(\[][^)\]]*[)\]]", " ", raw)  # 괄호 속 '인터미션 15분 포함' 같은 덧붙임은 뺀다
    text = text.split("인터미션")[0]
    hours = re.search(r"(\d+)\s*시간", text)
    minutes = re.search(r"(\d+)\s*분", text)
    total = (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)
    return total or None


async def fill_details(rows, skip_ids, report: "SourceReport", fetch_one, source_field: str,
                       limit: int = DETAIL_MAX_PER_AREA, concurrency: int = DETAIL_CONCURRENCY) -> None:
    """새 행사나 설명을 아직 확인하지 않은 행사만 상세를 불러 행에 채운다.

    - skip_ids: 최근에 확인한 external_id. 이 행사는 부르지 않고, 행에 상세 칸도 넣지 않는다 (저장된 값을 그대로 둔다).
    - fetch_one(row) → 설명 원문(없으면 None). 실패하면 CollectError. 실패한 행사도 칸을 넣지 않아 다음 수집에서 다시 시도한다.
    - limit을 넘는 행사는 다음 수집으로 미룬다.
    """
    skip_ids = skip_ids or set()
    targets = []
    for row in rows:
        if row["external_id"] in skip_ids:
            report.details["skipped_recent"] += 1
        elif len(targets) < limit:
            targets.append(row)
        else:
            report.details["deferred"] += 1
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            try:
                raw = await fetch_one(row)
            except CollectError:
                report.details["failed"] += 1
                return
        report.details["fetched"] += 1
        extra = detail_fields(raw, source_field)
        report.details["with_text"] += int(bool(extra["detail_text"]))
        row.update(extra)

    await asyncio.gather(*(one(r) for r in targets))


def detail_fields(text: str | None, source_field: str, images: list[str] | None = None) -> dict:
    """상세 조회 결과를 activities 칸으로. 설명이 없어도 '확인했다'는 시각은 남긴다 (다음 수집에서 다시 부르지 않게)."""
    text = plain_text(text)
    out = {
        "detail_text": text,
        "detail_source": source_field if text else None,
        "text_hash": text_hash(text),
        "detail_checked_at": datetime.now(KST).replace(tzinfo=None),
    }
    if images is not None:
        out["intro_images"] = json.dumps(images, ensure_ascii=False) if images else None
    return out
