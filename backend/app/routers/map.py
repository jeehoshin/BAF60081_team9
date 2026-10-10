from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Message, Participant, User

router = APIRouter(tags=["map"])


def _meetup_cards(db: Session, meetups: list[Meetup]) -> list[dict]:
    if not meetups:
        return []
    ids = [m.meetup_id for m in meetups]

    people: dict[int, list[str]] = {i: [] for i in ids}
    for meetup_id, nickname in (
        db.query(Participant.meetup_id, User.nickname)
        .join(User, User.user_id == Participant.user_id)
        .filter(Participant.meetup_id.in_(ids))
        .order_by(Participant.joined_at.asc())
        .all()
    ):
        people[meetup_id].append(nickname)

    msg_counts = dict(
        db.query(Message.meetup_id, func.count(Message.message_id))
        .filter(Message.meetup_id.in_(ids))
        .group_by(Message.meetup_id)
        .all()
    )

    cards = []
    for m in meetups:
        a: Activity = m.activity
        host: User = m.host
        lat = m.lat if m.lat is not None else a.lat
        lng = m.lng if m.lng is not None else a.lng
        cards.append(
            {
                "meetup_id": m.meetup_id,
                "name": m.name,
                "who": {
                    "host": host.nickname if host else None,
                    "host_id": m.host_id,
                    "members": people[m.meetup_id],
                    "count": len(people[m.meetup_id]),
                    "capacity": m.capacity,
                },
                "when": m.meet_at or a.starts_at,
                "where": {
                    "place_name": m.place_name or a.place,
                    "region": a.region,
                    "lat": lat,
                    "lng": lng,
                },
                "how": m.how,
                "activity": {
                    "activity_id": a.activity_id,
                    "title": a.title,
                    "type": a.activity_type,
                    "cost": a.cost,
                    "starts_at": a.starts_at,
                },
                "message_count": msg_counts.get(m.meetup_id, 0),
            }
        )
    return cards


@router.get("/map/meetups")
def map_meetups(type: str | None = None, db: Session = Depends(get_db)):
    """지도·타임라인용: 누가 / 언제 / 어디서 / 어떻게."""
    q = db.query(Meetup).join(Activity, Activity.activity_id == Meetup.activity_id)
    if type:
        q = q.filter(Activity.activity_type == type)
    meetups = q.order_by(Meetup.meet_at.asc().nullslast()).limit(200).all()
    return _meetup_cards(db, meetups)


@router.get("/users/{user_id}/meetups")
def my_meetups(user_id: int, db: Session = Depends(get_db)):
    """내가 참여한 모임톡 목록."""
    meetups = (
        db.query(Meetup)
        .join(Participant, Participant.meetup_id == Meetup.meetup_id)
        .filter(Participant.user_id == user_id)
        .order_by(Meetup.meet_at.asc().nullslast())
        .all()
    )
    cards = _meetup_cards(db, meetups)
    last_by_meetup = {}
    if meetups:
        for msg, nickname in (
            db.query(Message, User.nickname)
            .join(User, User.user_id == Message.user_id)
            .filter(Message.meetup_id.in_([m.meetup_id for m in meetups]))
            .order_by(Message.created_at.desc())
            .all()
        ):
            last_by_meetup.setdefault(
                msg.meetup_id, {"nickname": nickname, "body": msg.body, "created_at": msg.created_at}
            )
    for c in cards:
        c["last_message"] = last_by_meetup.get(c["meetup_id"])
    return cards


@router.get("/meetups/{meetup_id}/card")
def meetup_card(meetup_id: int, db: Session = Depends(get_db)):
    m = db.get(Meetup, meetup_id)
    if not m:
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    return _meetup_cards(db, [m])[0]
