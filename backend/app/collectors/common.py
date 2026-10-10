"""공공 API 수집에서 같이 쓰는 값과 도우미.

- 지역: 서울·대전. KOPIS 지역코드와 TourAPI 법정동 시도코드가 둘 다 11(서울)·30(대전)이다.
- 구: 주소("대전광역시 중구 선화서로 2")에서 뽑는다. 우리 activities.region은 'OO구' 형식이다.
- 날짜: 공공 API는 날짜만 준다. 시작은 그날 00:00, 끝은 그날 23:59:59로 저장한다.
"""

from __future__ import annotations

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
