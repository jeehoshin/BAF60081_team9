from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Message, Participant, User

router = APIRouter(prefix="/live", tags=["live"])


@router.get("")
def live_board(limit: int = 20, db: Session = Depends(get_db)):
    """발표 화면용 실시간 보드. 프론트가 3초마다 폴링한다.

    Render(미국)와 Supabase(서울)가 멀면 쿼리 한 번마다 왕복 시간이 붙는다.
    그래서 개수 5개는 한 쿼리로, 모임별 참여자 수도 한 쿼리로 센다 (전체 6번, 예전에는 최대 19번).
    """
    limit = max(1, min(limit, 50))

    recent_users = (
        db.query(User).order_by(User.created_at.desc(), User.user_id.desc()).limit(limit).all()
    )
    recent_joins = (
        db.query(Participant, User, Meetup, Activity)
        .join(User, User.user_id == Participant.user_id)
        .join(Meetup, Meetup.meetup_id == Participant.meetup_id)
        .join(Activity, Activity.activity_id == Meetup.activity_id)
        .order_by(Participant.joined_at.desc())
        .limit(limit)
        .all()
    )
    recent_messages = (
        db.query(Message, User, Meetup)
        .join(User, User.user_id == Message.user_id)
        .join(Meetup, Meetup.meetup_id == Message.meetup_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    open_meetups = (
        db.query(Meetup, Activity, User)
        .join(Activity, Activity.activity_id == Meetup.activity_id)
        .join(User, User.user_id == Meetup.host_id)
        .order_by(Meetup.created_at.desc())
        .limit(10)
        .all()
    )

    participant_counts: dict[int, int] = {}
    if open_meetups:
        participant_counts = dict(
            db.query(Participant.meetup_id, func.count(Participant.id))
            .filter(Participant.meetup_id.in_([m.meetup_id for m, _, _ in open_meetups]))
            .group_by(Participant.meetup_id)
            .all()
        )

    def total(model, column):
        return select(func.count(column)).select_from(model).scalar_subquery()

    counts = db.execute(
        select(
            total(User, User.user_id).label("users"),
            total(Activity, Activity.activity_id).label("activities"),
            total(Meetup, Meetup.meetup_id).label("meetups"),
            total(Participant, Participant.id).label("participants"),
            total(Message, Message.message_id).label("messages"),
        )
    ).one()

    return {
        "counts": dict(counts._mapping),
        "recent_users": [
            {
                "user_id": u.user_id,
                "nickname": u.nickname,
                "age_group": u.age_group,
                "preferred_types": u.preferred_types,
                "created_at": u.created_at,
            }
            for u in recent_users
        ],
        "recent_joins": [
            {
                "meetup_id": m.meetup_id,
                "activity_id": a.activity_id,
                "nickname": u.nickname,
                "meetup_name": m.name,
                "activity_title": a.title,
                "joined_at": p.joined_at,
            }
            for p, u, m, a in recent_joins
        ],
        "recent_messages": [
            {
                "meetup_id": m.meetup_id,
                "activity_id": m.activity_id,
                "nickname": u.nickname,
                "meetup_name": m.name,
                "body": msg.body,
                "created_at": msg.created_at,
            }
            for msg, u, m in recent_messages
        ],
        "open_meetups": [
            {
                "meetup_id": m.meetup_id,
                "activity_id": a.activity_id,
                "name": m.name,
                "activity_title": a.title,
                "host": host.nickname,
                "participant_count": participant_counts.get(m.meetup_id, 0),
                "capacity": m.capacity,
            }
            for m, a, host in open_meetups
        ],
    }
