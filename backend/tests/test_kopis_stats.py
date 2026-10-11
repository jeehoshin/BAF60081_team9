"""KOPIS 공연 통계 수집·집계 테스트 (인증키·인터넷 없이 돌아간다).

실행: cd backend && python -m unittest discover tests -v

응답 형식은 2026-10-11 실제 응답(2026년 9월분)과 같게 만들었고, 숫자는 계산을 확인하기 쉽게 줄인 값이다.
"""

import os

os.environ["USE_MEMORY"] = "1"
os.environ.setdefault("COLLECT_TOKEN", "test-token")

import unittest  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.collectors import kopis, kopis_stats  # noqa: E402
from app.collectors.common import CollectError  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import KopisStat  # noqa: E402
from app.routers.stats import kopis_stats as kopis_stats_api  # noqa: E402

kopis.MIN_INTERVAL = kopis.RETRY_WAIT = 0
TODAY = date(2026, 10, 11)


def xml_rows(rows):
    body = "".join("<prfst>" + "".join(f"<{k}>{v}</{k}>" for k, v in r.items()) + "</prfst>" for r in rows)
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><prfsts>{body}</prfsts>'


def area(name, amount, perf, booked, cancel):
    return {
        "area": name, "prfprocnt": 10, "prfdtcnt": perf, "amount": amount, "nmrs": booked,
        "totnmrs": booked - cancel, "seatcnt": booked * 2, "prfcnt": 12, "nmrcancl": cancel,
        "fcltycnt": 3, "prfplccnt": 4,
    }


# 합계 = 서울 + 경기 + 인천 + 대전 + 충남. 권역 소계(경기/인천, 충청도)는 겹쳐 세면 안 된다.
AREA_ROWS = [
    area("서울", 600, 60, 1000, 200),
    area("경기/인천", 300, 30, 500, 100),
    area("경기", 200, 20, 300, 60),
    area("인천", 100, 10, 200, 40),
    area("충청도", 50, 10, 100, 20),
    area("대전", 30, 6, 60, 12),
    area("충남", 20, 4, 40, 8),
    area("합계", 950, 100, 1600, 320),
]
GENRE_ROWS = [
    {"cate": "연극", "prfprocnt": 50, "prfdtcnt": 500, "amount": 100, "amountshr": 25.0, "nmrs": 900, "nmrsshr": 45.0},
    {"cate": "뮤지컬", "prfprocnt": 20, "prfdtcnt": 300, "amount": 300, "amountshr": 75.0, "nmrs": 1100, "nmrsshr": 55.0},
]


def day_rows(start, end):
    rows, d = [], start
    while d <= end:
        weekend = d.weekday() >= 5
        rows.append({
            "prfdt": d.strftime("%Y%m%d"), "prfprocnt": 1, "prfdtcnt": 20 if weekend else 10,
            "amount": 2000 if weekend else 1000, "nmrs": 200 if weekend else 100, "prfcnt": 5,
            "ntssnmrs": 250 if weekend else 130, "cancelnmrs": 50 if weekend else 30,
        })
        d += timedelta(days=1)
    return rows


