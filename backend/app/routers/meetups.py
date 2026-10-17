from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Message, Participant, User
from app.schemas import (
    MeetupCreate,
    MeetupOut,
    MeetupUpdate,
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
        gender=user.gender if user else None,
    )


def _clean_filter(val: str | None) -> str | None:
    if not val or val.strip() in ("", "무관", "선택 안 함"):
        return None
    return val.strip()


@router.get("", response_model=list[MeetupOut])
def list_meetups(db: Session = Depends(get_db)):
    rows = db.query(Meetup).order_by(Meetup.created_at.desc()).limit(50).all()
    return [_meetup_out(db, m) for m in rows]


@router.post("", response_model=MeetupOut, status_code=201)
def create_meetup(payload: MeetupCreate, db: Session = Depends(get_db)):
    if not db.get(Activity, payload.activity_id):
        raise HTTPException(status_code=404, detail="활동을 찾을 수 없습니다.")
    host = db.get(User, payload.host_id)
    if not host:
        raise HTTPException(status_code=404, detail="호스트 이용자를 찾을 수 없습니다.")
    if payload.capacity < 4 or payload.capacity > 20:
        raise HTTPException(status_code=400, detail="정원은 4~20명 사이로 설정해 주세요.")

    gender_filter = _clean_filter(payload.gender_filter)
    age_filter = _clean_filter(payload.age_filter)

    if gender_filter and (not host.gender or host.gender == "선택 안 함" or host.gender != gender_filter):
        raise HTTPException(status_code=400, detail="호스트도 성별 조건을 충족해야 모임을 개설할 수 있습니다.")
    if age_filter and (not host.age_group or host.age_group == "선택 안 함" or host.age_group != age_filter):
        raise HTTPException(status_code=400, detail="호스트도 연령대 조건을 충족해야 모임을 개설할 수 있습니다.")

    data = payload.model_dump()
    data["gender_filter"] = gender_filter
    data["age_filter"] = age_filter
    meetup = Meetup(**data)
    db.add(meetup)
    db.flush()
    db.add(Participant(meetup_id=meetup.meetup_id, user_id=payload.host_id))
    db.commit()
    db.refresh(meetup)
    return _meetup_out(db, meetup)


@router.patch("/{meetup_id}", response_model=MeetupOut)
def update_meetup(meetup_id: int, payload: MeetupUpdate, db: Session = Depends(get_db)):
    meetup = db.get(Meetup, meetup_id)
    if not meetup:
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    if meetup.host_id != payload.host_id:
        raise HTTPException(status_code=403, detail="모임 호스트만 수정할 수 있습니다.")

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("host_id", None)

    if "name" in updates and updates["name"] is not None:
        name = updates["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="모임 이름을 입력해 주세요.")
        updates["name"] = name

    if "capacity" in updates and updates["capacity"] is not None:
        cap = updates["capacity"]
        if cap < 4 or cap > 20:
            raise HTTPException(status_code=400, detail="정원은 4~20명 사이로 설정해 주세요.")
        current = db.query(Participant).filter(Participant.meetup_id == meetup_id).count()
        if cap < current:
            raise HTTPException(status_code=400, detail=f"현재 참여 인원({current}명)보다 적게 정원을 줄일 수 없습니다.")

    if "gender_filter" in updates:
        updates["gender_filter"] = _clean_filter(updates["gender_filter"])
    if "age_filter" in updates:
        updates["age_filter"] = _clean_filter(updates["age_filter"])

    for k, v in updates.items():
        setattr(meetup, k, v)

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

    existing = (
        db.query(Participant)
        .filter(Participant.meetup_id == meetup_id, Participant.user_id == payload.user_id)
        .first()
    )
    if existing:
        return _participant_out(existing, user)

    current = db.query(Participant).filter(Participant.meetup_id == meetup_id).count()
    if current >= meetup.capacity:
        raise HTTPException(status_code=400, detail="정원이 가득 찼습니다.")

    if meetup.gender_filter:
        if not user.gender or user.gender == "선택 안 함":
            raise HTTPException(
                status_code=400,
                detail="참여 조건이 있는 모임이에요. 연령대·성별을 입력해 주세요.",
            )
        if user.gender != meetup.gender_filter:
            raise HTTPException(status_code=400, detail="성별 조건에 맞지 않습니다.")

    if meetup.age_filter:
        if not user.age_group or user.age_group == "선택 안 함":
            raise HTTPException(
                status_code=400,
                detail="참여 조건이 있는 모임이에요. 연령대·성별을 입력해 주세요.",
            )
        if user.age_group != meetup.age_filter:
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
