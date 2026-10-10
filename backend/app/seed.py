from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Activity, Meetup, Message, Participant, User

# KAIST 대전 본원 주변 좌표
KAIST_GATE = (36.3664, 127.3636)
CREATIVE_HALL = (36.3703, 127.3627)
LIBRARY = (36.3696, 127.3622)
DUCK_POND = (36.3685, 127.3613)
GAPCHEON = (36.3668, 127.3765)
EOEUN = (36.3628, 127.3588)
YUSEONG_ART = (36.3745, 127.3889)
DAEJEON_STN = (36.3324, 127.4342)


def seed_demo_data(db: Session) -> None:
    """시연용 더미 데이터. 테이블이 비어 있을 때만 넣는다."""
    if db.query(Activity).count() > 0:
        return

    users = [
        User(nickname="유성러너", gender="남", age_group="20대", preferred_types="러닝,축제", preferred_regions="유성구"),
        User(nickname="창의관지킴이", gender="여", age_group="20대", preferred_types="전시,공연", preferred_regions="유성구"),
        User(nickname="튀소헌터", gender="남", age_group="20대", preferred_types="축제,러닝", preferred_regions="유성구,서구"),
        User(nickname="갤러리냥", gender="여", age_group="20대", preferred_types="전시,공연", preferred_regions="유성구"),
        User(nickname="밤샘피아니스트", gender="남", age_group="30대", preferred_types="공연", preferred_regions="유성구"),
    ]
    db.add_all(users)
    db.flush()

    now = datetime.now().replace(minute=0, second=0, microsecond=0)

    def at(days: int, hour: int, minute: int = 0) -> datetime:
        return (now + timedelta(days=days)).replace(hour=hour, minute=minute)

    activities = [
        Activity(
            activity_type="러닝", title="갑천 저녁 러닝", place="갑천 둔치", region="유성구",
            starts_at=at(1, 19), cost="무료",
            description="초보 환영 5km. 끝나고 성심당 경유 가능", source="user",
            lat=GAPCHEON[0], lng=GAPCHEON[1],
        ),
        Activity(
            activity_type="전시", title="넙죽이 팬아트 전시", place="유성 문화공간", region="유성구",
            starts_at=at(2, 14), cost="무료",
            description="넙죽이 팬아트 20점 + 굿즈", source="API",
            lat=YUSEONG_ART[0], lng=YUSEONG_ART[1],
        ),
        Activity(
            activity_type="축제", title="캠퍼스 번개 버스킹", place="KAIST 도서관 앞", region="유성구",
            starts_at=at(3, 17), cost="무료",
            description="노래·기타 아무나. 구경만 해도 OK", source="user",
            lat=LIBRARY[0], lng=LIBRARY[1],
        ),
        Activity(
            activity_type="공연", title="대전 재즈 나잇", place="대전역 인근 라이브홀", region="동구",
            starts_at=at(4, 19), cost="20,000원",
            description="퇴근길 재즈. 같이 버스 타고 가요", source="API",
            lat=DAEJEON_STN[0], lng=DAEJEON_STN[1],
        ),
        Activity(
            activity_type="러닝", title="오리연못 산책 런", place="KAIST 오리연못", region="유성구",
            starts_at=at(2, 7), cost="무료",
            description="아침 3km 가볍게. 거위 조심", source="user",
            lat=DUCK_POND[0], lng=DUCK_POND[1],
        ),
    ]
    db.add_all(activities)
    db.flush()

    meetups = [
        Meetup(
            activity_id=activities[0].activity_id, host_id=users[0].user_id,
            name="갑천 같이 뛰어요", meet_at=at(1, 18, 45), capacity=8,
            place_name="KAIST 정문", lat=KAIST_GATE[0], lng=KAIST_GATE[1],
            how="정문 집결 → 갑천까지 조깅 → 5km 후 성심당 DCC점",
        ),
        Meetup(
            activity_id=activities[1].activity_id, host_id=users[1].user_id,
            name="전시 보고 카페", meet_at=at(2, 13, 30), capacity=6,
            place_name="창의학습관 앞", lat=CREATIVE_HALL[0], lng=CREATIVE_HALL[1],
            how="창의관 앞 집결 → 버스 이동 → 전시 1시간 → 카페 수다",
        ),
        Meetup(
            activity_id=activities[2].activity_id, host_id=users[2].user_id,
            name="버스킹 구경반", meet_at=at(3, 16, 45), capacity=10,
            place_name="KAIST 도서관 앞", lat=LIBRARY[0], lng=LIBRARY[1],
            how="돗자리 펴고 구경, 신청곡 받아요",
        ),
        Meetup(
            activity_id=activities[4].activity_id, host_id=users[3].user_id,
            name="아침 오리연못 런", meet_at=at(2, 7, 0), capacity=5,
            place_name="어은동 입구", lat=EOEUN[0], lng=EOEUN[1],
            how="어은동 집결 → 오리연못 3바퀴 → 학식 아침",
        ),
    ]
    db.add_all(meetups)
    db.flush()

    db.add_all(
        [
            Participant(meetup_id=meetups[0].meetup_id, user_id=users[0].user_id),
            Participant(meetup_id=meetups[0].meetup_id, user_id=users[2].user_id),
            Participant(meetup_id=meetups[0].meetup_id, user_id=users[4].user_id),
            Participant(meetup_id=meetups[1].meetup_id, user_id=users[1].user_id),
            Participant(meetup_id=meetups[1].meetup_id, user_id=users[3].user_id),
            Participant(meetup_id=meetups[2].meetup_id, user_id=users[2].user_id),
            Participant(meetup_id=meetups[3].meetup_id, user_id=users[3].user_id),
        ]
    )
    db.flush()
    db.add_all(
        [
            Message(meetup_id=meetups[0].meetup_id, user_id=users[0].user_id, body="정문 시계탑 앞에서 봬요!"),
            Message(meetup_id=meetups[0].meetup_id, user_id=users[2].user_id, body="튀소 제가 쏩니다 🥖"),
            Message(meetup_id=meetups[1].meetup_id, user_id=users[1].user_id, body="버스 1시 40분 차 타요"),
        ]
    )
    db.commit()
