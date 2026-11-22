"""상세 설명·관람 조건 수집 테스트 (인증키·인터넷 없이 돌아간다).

실행: cd backend && python -m unittest discover tests -v

행사 이름과 설명은 테스트용으로 지어낸 값이라 화면에 나오지 않는다.
"""

import os

os.environ["USE_MEMORY"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from unittest import mock  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.collectors import common, kopis, runner  # noqa: E402
from app.collectors.common import (  # noqa: E402
    CollectError,
    SourceReport,
    fill_details,
    parse_age_months,
    parse_runtime_min,
    plain_text,
    text_hash,
)
from app.database import Base  # noqa: E402
from app.models import Activity  # noqa: E402

TODAY = date(2026, 11, 22)
kopis.MIN_INTERVAL = kopis.RETRY_WAIT = 0

# ---------- 가짜 응답 ----------

KOPIS_LIST = """<?xml version="1.0" encoding="UTF-8"?><dbs>
<db><mt20id>PF900001</mt20id><prfnm>테스트 가족 서커스</prfnm><prfpdfrom>2026.11.28</prfpdfrom><prfpdto>2026.11.28</prfpdto><fcltynm>테스트 어린이극장</fcltynm><poster>http://www.kopis.or.kr/upload/p.gif</poster><genrenm>서커스/마술</genrenm><openrun>N</openrun></db>
</dbs>"""

KOPIS_DETAIL = """<?xml version="1.0" encoding="UTF-8"?><dbs><db><mt20id>PF900001</mt20id><prfnm>테스트 가족 서커스</prfnm>
<prfruntime>1시간 10분 (인터미션 10분 포함)</prfruntime><prfage>30개월 이상</prfage><pcseguidance>전석 16,000원</pcseguidance>
<sty>&lt;p&gt;아이와 어른이 함께 보는 서커스.&amp;nbsp;저글링과 공중 곡예가 이어진다.&lt;/p&gt;</sty>
<mt10id>FC900001</mt10id><dtguidance>토요일(15:00)</dtguidance>
<styurls><styurl>http://www.kopis.or.kr/upload/i1.jpg</styurl><styurl>http://www.kopis.or.kr/upload/i2.jpg</styurl></styurls>
</db></dbs>"""

KOPIS_FACILITY = """<?xml version="1.0" encoding="UTF-8"?><dbs><db><fcltynm>테스트 어린이극장</fcltynm><mt10id>FC900001</mt10id>
<adres>서울특별시 송파구 올림픽로 1</adres><la>37.51</la><lo>127.10</lo></db></dbs>"""


def tour_page(items):
    return json.dumps({"response": {"header": {"resultCode": "0000"}, "body": {
        "items": {"item": items} if items else "", "totalCount": len(items)}}}, ensure_ascii=False)


TOUR_ITEM = {"contentid": "3900001", "title": "테스트 겨울 축제", "eventstartdate": "20261120", "eventenddate": "20261130",
             "addr1": "서울특별시 마포구 월드컵로 1", "lDongRegnCd": "11", "lclsSystm2": "EV01", "mapx": "126.9", "mapy": "37.56"}
TOUR_OVERVIEW = "<p>겨울 밤을 밝히는 빛 축제입니다.<br>가족 체험 부스와 공연이 함께 열립니다.</p>"

CULTURE_LIST = ("<response><header><resultCode>00</resultCode></header><body><totalCount>1</totalCount><items>"
                "<item><seq>990001</seq><title>테스트 기획전</title><startDate>20261101</startDate><endDate>20261231</endDate>"
                "<place>테스트 미술관</place><realmName>전시</realmName><area>서울</area><sigungu>종로구</sigungu>"
                "<gpsX>126.98</gpsX><gpsY>37.58</gpsY></item></items></body></response>")
CULTURE_DETAIL = ("<response><header><resultCode>00</resultCode></header><body><items><item><seq>990001</seq>"
                  "<title>테스트 기획전</title><contents1>&lt;p&gt;한국 근대 회화 120점을 시대별로 소개하는 기획전.&lt;/p&gt;</contents1>"
                  "<phone>02-000-0000</phone></item></items></body></response>")


def transport(calls, tour_detail_status=200, empty_overview=False):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        url = request.url
        if url.host == "kopis.or.kr":
            path = url.path.removeprefix("/openApi/restful/")
            if path == "pblprfr":
                ok = url.params["signgucode"] == "11" and url.params["shcate"] == "EEEB"
                return httpx.Response(200, text=KOPIS_LIST if ok else "<dbs></dbs>")
            if path == "pblprfr/PF900001":
                return httpx.Response(200, text=KOPIS_DETAIL)
            if path == "prfplc/FC900001":
                return httpx.Response(200, text=KOPIS_FACILITY)
            return httpx.Response(404)
        if url.host == "apis.data.go.kr":
            if url.path.endswith("/searchFestival2"):
                return httpx.Response(200, text=tour_page([TOUR_ITEM] if url.params.get("lDongRegnCd") == "11" else []))
            if url.path.endswith("/detailCommon2"):
                if tour_detail_status != 200:
                    return httpx.Response(tour_detail_status, text="error")
                overview = "" if empty_overview else TOUR_OVERVIEW
                return httpx.Response(200, text=tour_page([{"contentid": url.params["contentId"], "overview": overview}]))
            if url.path.endswith("/realm2"):
                body = CULTURE_LIST if url.params.get("sido") == "서울" else CULTURE_LIST.replace("<item>", "<x>").replace("</item>", "</x>")
                return httpx.Response(200, text=body)
            if url.path.endswith("/detail2"):
                return httpx.Response(200, text=CULTURE_DETAIL)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def gather(calls, fetch_details=True, detail_skip=None, **kw):
    opts = runner.CollectOptions(areas="서울")
    with mock.patch.object(runner, "today_kst", return_value=TODAY):
        rows, reports, *_ = asyncio.run(runner.gather_rows(
            opts, "kopis-key", "tour-key", transport(calls, **kw), culture_key="culture-key",
            fetch_details=fetch_details, detail_skip=detail_skip,
        ))
    return {r["external_id"]: r for r in rows}, {r.source: r for r in reports}


def detail_calls(calls):
    return [c for c in calls if c.url.path.endswith(("/detailCommon2", "/detail2"))]


# ---------- 테스트 ----------

class ParseTests(unittest.TestCase):
    def test_age_months(self):
        cases = {
            "전체 관람가": 0, "24개월 이상": 24, "36개월 이상 관람가": 36, "만 7세 이상": 84, "12세 이상": 144,
            "만 13세 이상": 156, "초등학생 이상": 84, "중학생 이상": 144, "청소년 관람불가": 228,
            "8세이상 관람가(2019년생 이상)": 96, "": None, None: None, "미정": None,
        }
        for raw, want in cases.items():
            self.assertEqual(parse_age_months(raw), want, raw)

    def test_runtime_min(self):
        cases = {
            "1시간 30분": 90, "90분": 90, "1시간": 60, "40분": 40, "2시간 10분": 130,
            "1시간 30분(인터미션 15분 포함)": 90, "1시간 30분 인터미션 15분": 90, "": None, None: None, "미정": None,
        }
        for raw, want in cases.items():
            self.assertEqual(parse_runtime_min(raw), want, raw)

    def test_plain_text_and_hash(self):
        self.assertEqual(plain_text("&lt;p&gt;가족&amp;nbsp;연극&lt;/p&gt;<br> 두 번째"), "가족 연극 두 번째")
        self.assertIsNone(plain_text("<p> </p>"))
        self.assertEqual(len(plain_text("가" * 5000)), common.DETAIL_MAX_CHARS)
        self.assertEqual(text_hash("같은 글"), text_hash("같은 글"))
        self.assertNotEqual(text_hash("글 하나"), text_hash("글 둘"))
        self.assertIsNone(text_hash(None))


class CollectorTests(unittest.TestCase):
    def test_kopis_row_gets_synopsis_age_runtime_images(self):
        rows, reports = gather([])
        row = rows["KOPIS:PF900001"]
        self.assertEqual(row["detail_text"], "아이와 어른이 함께 보는 서커스. 저글링과 공중 곡예가 이어진다.")
        self.assertEqual(row["detail_source"], "sty")
        self.assertEqual(row["text_hash"], text_hash(row["detail_text"]))
        self.assertEqual(row["min_age_months"], 30)
        self.assertEqual(row["runtime_min"], 70)
        self.assertEqual(json.loads(row["intro_images"]), ["https://www.kopis.or.kr/upload/i1.jpg", "https://www.kopis.or.kr/upload/i2.jpg"])
        self.assertIsNotNone(row["detail_checked_at"])
        self.assertIn("관람연령 30개월 이상", row["description"])  # 기존 description은 그대로
        self.assertEqual(reports["KOPIS"].details["fetched"], 1)

    def test_tour_and_culture_details(self):
        calls = []
        rows, reports = gather(calls)
        tour = rows["TOUR:3900001"]
        self.assertEqual(tour["detail_text"], "겨울 밤을 밝히는 빛 축제입니다. 가족 체험 부스와 공연이 함께 열립니다.")
        self.assertEqual(tour["detail_source"], "overview")
        self.assertNotIn("min_age_months", tour)  # 관람연령은 KOPIS에만 있다
        exh = rows["CULTURE:990001"]
        self.assertEqual(exh["detail_text"], "한국 근대 회화 120점을 시대별로 소개하는 기획전.")
        self.assertEqual(exh["detail_source"], "contents1")
        self.assertEqual(len(detail_calls(calls)), 2)
        detail = [c for c in calls if c.url.path.endswith("/detailCommon2")][0]
        self.assertEqual(detail.url.params["contentId"], "3900001")
        self.assertEqual(reports["한국관광공사"].details["with_text"], 1)

    def test_recently_checked_are_not_called(self):
        calls = []
        rows, reports = gather(calls, detail_skip={"TOUR:3900001", "CULTURE:990001"})
        self.assertEqual(detail_calls(calls), [])
        self.assertNotIn("detail_text", rows["TOUR:3900001"])  # 칸이 없으면 저장된 값을 그대로 둔다
        self.assertEqual(reports["한국관광공사"].details["skipped_recent"], 1)

    def test_details_off_by_default_in_gather(self):
        calls = []
        rows, _ = gather(calls, fetch_details=False)
        self.assertEqual(detail_calls(calls), [])
        self.assertIn("detail_text", rows["KOPIS:PF900001"])  # KOPIS는 원래 부르는 상세에서 꺼낸다

    def test_failed_detail_keeps_row_and_retries_later(self):
        rows, reports = gather([], tour_detail_status=500)
        self.assertIn("TOUR:3900001", rows)
        self.assertNotIn("detail_checked_at", rows["TOUR:3900001"])
        self.assertEqual(reports["한국관광공사"].details["failed"], 1)

    def test_empty_overview_is_still_marked_checked(self):
        rows, _ = gather([], empty_overview=True)
        tour = rows["TOUR:3900001"]
        self.assertIsNone(tour["detail_text"])
        self.assertIsNone(tour["detail_source"])
        self.assertIsNotNone(tour["detail_checked_at"])

    def test_limit_defers_the_rest(self):
        report = SourceReport(source="t", area="서울")
        rows = [{"external_id": f"T:{i}"} for i in range(5)]
        called = []

        async def fetch_one(row):
            called.append(row["external_id"])
            if row["external_id"] == "T:1":
                raise CollectError("boom")
            return "설명"

        asyncio.run(fill_details(rows, {"T:0"}, report, fetch_one, "overview", limit=2))
        self.assertEqual(sorted(called), ["T:1", "T:2"])
        self.assertEqual(report.details, {"fetched": 1, "with_text": 1, "failed": 1, "deferred": 2, "skipped_recent": 1})


class StoreTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def collect(self, db, calls, detail="new"):
        opts = runner.CollectOptions(areas="서울", detail=detail)
        original = runner.gather_rows

        def fake(opts, kopis_key="", tour_key="", transport=None, culture_key="", **kw):
            return original(opts, kopis_key, tour_key, transport_(calls), culture_key, **kw)

        transport_ = transport
        with mock.patch.object(runner, "today_kst", return_value=TODAY), mock.patch.object(runner, "gather_rows", fake):
            return runner.collect(db, opts, kopis_key="k", tour_key="t", culture_key="c")

    def test_second_run_skips_checked_details_and_keeps_text(self):
        with self.Session() as db:
            calls = []
            first = self.collect(db, calls)
            self.assertEqual(first["inserted"], 3)
            self.assertEqual(len(detail_calls(calls)), 2)
            cov = {c["source"]: c for c in first["text_coverage"]}
            self.assertEqual((cov["KOPIS"]["with_text"], cov["KOPIS"]["with_age"]), (1, 1))

            calls = []
            second = self.collect(db, calls)
            self.assertEqual(detail_calls(calls), [])  # 30일 안에 확인한 행사는 다시 부르지 않는다
            self.assertEqual(second["unchanged"], 3)
            tour = db.query(Activity).filter_by(external_id="TOUR:3900001").one()
            self.assertTrue(tour.detail_text.startswith("겨울 밤을"))  # 이전 설명이 지워지지 않는다

            # 30일이 지나면 다시 확인한다
            tour.detail_checked_at = datetime.now() - timedelta(days=40)
            db.commit()
            calls = []
            self.collect(db, calls)
            self.assertEqual([c.url.path.rsplit("/", 1)[-1] for c in detail_calls(calls)], ["detailCommon2"])

    def test_detail_all_and_off(self):
        with self.Session() as db:
            self.collect(db, [])
            calls = []
            self.collect(db, calls, detail="all")
            self.assertEqual(len(detail_calls(calls)), 2)
            calls = []
            self.collect(db, calls, detail="off")
            self.assertEqual(detail_calls(calls), [])

    def test_bad_detail_option(self):
        with self.assertRaises(ValueError):
            runner.CollectOptions(detail="sometimes")


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.database import SessionLocal
        from app.main import app

        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        with SessionLocal() as db:
            base = dict(activity_type="공연", region="송파구", source="KOPIS",
                        starts_at=datetime(2026, 11, 28), ends_at=datetime(2026, 11, 28, 23, 59, 59))
            kid = Activity(title="테스트 아기 인형극", external_id="KOPIS:TEST01", min_age_months=24, runtime_min=40,
                           detail_text="인형과 함께 노래하는 공연.", detail_source="sty", text_hash=text_hash("인형과 함께 노래하는 공연."),
                           intro_images=json.dumps(["https://example.org/a.jpg"]), detail_checked_at=datetime(2026, 11, 22), **base)
            teen = Activity(title="테스트 청소년 연극", external_id="KOPIS:TEST02", min_age_months=156, runtime_min=110, **base)
            unknown = Activity(title="테스트 연령 미상", external_id="KOPIS:TEST03", **base)
            db.add_all([kid, teen, unknown])
            db.commit()
            cls.kid_id = kid.activity_id

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def titles(self, **params):
        res = self.client.get("/activities", params=params)
        self.assertEqual(res.status_code, 200, res.text)
        return {a["title"] for a in res.json() if a["title"].startswith("테스트")}

    def test_age_and_runtime_filters(self):
        self.assertEqual(self.titles(age_months=36), {"테스트 아기 인형극"})
        self.assertEqual(self.titles(age_months=200), {"테스트 아기 인형극", "테스트 청소년 연극"})
        self.assertEqual(self.titles(max_runtime=60), {"테스트 아기 인형극"})
        self.assertEqual(self.client.get("/activities", params={"age_months": -1}).status_code, 422)

    def test_list_has_meta_but_not_text(self):
        row = next(a for a in self.client.get("/activities").json() if a["title"] == "테스트 아기 인형극")
        self.assertEqual((row["min_age_months"], row["runtime_min"]), (24, 40))
        self.assertNotIn("detail_text", row)

    def test_detail_endpoint_has_text(self):
        body = self.client.get(f"/activities/{self.kid_id}").json()
        self.assertEqual(body["detail"]["detail_text"], "인형과 함께 노래하는 공연.")
        self.assertEqual(body["detail"]["detail_source"], "sty")
        self.assertEqual(body["detail"]["intro_images"], ["https://example.org/a.jpg"])
        other = next(a for a in self.client.get("/activities").json() if a["title"] == "테스트 연령 미상")
        self.assertIsNone(self.client.get(f"/activities/{other['activity_id']}").json()["detail"])


if __name__ == "__main__":
    unittest.main()
