"""기획 미반영 항목 보완 테스트 (2026-10-17).

- 수집 실행 기록 collect_runs (기획 3-6)
- 분석 "오늘 QR 참여자만 보기" (since 필터, 기획 4장)
- 지표 G: 구별 인구 10만 명당 활동 수, 서울 vs 대전
- 탐색 city 필터 ('중구'를 서울·대전으로 가르기)

실행: cd backend && python -m unittest discover tests -v
"""

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

os.environ["USE_MEMORY"] = "1"
os.environ.setdefault("COLLECT_TOKEN", "test-token")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import population as pop  # noqa: E402
from app.collectors import runner  # noqa: E402
from app.collectors.runs import record_run  # noqa: E402
from app.database import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, CollectRun, Meetup, Participant, User  # noqa: E402
from app.routers.stats import city_of  # noqa: E402


def memory_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def empty_transport():
    """모든 공공 API가 빈 목록을 주는 가짜 서버 (KOPIS XML / TourAPI·문화정보원 JSON)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "kopis.or.kr" in request.url.host:
            return httpx.Response(200, text='<?xml version="1.0" encoding="UTF-8"?><dbs></dbs>')
        return httpx.Response(200, json={"response": {"body": {"items": "", "totalCount": 0}}})

    return httpx.MockTransport(handler)


class PopulationDistrictTests(unittest.TestCase):
    def test_district_totals_match_city_population(self):
        self.assertEqual(len(pop.DISTRICTS["서울"]), 25)
        self.assertEqual(len(pop.DISTRICTS["대전"]), 5)
        self.assertEqual(sum(pop.DISTRICTS["서울"].values()), pop.population_of("서울"))
        self.assertEqual(sum(pop.DISTRICTS["대전"].values()), pop.population_of("대전"))

    def test_jung_gu_needs_city(self):
        self.assertEqual(pop.district_population("대전", "중구"), 223_474)
        self.assertEqual(pop.district_population("서울특별시", "중구"), 117_205)
        self.assertIsNone(pop.district_population(None, "중구"))
        self.assertIsNone(pop.district_population("서울", "유성구"))


class CityOfTests(unittest.TestCase):
    def test_unique_gu_names(self):
        self.assertEqual(city_of(Activity(region="유성구")), "대전")
        self.assertEqual(city_of(Activity(region="마포구")), "서울")
        self.assertIsNone(city_of(Activity(region=None)))
        self.assertIsNone(city_of(Activity(region="해운대구")))

    def test_jung_gu_split_by_coords_then_text(self):
        self.assertEqual(city_of(Activity(region="중구", lat=36.33, lng=127.42)), "대전")
        self.assertEqual(city_of(Activity(region="중구", lat=37.56, lng=126.99)), "서울")
        self.assertEqual(city_of(Activity(region="중구", place="대전 으능정이")), "대전")
        self.assertEqual(city_of(Activity(region="중구", description="서울 명동 공연")), "서울")
        self.assertIsNone(city_of(Activity(region="중구")))


class CollectRunRecordTests(unittest.TestCase):
    def test_record_and_skip_without_db(self):
        self.assertIsNone(record_run(None, "activities", datetime.now(), {}))
        db = memory_session()
        run_id = record_run(
            db, "activities", datetime.now() - timedelta(seconds=3), {"results": [{"source": "KOPIS"}]},
            window_from="2026-10-17", window_to=datetime(2026, 11, 16), collected=5, inserted=2, updated=1,
            unchanged=2, skipped=7, error_count=1, trigger="cli", dry_run=False,
        )
        run = db.get(CollectRun, run_id)
        self.assertEqual((run.collected, run.inserted, run.updated, run.unchanged, run.skipped), (5, 2, 1, 2, 7))
        self.assertFalse(run.ok)
        self.assertEqual(run.trigger, "cli")
        self.assertEqual(run.window_from.isoformat(), "2026-10-17")
        self.assertEqual(run.window_to.isoformat(), "2026-11-16")
        self.assertIn("KOPIS", run.details)

    def test_runner_collect_writes_a_run_even_for_dry_run(self):
        db = memory_session()
        opts = runner.CollectOptions(sources="kopis,tour", areas="대전", days=7)
        result = runner.collect(
            db, opts, kopis_key="k", tour_key="t", dry_run=True, transport=empty_transport(), trigger="cli",
        )
        self.assertIsNotNone(result["run_id"])
        run = db.get(CollectRun, result["run_id"])
        self.assertTrue(run.dry_run)
        self.assertEqual(run.kind, "activities")
        self.assertEqual(run.collected, 0)
        self.assertEqual(run.window_from, runner.today_kst())
        # 두 번째 실행(저장)도 새 줄
        runner.collect(db, opts, kopis_key="k", tour_key="t", transport=empty_transport())
        self.assertEqual(db.query(CollectRun).count(), 2)

    def test_missing_key_counts_as_error(self):
        db = memory_session()
        result = runner.collect(
            db, runner.CollectOptions(sources="kopis", areas="서울"), kopis_key="", dry_run=True,
            transport=empty_transport(),
        )
        run = db.get(CollectRun, result["run_id"])
        self.assertEqual(run.error_count, 1)
        self.assertFalse(run.ok)


class StatsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        # "오늘 참여자만"의 기준 시각. 시드·다른 테스트가 방금 만든 행(지금 시각)이 섞이지 않게 2초 뒤로 둔다
        cls.cut = datetime.now().replace(microsecond=0) + timedelta(seconds=2)
        old = cls.cut - timedelta(days=3)
        new = cls.cut + timedelta(seconds=1)
        db = SessionLocal()
        try:
            acts = [
                Activity(activity_type="러닝", title="기획테스트 유성 러닝", region="유성구", source="user",
                         starts_at=new + timedelta(days=1), lat=36.37, lng=127.36),
                Activity(activity_type="공연", title="기획테스트 대전 중구 공연", region="중구", source="KOPIS",
                         external_id="KOPIS:PG1", starts_at=new + timedelta(days=1), lat=36.33, lng=127.42),
                Activity(activity_type="공연", title="기획테스트 서울 중구 공연", region="중구", source="KOPIS",
                         external_id="KOPIS:PG2", starts_at=new + timedelta(days=1), lat=37.56, lng=126.99),
                Activity(activity_type="전시", title="기획테스트 끝난 마포 전시", region="마포구", source="한국문화정보원",
                         external_id="CULTURE:PG1", starts_at=old - timedelta(days=20), ends_at=old - timedelta(days=1)),
            ]
            users = [
                User(nickname="기획테스트-옛날", age_group="30대", gender="남", created_at=old),
                User(nickname="기획테스트-오늘1", age_group="20대", gender="여", created_at=new),
                User(nickname="기획테스트-오늘2", age_group="20대", gender="남", created_at=new),
            ]
            db.add_all(acts + users)
            db.commit()
            cls.act_ids = [a.activity_id for a in acts]
            old_user, u1, u2 = users
            old_meetup = Meetup(activity_id=acts[0].activity_id, host_id=old_user.user_id, name="옛 모임",
                                capacity=4, created_at=old)
            new_meetup = Meetup(activity_id=acts[0].activity_id, host_id=u1.user_id, name="오늘 모임",
                                capacity=5, created_at=new)
            db.add_all([old_meetup, new_meetup])
            db.commit()
            db.add_all([
                Participant(meetup_id=old_meetup.meetup_id, user_id=old_user.user_id, joined_at=old),
                Participant(meetup_id=new_meetup.meetup_id, user_id=u1.user_id, joined_at=new),
                Participant(meetup_id=new_meetup.meetup_id, user_id=u2.user_id, joined_at=new),
                # 오늘 들어온 사람이 옛 모임에도 참여 → participants에는 세지만 충원율은 오늘 모임 기준
                Participant(meetup_id=old_meetup.meetup_id, user_id=u2.user_id, joined_at=new),
            ])
            db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_users_since(self):
        all_users = self.client.get("/stats/users").json()
        today = self.client.get("/stats/users", params={"since": self.cut.isoformat()}).json()
        self.assertIsNone(all_users["since"])
        self.assertEqual(today["total"], 2)
        self.assertGreater(all_users["total"], today["total"])
        self.assertEqual({b["key"]: b["count"] for b in today["by_age_group"]}, {"20대": 2})
        self.assertEqual({b["key"]: b["count"] for b in today["by_gender"]}, {"여": 1, "남": 1})

    def test_meetups_since(self):
        today = self.client.get("/stats/meetups", params={"since": self.cut.isoformat()}).json()
        self.assertEqual(today["open_meetups"], 1)
        self.assertEqual(today["participants"], 3)  # 오늘 참여 3건 (옛 모임에 들어간 1건 포함)
        self.assertEqual(today["avg_fill_rate_percent"], 40.0)  # 오늘 모임 정원 5명 중 2명
        everything = self.client.get("/stats/meetups").json()
        self.assertGreaterEqual(everything["open_meetups"], 2)

    def test_regions_per_capita(self):
        r = self.client.get("/stats/regions")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        cities = {c["city"]: c for c in body["cities"]}
        self.assertEqual(set(cities), {"서울", "대전"})
        dj = {d["key"]: d for d in cities["대전"]["districts"]}
        se = {d["key"]: d for d in cities["서울"]["districts"]}
        self.assertEqual(len(dj), 5)
        self.assertEqual(len(se), 25)
        # 대전 중구 공연은 대전으로, 서울 중구 공연은 서울로
        self.assertGreaterEqual(dj["중구"]["count"], 1)
        self.assertGreaterEqual(se["중구"]["count"], 1)
        self.assertEqual(dj["유성구"]["per_100k"], pop.per_100k(dj["유성구"]["count"], 374_328))
        self.assertEqual(cities["대전"]["activities"], sum(d["count"] for d in dj.values()))
        self.assertEqual(body["population_basis"]["month"], pop.BASIS_MONTH)
        h = body["highlights"]
        self.assertEqual(h["daejeon_per_100k"], cities["대전"]["per_100k"])

        # 끝난 행사 제외 옵션
        live = self.client.get("/stats/regions", params={"include_ended": "false"}).json()
        se_live = {d["key"]: d for d in next(c for c in live["cities"] if c["city"] == "서울")["districts"]}
        self.assertLess(se_live["마포구"]["count"], se["마포구"]["count"])

    def test_city_filter_splits_jung_gu(self):
        dj = self.client.get("/activities", params={"city": "대전", "region": "중구"}).json()
        se = self.client.get("/activities", params={"city": "서울", "region": "중구"}).json()
        dj_ids = {a["activity_id"] for a in dj}
        se_ids = {a["activity_id"] for a in se}
        _, dj_act, se_act, _ = self.act_ids
        self.assertIn(dj_act, dj_ids)
        self.assertNotIn(se_act, dj_ids)
        self.assertIn(se_act, se_ids)
        self.assertNotIn(dj_act, se_ids)
        # 도시만 고르면 그 도시 구 전부
        all_dj = self.client.get("/activities", params={"city": "대전"}).json()
        self.assertTrue(all(a["region"] in ("유성구", "서구", "중구", "동구", "대덕구") for a in all_dj))
        self.assertEqual(self.client.get("/activities", params={"city": "부산"}).status_code, 422)

    def test_collect_runs_endpoint_and_quality(self):
        db = SessionLocal()
        try:
            record_run(db, "activities", datetime.now(), {"results": []}, collected=3, inserted=3)
            record_run(db, "activities", datetime.now(), {"results": []}, dry_run=True, collected=9)
        finally:
            db.close()
        runs = self.client.get("/stats/collect-runs").json()
        self.assertGreaterEqual(runs["total"], 2)
        self.assertEqual(runs["last_activities"]["collected"], 3)  # dry_run은 '마지막 실제 수집'에서 뺀다
        self.assertTrue(runs["recent"][0]["dry_run"])
        q = self.client.get("/stats/quality").json()
        self.assertEqual(q["collect_runs"]["last_activities"]["inserted"], 3)


if __name__ == "__main__":
    unittest.main()
