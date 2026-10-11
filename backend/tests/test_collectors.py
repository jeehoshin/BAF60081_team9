"""공공 API 수집기 테스트 (인증키·인터넷 없이 돌아간다).

실행: cd backend && python -m unittest discover tests -v

KOPIS 응답은 2026-10 실제 응답을 줄여 쓴 것이고, TourAPI 응답은 KorService2 형식(lDongRegnCd,
lclsSystm2, 0건이면 items="" 등)을 따랐다.
"""

import os

os.environ["USE_MEMORY"] = "1"
os.environ["COLLECT_TOKEN"] = "test-token"
os.environ["KOPIS_API_KEY"] = "kopis-test-key"
os.environ["TOUR_API_KEY"] = "tour%2Btest%3D%3D"  # Encoding 키를 넣어도 풀어서 쓰는지 본다

import asyncio  # noqa: E402
import json  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime  # noqa: E402
from unittest import mock  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.collectors import kopis, runner, tourapi  # noqa: E402
from app.collectors.common import CollectError, gu_from_address  # noqa: E402
from app.database import Base, ensure_schema  # noqa: E402
from app.models import Activity  # noqa: E402

TODAY = date(2026, 10, 11)
kopis.MIN_INTERVAL = kopis.RETRY_WAIT = 0  # 테스트에서는 요청 사이에 쉬지 않는다

KOPIS_BLOCKED = "<HTML><HEAD><TITLE>400 Bad Request</TITLE></HEAD><BODY><H1>Request Blocked</H1></BODY></HTML>"

KOPIS_LIST_DAEJEON = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><dbs>
<db><mt20id>PF302715</mt20id><prfnm>꽃잠 [대전]</prfnm><prfpdfrom>2026.10.14</prfpdfrom><prfpdto>2026.10.17</prfpdto><fcltynm>드림아트홀 [대전]</fcltynm><poster>http://www.kopis.or.kr/upload/pfmPoster/PF_PF302715_261007_134956.gif</poster><area>대전광역시</area><genrenm>연극</genrenm><openrun>N</openrun><prfstate>공연예정</prfstate></db>
<db><mt20id>PF300001</mt20id><prfnm>상설 오픈런</prfnm><prfpdfrom>2025.01.01</prfpdfrom><prfpdto>2027.12.31</prfpdto><fcltynm>어딘가</fcltynm><poster></poster><area>대전광역시</area><genrenm>연극</genrenm><openrun>Y</openrun><prfstate>공연중</prfstate></db>
<db><mt20id>PF300002</mt20id><prfnm>반년짜리 공연</prfnm><prfpdfrom>2026.09.01</prfpdfrom><prfpdto>2027.02.28</prfpdto><fcltynm>어딘가</fcltynm><poster></poster><area>대전광역시</area><genrenm>연극</genrenm><openrun>N</openrun><prfstate>공연중</prfstate></db>
</dbs>"""

KOPIS_DETAIL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><dbs><db><mt20id>PF302715</mt20id><mt13id>FC000752-01</mt13id><prfnm>꽃잠 [대전]</prfnm><prfpdfrom>2026.10.14</prfpdfrom><prfpdto>2026.10.17</prfpdto><fcltynm>드림아트홀 [대전] (드림아트홀 [대전] )</fcltynm><prfcast>이승희, 정현주, 이진아</prfcast><prfruntime>1시간 20분</prfruntime><prfage>만 11세 이상</prfage><pcseguidance>전석 30,000원</pcseguidance><poster>http://www.kopis.or.kr/upload/pfmPoster/PF_PF302715_261007_134956.gif</poster><sty> </sty><area>대전광역시</area><genrenm>연극</genrenm><openrun>N</openrun><prfstate>공연예정</prfstate><mt10id>FC000752</mt10id><dtguidance>수요일 ~ 금요일(19:30), 토요일(15:00)</dtguidance><styurls><styurl>http://www.kopis.or.kr/upload/pfmIntroImage/a.jpg</styurl></styurls><relates><relate><relatenm>놀유니버스</relatenm><relateurl>http://ticket.interpark.com/Ticket/Goods/GoodsInfo.asp?GoodsCode=26013272</relateurl></relate></relates></db></dbs>"""

