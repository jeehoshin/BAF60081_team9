"""입력 검증 · 출처 고정 · 동시 참여 순서 · 모임 나가기 테스트.

실행: cd backend && python -m unittest discover tests -v
"""

import os
import unittest
import uuid
from datetime import datetime, timedelta

os.environ["USE_MEMORY"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Meetup  # noqa: E402


def soon(hours: int = 48) -> str:
    return (datetime.now() + timedelta(hours=hours)).replace(microsecond=0).isoformat()


class ValidationAndLeaveTests(unittest.TestCase):
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
        r = self.client.post("/activities", json={"activity_type": "러닝", "title": "검증용 러닝"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def meetup(self, host, act, **extra):
        body = {"activity_id": act["activity_id"], "host_id": host["user_id"], "name": "검증 모임",
                "capacity": 4, "meet_at": soon(), **extra}
        r = self.client.post("/meetups", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def join(self, meetup_id, user):
        return self.client.post(f"/meetups/{meetup_id}/participants", json={"user_id": user["user_id"]})

    # ---- 활동 등록: 출처 고정 -----------------------------------------------
    def test_source_is_always_user(self):
        r = self.client.post("/activities", json={"activity_type": "러닝", "title": "출처 위조", "source": "KOPIS"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["source"], "user")

    def test_only_running_even_with_fake_source(self):
        r = self.client.post("/activities", json={"activity_type": "공연", "title": "가짜 공연", "source": "KOPIS"})
        self.assertEqual(r.status_code, 400)

    def test_blank_title_rejected(self):
        r = self.client.post("/activities", json={"activity_type": "러닝", "title": "   "})
        self.assertEqual(r.status_code, 400)

    def test_activities_limit(self):
        self.running()
        self.running()
        r = self.client.get("/activities", params={"limit": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(self.client.get("/activities", params={"limit": 0}).status_code, 422)

    # ---- 이용자 등록 ---------------------------------------------------------
    def test_user_choices_are_limited(self):
        bad_age = self.client.post("/users", json={"nickname": "나이이상", "age_group": "999대"})
        self.assertEqual(bad_age.status_code, 422)
        bad_gender = self.client.post("/users", json={"nickname": "성별이상", "gender": "외계인"})
        self.assertEqual(bad_gender.status_code, 422)
        old = self.client.post("/users", json={"nickname": "구버전값", "age_group": "40대+"})
        self.assertEqual(old.status_code, 422)

    def test_choose_not_to_say_is_stored_empty(self):
        r = self.client.post("/users", json={"nickname": f"비공개{uuid.uuid4().hex[:6]}", "gender": "선택 안 함", "age_group": ""})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertIsNone(r.json()["gender"])
        self.assertIsNone(r.json()["age_group"])

    def test_nickname_unique_ignoring_case_and_spaces(self):
        base = f"Dup{uuid.uuid4().hex[:6]}"
        self.assertEqual(self.client.post("/users", json={"nickname": base}).status_code, 201)
        self.assertEqual(self.client.post("/users", json={"nickname": f"  {base.lower()} "}).status_code, 409)
        self.assertEqual(self.client.post("/users", json={"nickname": "   "}).status_code, 422)

    # ---- 모임 만들기 ---------------------------------------------------------
    def test_meetup_input_checks(self):
        host, act = self.user(), self.running()
        base = {"activity_id": act["activity_id"], "host_id": host["user_id"], "capacity": 4}

        past = self.client.post("/meetups", json={**base, "name": "지난 모임", "meet_at": "2020-01-01T10:00:00"})
        self.assertEqual(past.status_code, 400)
        self.assertEqual(self.client.post("/meetups", json={**base, "name": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/meetups", json={**base, "name": "가" * 129}).status_code, 422)
        self.assertEqual(self.client.post("/meetups", json={**base, "name": "ok", "age_filter": "10대"}).status_code, 422)
        no_time = self.client.post("/meetups", json={**base, "name": "시각 미정"})
        self.assertEqual(no_time.status_code, 201, no_time.text)

    # ---- 참여: 정원이 찬 모임에서 재참여 --------------------------------------------
    def test_rejoin_full_meetup_is_ok_but_new_user_rejected(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act, capacity=4)
        members = [self.user() for _ in range(3)]
        for u in members:
            self.assertEqual(self.join(m["meetup_id"], u).status_code, 201)
        # 정원 4/4. 이미 들어온 사람이 다시 눌러도 오류 없이 처리
        self.assertEqual(self.join(m["meetup_id"], members[0]).status_code, 201)
        # 새로 오는 사람은 거절
        late = self.join(m["meetup_id"], self.user())
        self.assertEqual(late.status_code, 400)
        self.assertIn("정원", late.json()["detail"])

    def test_meetup_list_has_participant_counts(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act)
        self.join(m["meetup_id"], self.user())
        rows = self.client.get("/meetups").json()
        mine = next(r for r in rows if r["meetup_id"] == m["meetup_id"])
        self.assertEqual(mine["participant_count"], 2)

    # ---- 호스트 수정 ---------------------------------------------------------
    def test_patch_cannot_break_conditions_of_current_members(self):
        host, act = self.user("여", "30대"), self.running()
        m = self.meetup(host, act)
        mate = self.user("여", "30대")
        self.assertEqual(self.join(m["meetup_id"], mate).status_code, 201)

        # 호스트 본인이 못 맞추는 조건
        r = self.client.patch(f"/meetups/{m['meetup_id']}", json={"host_id": host["user_id"], "age_filter": "20대"})
        self.assertEqual(r.status_code, 400)
        # 참여자 중 조건에 안 맞는 사람이 생기는 변경
        guy = self.user("남", "30대")
        self.assertEqual(self.join(m["meetup_id"], guy).status_code, 201)
        r = self.client.patch(f"/meetups/{m['meetup_id']}", json={"host_id": host["user_id"], "gender_filter": "여"})
        self.assertEqual(r.status_code, 400)
        # 모두 맞는 조건은 통과
        r = self.client.patch(f"/meetups/{m['meetup_id']}", json={"host_id": host["user_id"], "age_filter": "30대"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["age_filter"], "30대")

    def test_patch_checks_name_and_time(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act)
        url = f"/meetups/{m['meetup_id']}"
        self.assertEqual(self.client.patch(url, json={"host_id": host["user_id"], "name": " "}).status_code, 422)
        self.assertEqual(self.client.patch(url, json={"host_id": host["user_id"], "name": "나" * 200}).status_code, 422)
        past = self.client.patch(url, json={"host_id": host["user_id"], "meet_at": "2020-01-01T10:00:00"})
        self.assertEqual(past.status_code, 400)

    def test_patch_name_only_works_even_if_meetup_time_has_passed(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act)
        old = datetime.now() - timedelta(days=1)
        db = SessionLocal()
        try:
            db.get(Meetup, m["meetup_id"]).meet_at = old
            db.commit()
        finally:
            db.close()
        r = self.client.patch(
            f"/meetups/{m['meetup_id']}",
            json={"host_id": host["user_id"], "name": "이름만 고침", "meet_at": old.isoformat()},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], "이름만 고침")

    # ---- 모임 나가기 ---------------------------------------------------------
    def test_leave_meetup(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act)
        mid = m["meetup_id"]
        mate = self.user()
        self.assertEqual(self.join(mid, mate).status_code, 201)

        out = self.client.delete(f"/meetups/{mid}/participants/{mate['user_id']}")
        self.assertEqual(out.status_code, 200, out.text)
        self.assertEqual(out.json()["participant_count"], 1)

        # 나간 뒤에는 채팅 불가, 다시 참여는 가능
        talk = self.client.post(f"/meetups/{mid}/messages", json={"user_id": mate["user_id"], "body": "안녕"})
        self.assertEqual(talk.status_code, 403)  # 나간 사람은 참여자가 아니므로 권한 없음
        self.assertEqual(self.join(mid, mate).status_code, 201)

    def test_leave_rules(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act)
        mid = m["meetup_id"]
        # 호스트는 나갈 수 없음
        self.assertEqual(self.client.delete(f"/meetups/{mid}/participants/{host['user_id']}").status_code, 400)
        # 참여하지 않은 사람 / 없는 모임
        stranger = self.user()
        self.assertEqual(self.client.delete(f"/meetups/{mid}/participants/{stranger['user_id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/meetups/999999/participants/{stranger['user_id']}").status_code, 404)

    def test_leaving_frees_a_seat(self):
        host, act = self.user(), self.running()
        m = self.meetup(host, act, capacity=4)
        mid = m["meetup_id"]
        members = [self.user() for _ in range(3)]
        for u in members:
            self.join(mid, u)
        newcomer = self.user()
        self.assertEqual(self.join(mid, newcomer).status_code, 400)
        self.client.delete(f"/meetups/{mid}/participants/{members[0]['user_id']}")
        self.assertEqual(self.join(mid, newcomer).status_code, 201)


if __name__ == "__main__":
    unittest.main()
