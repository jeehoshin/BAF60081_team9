from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Message, Participant, User

router = APIRouter(prefix="/live", tags=["live"])


@router.get("")
def live_board(limit: int = 20, db: Session = Depends(get_db)):
    """발표 화면용 실시간 보드. 프론트가 3초마다 폴링한다."""
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

    def count_participants(meetup_id: int) -> int:
        return db.query(Participant).filter(Participant.meetup_id == meetup_id).count()

    return {
        "counts": {
            "users": db.query(User).count(),
            "activities": db.query(Activity).count(),
            "meetups": db.query(Meetup).count(),
            "participants": db.query(Participant).count(),
            "messages": db.query(Message).count(),
        },
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
                "participant_count": count_participants(m.meetup_id),
                "capacity": m.capacity,
            }
            for m, a, host in open_meetups
        ],
    }