def make_transport(calls, fail_path=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path.removeprefix("/openApi/restful/")
        p = request.url.params
        if path == fail_path:
            return httpx.Response(200, text="<dbs><db><returncode>02</returncode><errmsg>SERVICE KEY IS NOT REGISTERED</errmsg></db></dbs>")
        if path == "prfstsArea":
            return httpx.Response(200, text=xml_rows(AREA_ROWS))
        if path == "prfstsCate":
            return httpx.Response(200, text=xml_rows(GENRE_ROWS))
        if path == "prfstsTotal":
            start = date(int(p["stdate"][:4]), int(p["stdate"][4:6]), int(p["stdate"][6:]))
            end = date(int(p["eddate"][:4]), int(p["eddate"][4:6]), int(p["eddate"][6:]))
            return httpx.Response(200, text=xml_rows(day_rows(start, end)))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def memory_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class KopisStatsTests(unittest.TestCase):
    def collect(self, db, calls=None, fail_path=None, dry_run=False, months=3):
        return kopis_stats.collect(
            db, "kopis-test-key", months=months, dry_run=dry_run,
            transport=make_transport(calls if calls is not None else [], fail_path), today=TODAY,
        )

    def test_recent_months_skip_this_month(self):
        self.assertEqual(
            kopis_stats.recent_months(TODAY, 3),
            [(date(2026, 7, 1), date(2026, 7, 31)), (date(2026, 8, 1), date(2026, 8, 31)), (date(2026, 9, 1), date(2026, 9, 30))],
        )
        self.assertEqual(kopis_stats.recent_months(date(2026, 1, 5), 1), [(date(2025, 12, 1), date(2025, 12, 31))])

    def test_field_meanings_differ_by_api(self):
        a = kopis_stats.to_row("area", {k: str(v) for k, v in AREA_ROWS[0].items()}, TODAY, TODAY)
        self.assertEqual((a["tickets"], a["cancels"], a["audience"]), (1000, 200, 800))  # 지역별 nmrs = 예매
        d = kopis_stats.to_row("day", {k: str(v) for k, v in day_rows(date(2026, 9, 1), date(2026, 9, 1))[0].items()}, TODAY, TODAY)
        self.assertEqual((d["label"], d["tickets"], d["cancels"], d["audience"]), ("2026-09-01", 130, 30, 100))  # 일별 nmrs = 순 관객
        self.assertEqual([kopis_stats.area_level(n) for n in ("서울", "경기/인천", "충청도", "합계", "강원도")],
                         ["시도", "권역", "권역", "합계", "시도"])

    def test_calls_and_rows(self):
        calls = []
        res = self.collect(None, calls, dry_run=True)
        self.assertEqual(len(calls), 9)  # 3종류 × 3개월
        self.assertEqual({c.url.params["stdate"] for c in calls}, {"20260701", "20260801", "20260901"})
        self.assertTrue(all(c.url.params["service"] == "kopis-test-key" for c in calls))
        total_calls = [c for c in calls if c.url.path.endswith("prfstsTotal")]
        self.assertTrue(all(c.url.params["ststype"] == "day" for c in total_calls))
        self.assertNotIn("ststype", calls[0].url.params if calls[0].url.path.endswith("prfstsArea") else {})
        self.assertEqual(res["collected"], 3 * len(AREA_ROWS) + 3 * len(GENRE_ROWS) + 31 + 31 + 30)
        self.assertEqual(res["saved"], 0)
        self.assertEqual(res["period"], {"from": "2026-07-01", "to": "2026-09-30"})
        self.assertEqual(res["check"]["seoul_amount_share_percent"], 63.2)  # 600 / 950

    def test_save_twice_keeps_one_copy(self):
        db = memory_session()
        first = self.collect(db)
        self.assertEqual(db.query(KopisStat).count(), first["collected"])
        self.collect(db)
        self.assertEqual(db.query(KopisStat).count(), first["collected"])

    def test_one_api_failing_does_not_stop_others(self):
        res = self.collect(None, fail_path="prfstsCate", dry_run=True)
        errors = {r["label"]: r["error"] for r in res["results"]}
        self.assertIn("KOPIS 오류", errors["장르별"])
        self.assertIsNone(errors["지역별"])
        self.assertEqual(res["collected"], 3 * len(AREA_ROWS) + 92)

    def test_missing_key(self):
        with self.assertRaises(CollectError):
            kopis_stats.collect(None, "", dry_run=True)

    def test_stats_api_aggregates(self):
        db = memory_session()
        self.assertFalse(kopis_stats_api(db)["available"])
        self.collect(db)
        out = kopis_stats_api(db)
        self.assertTrue(out["available"])
        areas = {a["key"]: a for a in out["by_area"]}
        self.assertEqual(set(areas), {"서울", "경기", "인천", "대전", "충남"})  # 권역·합계 줄은 빠진다
        self.assertEqual(out["by_area"][0]["key"], "서울")
        self.assertEqual(areas["서울"]["amount"], 1800)  # 3개월 합
        self.assertEqual(areas["서울"]["amount_share"], 63.2)
        self.assertEqual(areas["대전"]["amount_share"], 3.2)
        self.assertEqual(areas["서울"]["performance_share"], 60.0)
        self.assertEqual(round(sum(a["amount_share"] for a in out["by_area"])), 100)

        genres = {g["key"]: g for g in out["by_genre"]}
        self.assertEqual((genres["뮤지컬"]["amount_share"], genres["뮤지컬"]["performance_share"]), (75.0, 37.5))
        self.assertEqual(out["by_genre"][0]["key"], "뮤지컬")

        week = out["by_weekday"]
        self.assertEqual([d["key"] for d in week], ["월", "화", "수", "목", "금", "토", "일"])
        self.assertEqual((week[0]["avg_audience"], week[5]["avg_audience"]), (100, 200))
        self.assertEqual(sum(d["days"] for d in week), 92)
        h = out["highlights"]
        self.assertEqual((h["seoul_amount_share"], h["daejeon_amount_share"]), (63.2, 3.2))
        self.assertTrue(30 < h["weekend_audience_share"] < 50)
        self.assertIn("집계기간: 2026.07.01 ~ 2026.09.30", out["notice"])
        self.assertIn("발권된 분량 기준", out["notice"])


class KopisStatsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.main import app

        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_collect_requires_token(self):
        self.assertEqual(self.client.post("/collect/kopis-stats").status_code, 401)
        self.assertEqual(self.client.post("/collect/kopis-stats", headers={"x-collect-token": "wrong"}).status_code, 401)

    def test_stats_endpoint_answers(self):
        res = self.client.get("/stats/kopis")
        self.assertEqual(res.status_code, 200)
        self.assertIn("available", res.json())


if __name__ == "__main__":
    unittest.main()
