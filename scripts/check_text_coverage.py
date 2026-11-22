"""
행사 설명 텍스트가 RAG·텍스트 분석에 쓸 만큼 채워져 있는지 샘플로 확인한다. (읽기만 하고 DB는 건드리지 않는다)

지금 activities.description은 "장르 · 공연시간 · 관람료 …" 같은 메타데이터 나열이라(중앙값 71자)
임베딩해도 장르·가격만 잡힌다. 각 API의 '상세' 응답에 긴 설명이 있는지 본다.

  KOPIS      공연상세 pblprfr/{id}       → sty (줄거리), styurls (소개 이미지)
  TourAPI    detailCommon2 (contentId)   → overview (개요)
  문화정보원 detail2 (seq)               → 가장 긴 텍스트 칸을 자동으로 찾는다

준비: 프로젝트 루트 .env 에 KOPIS_API_KEY, TOUR_API_KEY, CULTURE_API_KEY (수집 때와 같은 키)
실행:
  python scripts/check_text_coverage.py              # 출처별·지역별 20건씩
  python scripts/check_text_coverage.py --n 10       # 더 빨리
  python scripts/check_text_coverage.py --sources kopis

결과: 화면에 요약표, text_coverage.csv 에 건별 결과 (커밋하지 않는다, .gitignore에 있음)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

AREA_CODE = {"서울": "11", "대전": "30"}  # KOPIS signgucode = TourAPI lDongRegnCd
KOPIS = "https://kopis.or.kr/openApi/restful"
TOUR = "https://apis.data.go.kr/B551011/KorService2"
CULTURE = "https://apis.data.go.kr/B553457/cultureinfo"
SLEEP = 0.4  # KOPIS는 빠르게 보내면 막힌다 (CLAUDE.md 메모)
OUT = ROOT / "text_coverage.csv"


def key(name: str) -> str:
    k = os.getenv(name, "").strip()
    if not k:
        sys.exit(f".env에 {name}이 없어요.")
    return unquote(k) if "%" in k else k


def plain(text: str | None) -> str:
    """HTML 태그·엔티티·공백을 정리해 사람이 읽는 글자만 남긴다."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = t.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t).strip()


def leaves(el: ET.Element) -> dict[str, str]:
    """XML 한 항목의 바로 아래 태그 → 글자. 안에 HTML 태그가 섞여 있어도 글자만 모은다."""
    return {child.tag: "".join(child.itertext()).strip() for child in el}


def longest(fields: dict[str, str], skip: tuple[str, ...] = ()) -> tuple[str, int]:
    best = ("", 0)
    for k, v in fields.items():
        if k in skip or v.startswith("http"):
            continue
        n = len(plain(v))
        if n > best[1]:
            best = (k, n)
    return best


def get(client: httpx.Client, url: str, params: dict) -> str:
    for attempt in range(3):
        try:
            res = client.get(url, params=params, timeout=30)
            if res.status_code == 200:
                return res.text
            print(f"  ! HTTP {res.status_code}: {res.text[:200]}")
        except httpx.HTTPError as exc:
            print(f"  ! {type(exc).__name__}: {exc}")
        time.sleep(2 * (attempt + 1))
    return ""


def check_kopis(client: httpx.Client, area: str, n: int) -> list[dict]:
    k = key("KOPIS_API_KEY")
    today = date.today()
    text = get(client, f"{KOPIS}/pblprfr", {
        "service": k, "stdate": today.strftime("%Y%m%d"), "eddate": (today + timedelta(days=30)).strftime("%Y%m%d"),
        "cpage": 1, "rows": n, "signgucode": AREA_CODE[area],
    })
    if not text:
        return []
    ids = [(d.findtext("mt20id"), d.findtext("prfnm")) for d in ET.fromstring(text).iter("db")][:n]
    rows = []
    for pid, title in ids:
        time.sleep(SLEEP)
        body = get(client, f"{KOPIS}/pblprfr/{pid}", {"service": k})
        if not body:
            continue
        db = next(ET.fromstring(body).iter("db"), None)
        if db is None:
            continue
        f = leaves(db)
        sty = plain(f.get("sty"))
        images = len(list(db.iter("styurl")))
        rows.append({"source": "KOPIS", "area": area, "id": pid, "title": title, "field": "sty",
                     "length": len(sty), "intro_images": images, "preview": sty[:80]})
    return rows


