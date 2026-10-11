"""한국문화정보원 전시 수집기 테스트 (인증키·인터넷 없이 돌아간다).

실행: cd backend && python -m unittest discover tests -v

응답은 realm2(분야별 조회) XML 형식을 따랐다. 행사 이름은 테스트용으로 지어낸 값이라 화면에 나오지 않는다.
"""

import os

os.environ["USE_MEMORY"] = "1"

import asyncio  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime  # noqa: E402
from unittest import mock  # noqa: E402

import httpx  # noqa: E402

from app.collectors import culture, runner  # noqa: E402
from app.collectors.common import CollectError, SourceReport  # noqa: E402

TODAY = date(2026, 10, 11)


def item(seq, title, start, end, area="서울", sigungu="종로구", **extra):
    fields = {
        "serviceName": "공연/전시", "seq": seq, "title": title, "startDate": start, "endDate": end,
        "place": "테스트 갤러리", "realmName": "전시", "area": area, "sigungu": sigungu,
        "thumbnail": "http://www.culture.go.kr/upload/rdf/test.jpg", "gpsX": "126.98", "gpsY": "37.57",
    }
    fields.update(extra)
    inner = "".join(f"<{k}>{v}</{k}>" for k, v in fields.items())
    return f"<item>{inner}</item>"


def page(items, total=None):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>00</resultCode>'
        "<resultMsg>NORMAL SERVICE.</resultMsg></header><body>"
        f"<totalCount>{len(items) if total is None else total}</totalCount><PageNo>1</PageNo><numOfrows>100</numOfrows>"
        f"<items>{''.join(items)}</items></body></response>"
    )


SEOUL = [
    item("100001", "테스트 사진전", "20261001", "20261025"),
    item("100002", "테스트 상설전", "20250101", "20271231"),  # 장기
    item("100003", "지난 전시", "20260801", "20260830"),  # 기간 밖
    item("100004", "구 없는 전시", "20261010", "20261020", sigungu=""),
    item("100001", "테스트 사진전", "20261001", "20261025"),  # 같은 전시가 두 번
    item("", "아이디 없음", "20261010", "20261020"),
]
DAEJEON = [item("200001", "테스트 판화전", "20261015", "20261101", area="대전", sigungu="서구", gpsX="127.38", gpsY="36.35")]

AUTH_ERROR = (
    "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>"
    "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode>"
    "</cmmMsgHeader></OpenAPI_ServiceResponse>"
)


def make_transport(calls, body_for=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host != "apis.data.go.kr" or not request.url.path.endswith("/cultureinfo/realm2"):
            return httpx.Response(404)
        if body_for:
            return httpx.Response(200, text=body_for(request))
        sido = request.url.params["sido"]
        return httpx.Response(200, text=page(SEOUL if sido == "서울" else DAEJEON))

    return httpx.MockTransport(handler)


class CultureTests(unittest.TestCase):
    def gather(self, calls, body_for=None, **opts):
        options = runner.CollectOptions(sources="culture", **opts)
        with mock.patch.object(runner, "today_kst", return_value=TODAY):
            return asyncio.run(
                runner.gather_rows(options, transport=make_transport(calls, body_for), culture_key="culture%2Btest%3D%3D")
            )

    def test_rows_and_filters(self):
        calls = []
        rows, reports, wf, wt = self.gather(calls)
        by_id = {r["external_id"]: r for r in rows}
        self.assertEqual(set(by_id), {"CULTURE:100001", "CULTURE:200001"})

        photo = by_id["CULTURE:100001"]
        self.assertEqual((photo["activity_type"], photo["region"], photo["source"]), ("전시", "종로구", "한국문화정보원"))
        self.assertEqual(photo["starts_at"], datetime(2026, 10, 1, 0, 0))
        self.assertEqual(photo["ends_at"], datetime(2026, 10, 25, 23, 59, 59))
        self.assertEqual((photo["lat"], photo["lng"]), (37.57, 126.98))
        self.assertTrue(photo["image_url"].startswith("https://"))
        self.assertIn("한국문화정보원", photo["description"])
        self.assertIsNone(photo["cost"])
        self.assertEqual(by_id["CULTURE:200001"]["region"], "서구")

        seoul = next(r for r in reports if r.area == "서울")
        self.assertEqual(seoul.skipped, {"90일 넘는 장기 전시": 1, "기간 밖": 1, "구를 알 수 없음": 1, "ID·제목 없음": 1})
        self.assertEqual(seoul.kept, 1)  # 두 번 온 전시는 한 번만

        params = calls[0].url.params
        self.assertEqual(params["serviceKey"], "culture+test==")
        self.assertEqual((params["realmCode"], params["from"], params["to"]), ("D000", "20261011", "20261110"))
        self.assertEqual({c.url.params["sido"] for c in calls}, {"서울", "대전"})

    def test_long_exhibitions_kept_when_unlimited(self):
        rows, *_ = self.gather([], max_span_days=0)
        self.assertIn("CULTURE:100002", {r["external_id"] for r in rows})

    def test_pages_until_total(self):
        many = [item(str(300000 + i), f"전시 {i}", "20261010", "20261020") for i in range(150)]

        def body_for(request):
            n = int(request.url.params["PageNo"])
            return page(many[(n - 1) * 100 : n * 100], total=150)

        calls = []
        rows, *_ = self.gather(calls, body_for=body_for, areas="서울")
        self.assertEqual(len(rows), 150)
        self.assertEqual([c.url.params["PageNo"] for c in calls], ["1", "2"])

    def test_auth_error_is_reported(self):
        rows, reports, *_ = self.gather([], body_for=lambda r: AUTH_ERROR)
        self.assertEqual(rows, [])
        self.assertTrue(all("SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in r.error for r in reports))

    def test_parse_errors(self):
        with self.assertRaises(CollectError):
            culture.parse_page("not xml")
        with self.assertRaisesRegex(CollectError, "99"):
            culture.parse_page("<response><header><resultCode>99</resultCode><resultMsg>ERR</resultMsg></header></response>")
        self.assertEqual(culture.parse_page(page([]))[0], [])

    def test_other_city_is_skipped(self):
        report = SourceReport(source=culture.SOURCE, area="서울")
        raw = {"seq": "1", "title": "부산 전시", "startDate": "20261012", "endDate": "20261013", "area": "부산", "sigungu": "중구"}
        self.assertIsNone(culture.to_row(raw, "서울", TODAY, date(2026, 11, 10), 90, report))
        self.assertEqual(report.skipped, {"다른 지역": 1})

    def test_missing_key_is_reported(self):
        options = runner.CollectOptions(sources="culture", areas="대전")
        rows, reports, *_ = asyncio.run(runner.gather_rows(options, transport=make_transport([])))
        self.assertEqual(rows, [])
        self.assertIn("CULTURE_API_KEY", reports[0].error)


if __name__ == "__main__":
    unittest.main()
