"""분석 보강 테스트: 인구 10만 명당 지표, 데이터 품질, 출처 간 중복 후보.

실행: cd backend && python -m unittest discover tests -v
"""

import os
import unittest
from datetime import date, datetime, timedelta

os.environ["USE_MEMORY"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import population as pop  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, KopisStat  # noqa: E402
from app.routers.stats import normalize_title  # noqa: E402


class PopulationTests(unittest.TestCase):
    def test_population_table_matches_national_total(self):
        self.assertEqual(len(pop.POPULATION), 17)
        self.assertEqual(sum(pop.POPULATION.values()), pop.NATIONAL_TOTAL)

    def test_lookup_by_short_and_full_name(self):
        self.assertEqual(pop.population_of("대전"), 1_443_122)
        self.assertEqual(pop.population_of("대전광역시"), 1_443_122)
        self.assertEqual(pop.population_of("강원특별자치도"), pop.population_of("강원"))
        self.assertIsNone(pop.population_of("경기/인천"))  # 권역 소계는 인구 없음
        self.assertIsNone(pop.population_of(None))

    def test_per_100k(self):
        self.assertEqual(pop.per_100k(1_443_122, 1_443_122), 100000.0)
        self.assertIsNone(pop.per_100k(10, None))


class TitleTests(unittest.TestCase):
    def test_normalize_title(self):
        self.assertEqual(normalize_title("피터팬 [대전 대덕]"), "피터팬")
        self.assertEqual(normalize_title("2026 서울발레페스티벌"), "서울발레페스티벌")
        self.assertEqual(normalize_title("제15회 대전 윈드오케스트라 (정기연주회)"), "대전윈드오케스트라")
        # 《전시명》은 제목이므로 남긴다
        self.assertEqual(normalize_title("《도시의 밤》 김혜정 개인전"), "도시의밤김혜정개인전")


class QualityAndPerCapitaApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        db = SessionLocal()
        try:
            rows = [
                # 같은 공연이 두 출처에 → 중복 후보
                Activity(activity_type="공연", title="품질테스트 가을음악회 [대전]", region="유성구",
                         starts_at=today, ends_at=today + timedelta(days=2), source="KOPIS",
                         external_id="KOPIS:QT1", image_url="https://example.com/a.jpg", lat=36.3, lng=127.3),
                Activity(activity_type="공연", title="2026 품질테스트 가을음악회", region="유성구",
                         starts_at=today + timedelta(days=1), ends_at=today + timedelta(days=1), source="한국관광공사",
                         external_id="TOUR:QT1"),
                # 제목은 같지만 구가 달라 중복 아님
                Activity(activity_type="공연", title="품질테스트 가을음악회", region="마포구",
                         starts_at=today, ends_at=today, source="한국문화정보원", external_id="CULTURE:QT1"),
                # 이미 끝난 행사
                Activity(activity_type="전시", title="품질테스트 지난 전시", region="종로구",
                         starts_at=today - timedelta(days=30), ends_at=today - timedelta(days=10),
                         source="한국문화정보원", external_id="CULTURE:QT2"),
            ]
            db.add_all(rows)
            db.commit()
            cls.ids = [r.activity_id for r in rows]

            first = date.today().replace(day=1) - timedelta(days=1)
            start = first.replace(day=1)
            if not db.query(KopisStat).filter(KopisStat.kind == "area").first():
                db.add_all([
                    KopisStat(kind="area", period_from=start, period_to=first, label="서울", level="시도",
                              amount=9_279_861_000, performance_count=9_279, audience=92_798),
                    KopisStat(kind="area", period_from=start, period_to=first, label="대전", level="시도",
                              amount=1_443_122_000, performance_count=1_443, audience=14_431),
                    KopisStat(kind="area", period_from=start, period_to=first, label="합계", level="합계",
                              amount=10_722_983_000, performance_count=10_722, audience=107_229),
                ])
                db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_quality_endpoint(self):
        r = self.client.get("/stats/quality")
        self.assertEqual(r.status_code, 200, r.text)
        q = r.json()
        sources = {s["source"]: s for s in q["by_source"]}
        self.assertIn("KOPIS", sources)
        for s in q["by_source"]:
            self.assertEqual(sum(s["status"].values()), s["count"])
        self.assertEqual(sum(s["count"] for s in q["by_source"]), q["total"]["count"])

        pairs = q["cross_source_duplicates"]["pairs"]
        found = {frozenset((p["a"]["activity_id"], p["b"]["activity_id"])) for p in pairs}
        kopis_id, tour_id, culture_mapo_id, _ = self.ids
        self.assertIn(frozenset((kopis_id, tour_id)), found)
        self.assertNotIn(frozenset((kopis_id, culture_mapo_id)), found)  # 다른 구
        self.assertGreaterEqual(q["cross_source_duplicates"]["count"], 1)

    def test_kopis_per_capita(self):
        k = self.client.get("/stats/kopis").json()
        self.assertTrue(k["available"])
        self.assertEqual(k["population_basis"]["month"], pop.BASIS_MONTH)
        for a in k["by_area"]:
            people = pop.population_of(a["key"])
            if people:
                self.assertEqual(a["population"], people)
                self.assertEqual(a["amount_per_100k"], round(a["amount"] / people * 100_000, 1))
        seoul = next(a for a in k["by_area"] if a["key"] == "서울")
        self.assertEqual(k["highlights"]["seoul_amount_per_100k"], seoul["amount_per_100k"])


if __name__ == "__main__":
    unittest.main()