def check_tour(client: httpx.Client, area: str, n: int) -> list[dict]:
    k = key("TOUR_API_KEY")
    base = {"serviceKey": k, "MobileOS": "ETC", "MobileApp": "gachigalae", "_type": "json"}
    text = get(client, f"{TOUR}/searchFestival2", {
        **base, "arrange": "A", "numOfRows": n, "pageNo": 1,
        "eventStartDate": (date.today() - timedelta(days=60)).strftime("%Y%m%d"), "lDongRegnCd": AREA_CODE[area],
    })
    try:
        items = json.loads(text)["response"]["body"]["items"]
        items = items.get("item", []) if isinstance(items, dict) else []
    except (ValueError, KeyError, TypeError):
        print(f"  ! TourAPI 목록 응답을 읽지 못했어요: {text[:200]}")
        return []
    if isinstance(items, dict):
        items = [items]
    rows = []
    for it in items[:n]:
        time.sleep(SLEEP)
        body = get(client, f"{TOUR}/detailCommon2", {**base, "contentId": it.get("contentid")})
        try:
            d = json.loads(body)["response"]["body"]["items"]["item"]
            d = d[0] if isinstance(d, list) else d
        except (ValueError, KeyError, TypeError, IndexError):
            print(f"  ! 상세 응답을 읽지 못했어요 ({it.get('contentid')}): {body[:200]}")
            continue
        ov = plain(d.get("overview"))
        rows.append({"source": "TourAPI", "area": area, "id": it.get("contentid"), "title": it.get("title"),
                     "field": "overview", "length": len(ov), "intro_images": "", "preview": ov[:80]})
    return rows


def check_culture(client: httpx.Client, area: str, n: int) -> list[dict]:
    k = key("CULTURE_API_KEY")
    today = date.today()
    text = get(client, f"{CULTURE}/realm2", {
        "serviceKey": k, "PageNo": 1, "numOfrows": n, "sido": area, "realmCode": "D000", "serviceTp": "A",
        "from": today.strftime("%Y%m%d"), "to": (today + timedelta(days=30)).strftime("%Y%m%d"),
    })
    if not text:
        return []
    try:
        items = [leaves(i) for i in ET.fromstring(text).iter("item")][:n]
    except ET.ParseError:
        print(f"  ! 문화정보원 목록 응답을 읽지 못했어요: {text[:200]}")
        return []
    rows = []
    for it in items:
        time.sleep(SLEEP)
        body = get(client, f"{CULTURE}/detail2", {"serviceKey": k, "seq": it.get("seq")})
        try:
            item = next(ET.fromstring(body).iter("item"), None) if body else None
        except ET.ParseError:
            item = None
        if item is None:
            print(f"  ! 상세 응답을 읽지 못했어요 ({it.get('seq')}): {body[:200]}")
            continue
        f = leaves(item)
        name, n_chars = longest(f, skip=("title", "place", "placeAddr", "area", "sigungu", "sido"))
        rows.append({"source": "문화정보원", "area": area, "id": it.get("seq"), "title": it.get("title"),
                     "field": name, "length": n_chars, "intro_images": "", "preview": plain(f.get(name))[:80]})
    return rows


CHECKS = {"kopis": check_kopis, "tour": check_tour, "culture": check_culture}


def summarize(rows: list[dict]) -> None:
    print("\n출처        지역  샘플  50자↑  200자↑  중앙값  가장 많이 쓰인 칸")
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["source"], r["area"]), []).append(r)
    for (src, area), rs in groups.items():
        lens = [r["length"] for r in rs]
        fields = [r["field"] for r in rs if r["length"]]
        common = max(set(fields), key=fields.count) if fields else "-"
        print(f"{src:<10} {area:<4} {len(rs):>4}  {sum(l >= 50 for l in lens):>5}  {sum(l >= 200 for l in lens):>6}"
              f"  {int(statistics.median(lens)) if lens else 0:>6}  {common}")
    kopis = [r for r in rows if r["source"] == "KOPIS"]
    if kopis:
        img_only = sum(1 for r in kopis if r["length"] < 50 and (r["intro_images"] or 0) > 0)
        print(f"\nKOPIS 줄거리가 비었거나 짧은데 소개 이미지만 있는 공연: {img_only} / {len(kopis)}건")
    print("\n판단 기준(제안): 200자 넘는 건이 절반 이상이면 RAG 소재로 충분, 아니면 축소안 검토")


def main() -> int:
    p = argparse.ArgumentParser(description="행사 상세 설명 텍스트 충족률 샘플 확인")
    p.add_argument("--n", type=int, default=20, help="출처·지역마다 샘플 수 (기본 20)")
    p.add_argument("--sources", default="kopis,tour,culture")
    p.add_argument("--areas", default="서울,대전")
    a = p.parse_args()
    rows: list[dict] = []
    with httpx.Client(headers={"User-Agent": "gachigalae-text-check"}) as client:
        for src in [s.strip() for s in a.sources.split(",") if s.strip()]:
            for area in [x.strip() for x in a.areas.split(",") if x.strip()]:
                print(f"- {src} / {area} 확인 중...")
                rows += CHECKS[src](client, area, a.n)
    if not rows:
        print("받은 결과가 없어요. 키와 네트워크를 확인해 주세요.")
        return 1
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summarize(rows)
    print(f"\n건별 결과: {OUT.name} (엑셀로 열림, 커밋하지 마세요)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
