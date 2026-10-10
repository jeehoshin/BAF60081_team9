from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Message, Participant, User
from app.schemas import (
    MeetupCreate,
    MeetupOut,
    MessageCreate,
    MessageOut,
    ParticipantCreate,
    ParticipantOut,
)

router = APIRouter(prefix="/meetups", tags=["meetups"])


def _meetup_out(db: Session, meetup: Meetup) -> MeetupOut:
    count = db.query(Participant).filter(Participant.meetup_id == meetup.meetup_id).count()
    data = MeetupOut.model_validate(meetup)
    data.participant_count = count
    return data


def _participant_out(p: Participant, user: User | None = None) -> ParticipantOut:
    return ParticipantOut(
        meetup_id=p.meetup_id,
        user_id=p.user_id,
        joined_at=p.joined_at,
        vote=p.vote,
        nickname=user.nickname if user else None,
        age_group=user.age_group if user else None,
    )


@router.get("", response_model=list[MeetupOut])
def list_meetups(db: Session = Depends(get_db)):
    rows = db.query(Meetup).order_by(Meetup.created_at.desc()).limit(50).all()
    return [_meetup_out(db, m) for m in rows]


@router.post("", response_model=MeetupOut, status_code=201)
def create_meetup(payload: MeetupCreate, db: Session = Depends(get_db)):
    if not db.get(Activity, payload.activity_id):
        raise HTTPException(status_code=404, detail="활동을 찾을 수 없습니다.")
    if not db.get(User, payload.host_id):
        raise HTTPException(status_code=404, detail="호스트 이용자를 찾을 수 없습니다.")

    meetup = Meetup(**payload.model_dump())
    db.add(meetup)
    db.flush()
    db.add(Participant(meetup_id=meetup.meetup_id, user_id=payload.host_id))
    db.commit()
    db.refresh(meetup)
    return _meetup_out(db, meetup)


@router.post("/{meetup_id}/participants", response_model=ParticipantOut, status_code=201)
def join_meetup(meetup_id: int, payload: ParticipantCreate, db: Session = Depends(get_db)):
    meetup = db.get(Meetup, meetup_id)
    if not meetup:
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다.")

    current = db.query(Participant).filter(Participant.meetup_id == meetup_id).count()
    if current >= meetup.capacity:
        raise HTTPException(status_code=400, detail="정원이 가득 찼습니다.")

    existing = (
        db.query(Participant)
        .filter(Participant.meetup_id == meetup_id, Participant.user_id == payload.user_id)
        .first()
    )
    if existing:
        return _participant_out(existing, user)

    if meetup.gender_filter and user.gender and user.gender != meetup.gender_filter:
        raise HTTPException(status_code=400, detail="성별 조건에 맞지 않습니다.")
    if meetup.age_filter and user.age_group and user.age_group != meetup.age_filter:
        raise HTTPException(status_code=400, detail="연령대 조건에 맞지 않습니다.")

    row = Participant(meetup_id=meetup_id, user_id=payload.user_id, vote=payload.vote)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _participant_out(row, user)


@router.get("/{meetup_id}/participants", response_model=list[ParticipantOut])
def list_participants(meetup_id: int, db: Session = Depends(get_db)):
    if not db.get(Meetup, meetup_id):
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    rows = (
        db.query(Participant, User)
        .join(User, User.user_id == Participant.user_id)
        .filter(Participant.meetup_id == meetup_id)
        .order_by(Participant.joined_at.asc())
        .all()
    )
    return [_participant_out(p, u) for p, u in rows]


@router.get("/{meetup_id}/messages", response_model=list[MessageOut])
def list_messages(meetup_id: int, db: Session = Depends(get_db)):
    if not db.get(Meetup, meetup_id):
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    rows = (
        db.query(Message, User)
        .join(User, User.user_id == Message.user_id)
        .filter(Message.meetup_id == meetup_id)
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )
    return [
        MessageOut(
            message_id=m.message_id,
            meetup_id=m.meetup_id,
            user_id=m.user_id,
            body=m.body,
            created_at=m.created_at,
            nickname=u.nickname,
        )
        for m, u in rows
    ]


@router.post("/{meetup_id}/messages", response_model=MessageOut, status_code=201)
def post_message(meetup_id: int, payload: MessageCreate, db: Session = Depends(get_db)):
    if not db.get(Meetup, meetup_id):
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다.")

    joined = (
        db.query(Participant)
        .filter(Participant.meetup_id == meetup_id, Participant.user_id == payload.user_id)
        .first()
    )
    if not joined:
        raise HTTPException(status_code=400, detail="모임에 참여한 뒤에 메시지를 보낼 수 있습니다.")

    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="메시지 내용을 입력하세요.")

    msg = Message(meetup_id=meetup_id, user_id=payload.user_id, body=body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MessageOut(
        message_id=msg.message_id,
        meetup_id=msg.meetup_id,
        user_id=msg.user_id,
        body=msg.body,
        created_at=msg.created_at,
        nickname=user.nickname,
    )
