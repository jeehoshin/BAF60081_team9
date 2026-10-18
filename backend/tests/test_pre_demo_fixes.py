"""발표 전 점검(10/18)에서 찾은 버그 회귀 테스트.

실행: cd backend && python -m unittest discover tests -v
"""

import os
import unittest
import uuid
from datetime import datetime, timedelta

os.environ["USE_MEMORY"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def soon(hours: int = 48) -> str:
    return (datetime.now() + timedelta(hours=hours)).replace(microsecond=0).isoformat()


class PreDemoFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    # ---- 도우미 -----------------------------------------------------------
    def user(self, gender="여", age_group="30대", nickname=None):
        body = {"nickname": nickname or f"u{uuid.uuid4().hex[:8]}"}
        if gender:
            body["gender"] = gender
        if age_group:
            body["age_group"] = age_group
        r = self.client.post("/users", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def running(self):
        r = self.client.post("/activities", json={"activity_type": "러닝", "title": "점검용 러닝", "starts_at": soon()})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def meetup(self, host, act, **extra):
        body = {"activity_id": act["activity_id"], "host_id": host["user_id"], "name": "점검 모임",
                "capacity": 20, "meet_at": soon(), **extra}
        r = self.client.post("/meetups", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    # ---- 1. 모임톡: 메시지가 100개를 넘어도 최근 메시지가 보인다 --------------------
    def test_messages_show_latest_100_in_order(self):
        host = self.user()
        m = self.meetup(host, self.running())
        for i in range(105):
            r = self.client.post(f"/meetups/{m['meetup_id']}/messages",
                                 json={"user_id": host["user_id"], "body": f"msg {i}"})
            self.assertEqual(r.status_code, 201, r.text)
        msgs = self.client.get(f"/meetups/{m['meetup_id']}/messages").json()
        self.assertEqual(len(msgs), 100)
        self.assertEqual(msgs[-1]["body"], "msg 104")  # 가장 최근 메시지가 맨 아래
        self.assertEqual(msgs[0]["body"], "msg 5")  # 오래된 5개만 빠진다
        ids = [x["message_id"] for x in msgs]
        self.assertEqual(ids, sorted(ids))  # 오래된 것부터


    # ---- 2. 지도·모임톡 카드: 모임 수가 늘어도 쿼리 수가 늘지 않는다 ------------------
    def test_meetup_cards_do_not_query_per_meetup(self):
        from sqlalchemy import event

        from app.database import engine

        for _ in range(6):
            self.meetup(self.user(), self.running())  # 서로 다른 활동·호스트 6쌍
        count = {"n": 0}

        def _count(*_a, **_k):
            count["n"] += 1

        event.listen(engine, "before_cursor_execute", _count)
        try:
            r = self.client.get("/map/meetups")
        finally:
            event.remove(engine, "before_cursor_execute", _count)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()), 6)
        # 모임 목록 1 + 활동 1 + 호스트 1 + 참여자 1 + 메시지 수 1 = 5 (모임 수와 무관)
        self.assertLessEqual(count["n"], 5)


    # ---- 3. 내 정보 수정(PATCH /users)도 합류와 같은 검사를 한다 ----------------------
    def test_patch_user_rejects_values_that_join_rejects(self):
        u = self.user(nickname=f"p{uuid.uuid4().hex[:6]}")
        uid = u["user_id"]
        # 성인 대상 서비스: '10대'·'기타'는 합류에서도 수정에서도 안 된다
        self.assertEqual(self.client.patch(f"/users/{uid}", json={"age_group": "10대"}).status_code, 422)
        self.assertEqual(self.client.patch(f"/users/{uid}", json={"gender": "기타"}).status_code, 422)
        # 길이 초과는 DB 오류(500)가 아니라 422
        self.assertEqual(self.client.patch(f"/users/{uid}", json={"preferred_types": "공연," * 60}).status_code, 422)
        # 정상 값·'선택 안 함'은 그대로 된다
        r = self.client.patch(f"/users/{uid}", json={"age_group": "40대", "gender": "선택 안 함"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["age_group"], "40대")
        self.assertIsNone(r.json()["gender"])

    def test_patch_user_nickname_must_stay_unique(self):
        a = self.user(nickname=f"Dup{uuid.uuid4().hex[:6]}")
        b = self.user()
        r = self.client.patch(f"/users/{b['user_id']}", json={"nickname": a["nickname"].lower()})
        self.assertEqual(r.status_code, 409)
        # 내 닉네임의 대소문자만 바꾸는 것은 된다
        r = self.client.patch(f"/users/{a['user_id']}", json={"nickname": a["nickname"].upper()})
        self.assertEqual(r.status_code, 200, r.text)


    # ---- 4. 모임에 참여하지 않은 사람의 메시지 작성은 403 ----------------------------
    def test_non_participant_message_is_403(self):
        m = self.meetup(self.user(), self.running())
        outsider = self.user()
        r = self.client.post(f"/meetups/{m['meetup_id']}/messages",
                             json={"user_id": outsider["user_id"], "body": "끼워 주세요"})
        self.assertEqual(r.status_code, 403)


    # ---- 5. 없는 이용자의 좋아요는 500이 아니라 404 --------------------------------
    def test_like_with_unknown_user_is_404(self):
        act = self.running()
        r = self.client.post(f"/activities/{act['activity_id']}/likes", json={"user_id": 99_999_999})
        self.assertEqual(r.status_code, 404)
        ok = self.client.post(f"/activities/{act['activity_id']}/likes", json={"user_id": self.user()["user_id"]})
        self.assertEqual(ok.status_code, 201, ok.text)


    # ---- 6. KOPIS가 '전남광주' 한 줄로 주는 지역도 인구 10만 명당 값이 나온다 ----------
    def test_merged_area_population(self):
        from app import population as pop

        self.assertEqual(pop.population_of("전남광주"), 3_154_398)  # 광주 + 전남
        self.assertEqual(len(pop.POPULATION), 17)  # 시·도 표 자체는 그대로


if __name__ == "__main__":
    unittest.main()