KOPIS_FACILITY = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><dbs><db><fcltynm>드림아트홀 [대전]</fcltynm><mt10id>FC000752</mt10id><mt13cnt>1</mt13cnt><telno>042-252-0887</telno><adres>대전광역시 중구 선화서로 2 (대흥동)</adres><la>36.324377100000000</la><lo>127.42044770000007</lo><mt13s><mt13><prfplcnm>드림아트홀 [대전] </prfplcnm><mt13id>FC000752-01</mt13id></mt13></mt13s></db></dbs>"""


def tour_page(items, total=None):
    return json.dumps(
        {
            "response": {
                "header": {"resultCode": "0000", "resultMsg": "OK"},
                "body": {
                    "items": {"item": items} if items else "",
                    "numOfRows": 100,
                    "pageNo": 1,
                    "totalCount": len(items) if total is None else total,
                },
            }
        },
        ensure_ascii=False,
    )


TOUR_SEOUL_ITEMS = [
    {
        "contentid": "2786391", "title": "서울세계불꽃축제 2026", "eventstartdate": "20261017",
        "eventenddate": "20261017", "addr1": "서울특별시 영등포구 여의동로 330", "addr2": "(여의도동)",
        "areacode": "", "sigungucode": "", "lDongRegnCd": "11", "lDongSignguCd": "560",
        "lclsSystm2": "EV01", "cat2": "", "mapx": "126.9341", "mapy": "37.5284",
        "firstimage": "http://tong.visitkorea.or.kr/cms/a.jpg", "tel": "02-123-4567<br>(평일)",
    },
    {
        "contentid": "2786392", "title": "한국 근대 미술 특별전", "eventstartdate": "20261001",
        "eventenddate": "20261130", "addr1": "", "lDongRegnCd": "11", "lDongSignguCd": "110",
        "lclsSystm2": "EV03", "mapx": "126.97", "mapy": "37.57", "firstimage": "",
    },
    {
        "contentid": "2786393", "title": "1년 내내 하는 관람", "eventstartdate": "20260101",
        "eventenddate": "20261231", "addr1": "서울특별시 중구 세종대로 99", "lDongRegnCd": "11",
        "lclsSystm2": "EV03",
    },
    {
        "contentid": "2786394", "title": "지난달 끝난 축제", "eventstartdate": "20260901",
        "eventenddate": "20260905", "addr1": "서울특별시 마포구 월드컵로 1", "lDongRegnCd": "11",
        "lclsSystm2": "EV01",
    },
    {
        "contentid": "2786395", "title": "하루 공연", "eventstartdate": "20261020",
        "eventenddate": "20261020", "addr1": "서울 종로구 대학로 1", "lDongRegnCd": "11", "lclsSystm2": "EV02",
    },
    {"contentid": "", "title": "아이디 없음", "eventstartdate": "20261020"},
]

TOUR_DAEJEON_ONE = {
    "contentid": "3000001", "title": "유성온천문화축제", "eventstartdate": "20261023", "eventenddate": "20261025",
    "addr1": "대전광역시 유성구 온천로 일원", "lDongRegnCd": "30", "lDongSignguCd": "200", "lclsSystm2": "EV01",
    "mapx": "127.34", "mapy": "36.35",
}


def make_transport(calls, tour_daejeon_single=True, tour_error=None, kopis_error=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url = request.url
        if url.host == "kopis.or.kr":
            if kopis_error:
                return httpx.Response(200, text=kopis_error)
            path = url.path.removeprefix("/openApi/restful/")
            if path == "pblprfr":
                p = url.params
                if p["signgucode"] == "30" and p["shcate"] == "AAAA":
                    return httpx.Response(200, text=KOPIS_LIST_DAEJEON)
                return httpx.Response(200, text="<dbs></dbs>")
            if path == "pblprfr/PF302715":
                return httpx.Response(200, text=KOPIS_DETAIL)
            if path == "prfplc/FC000752":
                return httpx.Response(200, text=KOPIS_FACILITY)
            return httpx.Response(404, text="not found")
        if url.host == "apis.data.go.kr":
            if tour_error:
                return httpx.Response(200, text=tour_error)
            if url.params.get("lDongRegnCd") == "11":
                return httpx.Response(200, text=tour_page(TOUR_SEOUL_ITEMS))
            if url.params.get("lDongRegnCd") == "30":
                if tour_daejeon_single:  # 한 건이면 item이 배열이 아니라 객체로 온다
                    body = json.loads(tour_page([TOUR_DAEJEON_ONE]))
                    body["response"]["body"]["items"]["item"] = TOUR_DAEJEON_ONE
                    return httpx.Response(200, text=json.dumps(body, ensure_ascii=False))
                return httpx.Response(200, text=tour_page([]))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def memory_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


class ParsingTests(unittest.TestCase):
    def test_gu_from_address(self):
        self.assertEqual(gu_from_address("대전광역시 중구 선화서로 2 (대흥동)", "대전"), "중구")
        self.assertEqual(gu_from_address("서울 마포구 월드컵북로 400", "서울"), "마포구")
        self.assertEqual(gu_from_address("서울특별시 중랑구 망우로 1", "서울"), "중랑구")
        self.assertEqual(gu_from_address("서울특별시강서구 공항대로 1", "서울"), "강서구")
        self.assertIsNone(gu_from_address("경기도 고양시 일산서구 1", "서울"))
        self.assertIsNone(gu_from_address("대전광역시 유성구 대학로 291", "서울"))
        self.assertIsNone(gu_from_address("", "서울"))

    def test_kopis_error_body(self):
        with self.assertRaises(CollectError):
            kopis.parse_dbs("<dbs><db><returncode>02</returncode><errmsg>SERVICE KEY IS NOT REGISTERED</errmsg></db></dbs>")
        with self.assertRaises(CollectError):
            kopis.parse_dbs("<html>oops")
        self.assertEqual(kopis.parse_dbs("<dbs></dbs>"), [])
        self.assertEqual(kopis.parse_dbs("<dbs/>"), [])

    def test_kopis_windows_split_31_days(self):
        parts = kopis.windows(date(2026, 10, 1), date(2026, 12, 15))
        self.assertEqual(parts[0], (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(parts[-1][1], date(2026, 12, 15))
        self.assertTrue(all((b - a).days < 31 for a, b in parts))

    def test_tour_errors(self):
        xml = (
            "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
            "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
            "<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        )
        with self.assertRaisesRegex(CollectError, "Decoding"):
            tourapi.parse_page(xml)
        with self.assertRaisesRegex(CollectError, "11"):
            tourapi.parse_page('{"responseTime":"x","resultCode":"11","resultMsg":"NO_MANDATORY_REQUEST_PARAMETERS_ERROR"}')
        self.assertEqual(tourapi.parse_page(tour_page([]))[0], [])

    def test_tour_type_mapping(self):
        self.assertEqual(tourapi.activity_type_of({"lclsSystm2": "EV01", "title": "가을 축제"}), "축제")
        self.assertEqual(tourapi.activity_type_of({"lclsSystm2": "EV02", "title": "음악회"}), "공연")
        self.assertEqual(tourapi.activity_type_of({"lclsSystm2": "EV03", "title": "근대 미술 특별전"}), "전시")
        self.assertEqual(tourapi.activity_type_of({"lclsSystm2": "EV03", "title": "야시장"}), "축제")
        self.assertEqual(tourapi.activity_type_of({"cat2": "A0207", "title": "옛 분류 축제"}), "축제")
        self.assertEqual(tourapi.activity_type_of({"cat2": "A0208", "cat3": "A02080500", "title": "옛 전시회"}), "전시")

    def test_tour_key_normalized(self):
        self.assertEqual(tourapi.normalize_key("abc%2Bdef%3D%3D"), "abc+def==")
        self.assertEqual(tourapi.normalize_key("abc+def=="), "abc+def==")


class CollectTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(runner, "today_kst", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def gather(self, calls, opts=None, **kw):
        transport = make_transport(calls, **kw)
        return asyncio.run(
            runner.gather_rows(opts or runner.CollectOptions(), "kopis-test-key", "tour%2Btest%3D%3D", transport)
        )

    def test_rows_and_filters(self):
        calls = []
        rows, reports, wf, wt = self.gather(calls)
        self.assertEqual((wf, wt), (TODAY, date(2026, 11, 10)))
        by_id = {r["external_id"]: r for r in rows}
        self.assertEqual(
            set(by_id),
            {"KOPIS:PF302715", "TOUR:2786391", "TOUR:2786392", "TOUR:2786395", "TOUR:3000001"},
        )

        play = by_id["KOPIS:PF302715"]
        self.assertEqual(play["activity_type"], "공연")
        self.assertEqual(play["region"], "중구")
        self.assertEqual(play["place"], "드림아트홀 [대전]")
        self.assertEqual(play["starts_at"], datetime(2026, 10, 14, 0, 0))
        self.assertEqual(play["ends_at"], datetime(2026, 10, 17, 23, 59, 59))
        self.assertEqual(play["cost"], "전석 30,000원")
        self.assertAlmostEqual(play["lat"], 36.3243771)
        self.assertTrue(play["image_url"].startswith("https://www.kopis.or.kr/"))
        self.assertIn("mt20Id=PF302715", play["source_url"])
        self.assertIn("예매 놀유니버스", play["description"])
        self.assertIn("공연예술통합전산망", play["description"])

        fireworks = by_id["TOUR:2786391"]
        self.assertEqual((fireworks["activity_type"], fireworks["region"]), ("축제", "영등포구"))
        self.assertEqual((fireworks["lat"], fireworks["lng"]), (37.5284, 126.9341))
        self.assertIn("문의 02-123-4567 (평일)", fireworks["description"])
        self.assertEqual(fireworks["image_url"], "https://tong.visitkorea.or.kr/cms/a.jpg")

        exhibit = by_id["TOUR:2786392"]  # 주소가 비면 lDongSignguCd로 구를 찾는다
        self.assertEqual((exhibit["activity_type"], exhibit["region"]), ("전시", "종로구"))
        self.assertEqual(by_id["TOUR:2786395"]["activity_type"], "공연")
        self.assertEqual(by_id["TOUR:3000001"]["region"], "유성구")

        kopis_dj = next(r for r in reports if r.source == "KOPIS" and r.area == "대전")
        self.assertEqual(kopis_dj.kept, 1)
        self.assertEqual(kopis_dj.skipped.get("오픈런(상시 공연)"), 1)
        self.assertEqual(kopis_dj.skipped.get("90일 넘는 장기 공연"), 1)
        tour_seoul = next(r for r in reports if r.source == "한국관광공사" and r.area == "서울")
        self.assertEqual(tour_seoul.skipped, {"90일 넘는 장기 행사": 1, "기간 밖": 1, "ID·제목 없음": 1})

        tour_calls = [c for c in calls if c.url.host == "apis.data.go.kr"]
        self.assertTrue(all(c.url.params["serviceKey"] == "tour+test==" for c in tour_calls))
        self.assertEqual({c.url.params["lDongRegnCd"] for c in tour_calls}, {"11", "30"})
        self.assertNotIn("areaCode", tour_calls[0].url.params)
        facility_calls = [c for c in calls if c.url.path.endswith("/prfplc/FC000752")]
        self.assertEqual(len(facility_calls), 1)

    def test_one_source_failing_does_not_stop_the_other(self):
        calls = []
        bad_key = "<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>"
        rows, reports, *_ = self.gather(calls, tour_error=bad_key)
        self.assertEqual([r["external_id"] for r in rows], ["KOPIS:PF302715"])
        tour_errors = [r.error for r in reports if r.source == "한국관광공사"]
        self.assertTrue(all("SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in e for e in tour_errors))

    def test_kopis_retries_when_blocked(self):
        """요청이 잦아 400 Request Blocked가 오면 다시 불러서 받는다. 계속 막히면 인증키 탓으로 돌리지 않는다."""
        inner = make_transport([])
        seen: dict[str, int] = {}

        def flaky(request):
            if request.url.host == "kopis.or.kr":
                seen[request.url.path] = seen.get(request.url.path, 0) + 1
                if seen[request.url.path] == 1 and "PF302715" in request.url.path:
                    return httpx.Response(400, text=KOPIS_BLOCKED)
            return inner.handler(request)

        opts = runner.CollectOptions(sources="kopis", areas="대전")
        rows, reports, *_ = asyncio.run(runner.gather_rows(opts, "key", "", httpx.MockTransport(flaky)))
        self.assertEqual([r["external_id"] for r in rows], ["KOPIS:PF302715"])
        self.assertEqual(seen["/openApi/restful/pblprfr/PF302715"], 2)

        always = httpx.MockTransport(lambda request: httpx.Response(400, text=KOPIS_BLOCKED))
        rows, reports, *_ = asyncio.run(runner.gather_rows(opts, "key", "", always))
        self.assertEqual(rows, [])
        self.assertIn("Request Blocked", reports[0].error)
        self.assertNotIn("인증키", reports[0].error)

    def test_tour_pages_until_total(self):
        def item(i):
            return {
                "contentid": str(5000 + i), "title": f"행사 {i}", "eventstartdate": "20261020",
                "eventenddate": "20261021", "addr1": "서울특별시 마포구 월드컵로 1", "lDongRegnCd": "11",
                "lclsSystm2": "EV01",
            }

        calls = []

        def handler(request):
            calls.append(request)
            page = int(request.url.params["pageNo"])
            items = [item(i) for i in range(100)] if page == 1 else [item(i) for i in range(100, 150)]
            return httpx.Response(200, text=tour_page(items, total=150))

        opts = runner.CollectOptions(sources="tour", areas="서울")
        rows, *_ = asyncio.run(runner.gather_rows(opts, "", "key", httpx.MockTransport(handler)))
        self.assertEqual(len(rows), 150)
        self.assertEqual([c.url.params["pageNo"] for c in calls], ["1", "2"])

    def test_missing_key_is_reported(self):
        transport = make_transport([])
        rows, reports, *_ = asyncio.run(runner.gather_rows(runner.CollectOptions(sources="kopis"), "", "", transport))
        self.assertEqual(rows, [])
        self.assertTrue(all("KOPIS_API_KEY" in r.error for r in reports))

    def test_upsert_is_idempotent_and_keeps_ids(self):
        _, db = memory_session()
        calls = []
        rows, *_ = self.gather(calls)
        self.assertEqual(runner.upsert(db, rows), (5, 0))
        first_ids = {a.external_id: a.activity_id for a in db.query(Activity)}

        rows[0]["title"] = rows[0]["title"] + " (변경)"
        self.assertEqual(runner.upsert(db, rows), (0, 1))
        self.assertEqual(db.query(Activity).count(), 5)
        self.assertEqual({a.external_id: a.activity_id for a in db.query(Activity)}, first_ids)

    def test_options_validation(self):
        with self.assertRaises(ValueError):
            runner.CollectOptions(areas="부산")
        with self.assertRaises(ValueError):
            runner.CollectOptions(sources="museum")
        self.assertEqual(runner.CollectOptions(areas=" 대전 , 서울 ").areas, ("대전", "서울"))


class SchemaTests(unittest.TestCase):
    def test_old_table_gets_new_columns(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        with engine.begin() as conn:  # 예전 db_schema.sql 그대로의 테이블
            conn.execute(text(
                "create table activities (activity_id integer primary key, activity_type varchar(32) not null, "
                "title varchar(255) not null, place varchar(255), region varchar(64), starts_at timestamp, "
                "cost varchar(64), description text, source varchar(32) default 'user', lat double precision, "
                "lng double precision, created_at timestamp)"
            ))
            conn.execute(text("insert into activities (activity_type, title) values ('러닝', '예전 활동')"))
        added = ensure_schema(engine)
        self.assertEqual(set(added), {"activities.ends_at", "activities.external_id", "activities.source_url", "activities.image_url"})
        columns = {c["name"] for c in inspect(engine).get_columns("activities")}
        self.assertTrue({"ends_at", "external_id", "source_url", "image_url"} <= columns)
        self.assertEqual(ensure_schema(engine), [])  # 두 번째는 할 일이 없다
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("select title from activities")).scalar(), "예전 활동")


class ApiTests(unittest.TestCase):
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
        self.assertEqual(self.client.post("/collect").status_code, 401)
        self.assertEqual(self.client.post("/collect", headers={"x-collect-token": "wrong"}).status_code, 401)

    def test_collect_then_list(self):
        calls = []
        original = runner.gather_rows

        def fake_gather(opts, kopis_key="", tour_key="", transport=None, culture_key=""):
            return original(opts, kopis_key, tour_key, make_transport(calls))

        with mock.patch.object(runner, "today_kst", return_value=TODAY), mock.patch.object(
            runner, "gather_rows", fake_gather
        ):
            res = self.client.post("/collect", headers={"x-collect-token": "test-token"}, params={"dry_run": "true"})
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual((res.json()["collected"], res.json()["inserted"]), (5, 0))

            res = self.client.post("/collect", headers={"x-collect-token": "test-token"})
            self.assertEqual(res.status_code, 200, res.text)
            body = res.json()
            self.assertEqual(body["inserted"], 5)
            res2 = self.client.post("/collect", headers={"x-collect-token": "test-token"})
            self.assertEqual((res2.json()["inserted"], res2.json()["unchanged"]), (0, 5))

        acts = self.client.get("/activities").json()
        api_rows = [a for a in acts if a.get("external_id")]
        self.assertEqual(len(api_rows), 5)
        self.assertTrue(all(a["ends_at"] for a in api_rows))
        self.assertEqual({a["source"] for a in api_rows}, {"KOPIS", "한국관광공사"})

        # 기간 겹침 필터: 10/16에 하는 것 = 꽃잠(10/14~17) + 특별전(10/1~11/30)
        res = self.client.get("/activities", params={"date_from": "2026-10-16T00:00:00", "date_to": "2026-10-16T23:59:59"})
        titles = {a["title"] for a in res.json() if a.get("external_id")}
        self.assertEqual(titles, {"꽃잠 [대전]", "한국 근대 미술 특별전"})

        res = self.client.get("/activities", params={"region": "중구", "type": "공연"})
        self.assertIn("꽃잠 [대전]", [a["title"] for a in res.json()])

        stats = self.client.get("/stats/activities").json()
        sources = {b["key"]: b["count"] for b in stats["by_source"]}
        self.assertEqual((sources.get("KOPIS"), sources.get("한국관광공사")), (1, 4))

    def test_bad_options(self):
        res = self.client.post("/collect", headers={"x-collect-token": "test-token"}, params={"areas": "부산"})
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
