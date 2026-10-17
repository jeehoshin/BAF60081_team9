"""모임 규칙·호스트 수정·라이브 보드 테스트.

실행: cd backend && python -m unittest discover tests -v
"""

import os
import unittest

os.environ["USE_MEMORY"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class MeetupAndLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_user_activity_must_be_running(self):
        bad = self.client.post(
            "/activities",
            json={"activity_type": "축제", "title": "가짜 축제", "source": "user"},
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            "/activities",
            json={"activity_type": "러닝", "title": "유성천 저녁 러닝", "region": "유성구", "source": "user"},
        )
        self.assertEqual(ok.status_code, 201)

    def test_meetup_conditions_and_host_update(self):
        u_host = self.client.post(
            "/users",
            json={"nickname": "서연", "gender": "여", "age_group": "30대"},
        ).json()
        u_no_info = self.client.post(
            "/users",
            json={"nickname": "바다"},
        ).json()
        u_male = self.client.post(
            "/users",
            json={"nickname": "준호", "gender": "남", "age_group": "30대"},
        ).json()
        u_ok = self.client.post(
            "/users",
            json={"nickname": "지민", "gender": "여", "age_group": "30대"},
        ).json()

        act = self.client.post(
            "/activities",
            json={"activity_type": "러닝", "title": "한빛탑 야간 러닝", "region": "유성구"},
        ).json()

        # 정원 범위 밖(2명) 거절
        bad_cap = self.client.post(
            "/meetups",
            json={"activity_id": act["activity_id"], "host_id": u_host["user_id"], "name": "소규모", "capacity": 2},
        )
        self.assertEqual(bad_cap.status_code, 400)

        # 호스트 조건 불일치(30대 여성이 20대 조건 개설) 거절
        bad_host = self.client.post(
            "/meetups",
            json={
                "activity_id": act["activity_id"],
                "host_id": u_host["user_id"],
                "name": "20대만",
                "capacity": 4,
                "age_filter": "20대",
            },
        )
        self.assertEqual(bad_host.status_code, 400)

        # 정상 개설 (30대 여성 조건)
        meetup = self.client.post(
            "/meetups",
            json={
                "activity_id": act["activity_id"],
                "host_id": u_host["user_id"],
                "name": "30대 여성 러닝",
                "capacity": 4,
                "gender_filter": "여",
                "age_filter": "30대",
            },
        )
        self.assertEqual(meetup.status_code, 201, meetup.text)
        m_id = meetup.json()["meetup_id"]

        # 성별·연령대 미입력 이용자 참여 거절
        r_no_info = self.client.post(f"/meetups/{m_id}/participants", json={"user_id": u_no_info["user_id"]})
        self.assertEqual(r_no_info.status_code, 400)

        # 성별 불일치 이용자 참여 거절
        r_male = self.client.post(f"/meetups/{m_id}/participants", json={"user_id": u_male["user_id"]})
        self.assertEqual(r_male.status_code, 400)

        # 조건 충족 이용자 참여 성공 + gender 반환 확인
        r_ok = self.client.post(f"/meetups/{m_id}/participants", json={"user_id": u_ok["user_id"]})
        self.assertEqual(r_ok.status_code, 201)
        self.assertEqual(r_ok.json()["gender"], "여")
        self.assertEqual(r_ok.json()["age_group"], "30대")

        # 호스트가 아닌 사람이 수정 시도 → 403
        r_forbidden = self.client.patch(
            f"/meetups/{m_id}",
            json={"host_id": u_ok["user_id"], "name": "남이 바꾼 이름"},
        )
        self.assertEqual(r_forbidden.status_code, 403)

        # 호스트가 수정 시도 → 200
        r_patch = self.client.patch(
            f"/meetups/{m_id}",
            json={
                "host_id": u_host["user_id"],
                "name": "30대 여성 저녁 러닝 (수정됨)",
                "capacity": 6,
                "place_name": "한빛탑 광장",
            },
        )
        self.assertEqual(r_patch.status_code, 200)
        self.assertEqual(r_patch.json()["name"], "30대 여성 저녁 러닝 (수정됨)")
        self.assertEqual(r_patch.json()["capacity"], 6)
        self.assertEqual(r_patch.json()["place_name"], "한빛탑 광장")

        # 라이브 보드에 meetup_id와 activity_id가 포함되는지 확인
        live = self.client.get("/live").json()
        self.assertTrue(any(j.get("meetup_id") == m_id and j.get("activity_id") == act["activity_id"] for j in live["recent_joins"]))
        self.assertTrue(any(om.get("meetup_id") == m_id and om.get("activity_id") == act["activity_id"] for om in live["open_meetups"]))

        # 정보 미입력 이용자가 내 정보를 채우면(같은 user_id 유지) 조건 모임에 참여할 수 있다
        r_fill = self.client.patch(
            f"/users/{u_no_info['user_id']}",
            json={"gender": "여", "age_group": "30대"},
        )
        self.assertEqual(r_fill.status_code, 200, r_fill.text)
        self.assertEqual(r_fill.json()["user_id"], u_no_info["user_id"])
        self.assertEqual(r_fill.json()["gender"], "여")
        r_now_ok = self.client.post(f"/meetups/{m_id}/participants", json={"user_id": u_no_info["user_id"]})
        self.assertEqual(r_now_ok.status_code, 201, r_now_ok.text)

    def test_user_update_rules(self):
        u = self.client.post("/users", json={"nickname": "하늘", "age_group": "20대"}).json()

        # 보낸 칸만 바뀐다
        r = self.client.patch(f"/users/{u['user_id']}", json={"nickname": "하늘2"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["nickname"], "하늘2")
        self.assertEqual(r.json()["age_group"], "20대")

        # "선택 안 함"·빈 값은 지움으로 저장
        r = self.client.patch(f"/users/{u['user_id']}", json={"age_group": "선택 안 함", "gender": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["age_group"])
        self.assertIsNone(r.json()["gender"])

        # 닉네임은 비울 수 없다
        r = self.client.patch(f"/users/{u['user_id']}", json={"nickname": "  "})
        self.assertEqual(r.status_code, 400)

        # 없는 이용자 → 404
        r = self.client.patch("/users/999999", json={"nickname": "유령"})
        self.assertEqual(r.status_code, 404)
        r = self.client.get("/users/999999")
        self.assertEqual(r.status_code, 404)
        r = self.client.get(f"/users/{u['user_id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["nickname"], "하늘2")


if __name__ == "__main__":
    unittest.main()
