from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KST, Activity, Meetup, Message, Participant, User, now_kst
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
    return _meetup_outs(db, [meetup])[0]


def _meetup_outs(db: Session, meetups: list[Meetup]) -> list[MeetupOut]:
    """모임 목록 + 참여자 수. 모임마다 따로 세지 않고 한 번에 센다."""
    counts: dict[int, int] = {}
    if meetups:
        counts = dict(
            db.query(Participant.meetup_id, func.count(Participant.id))
            .filter(Participant.meetup_id.in_([m.meetup_id for m in meetups]))
            .group_by(Participant.meetup_id)
            .all()
        )
    outs = []
    for m in meetups:
        data = MeetupOut.model_validate(m)
        data.participant_count = counts.get(m.meetup_id, 0)
        outs.append(data)
    return outs


def _check_not_past(meet_at: datetime | None) -> None:
    """이미 지난 시각으로는 모임을 열거나 옮길 수 없다 (직전 개설을 위해 5분은 봐 준다)."""
    if meet_at is None:
        return
    if meet_at.tzinfo is not None:
        meet_at = meet_at.astimezone(KST).replace(tzinfo=None)
    if meet_at < now_kst() - timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="모임 시각이 이미 지났어요. 앞으로의 시각을 골라 주세요.")


def _lock_meetup(db: Session, meetup_id: int) -> Meetup | None:
    """모임 행을 잠그고 가져온다. 여럿이 동시에 참여해도 정원을 넘기지 않게 한 줄씩 처리한다.
    (PostgreSQL에서 동작. 로컬 SQLite는 잠금 없이 그냥 읽는다.)"""
    return db.query(Meetup).filter(Meetup.meetup_id == meetup_id).with_for_update().one_or_none()


def _unmet_members(db: Session, meetup_id: int, gender_filter: str | None, age_filter: str | None) -> list[str]:
    """새 조건에 맞지 않는 현재 참여자 닉네임."""
    rows = (
        db.query(User.nickname, User.gender, User.age_group)
        .join(Participant, Participant.user_id == User.user_id)
        .filter(Participant.meetup_id == meetup_id)
        .all()
    )
    return [
        nickname
        for nickname, gender, age_group in rows
        if (gender_filter and gender != gender_filter) or (age_filter and age_group != age_filter)
    ]


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
    return _meetup_outs(db, rows)


@router.post("", response_model=MeetupOut, status_code=201)
def create_meetup(payload: MeetupCreate, db: Session = Depends(get_db)):
    if not db.get(Activity, payload.activity_id):
        raise HTTPException(status_code=404, detail="활동을 찾을 수 없습니다.")
    host = db.get(User, payload.host_id)
    if not host:
        raise HTTPException(status_code=404, detail="호스트 이용자를 찾을 수 없습니다.")
    if payload.capacity < 4 or payload.capacity > 20:
        raise HTTPException(status_code=400, detail="정원은 4~20명 사이로 설정해 주세요.")
    _check_not_past(payload.meet_at)

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
    meetup = _lock_meetup(db, meetup_id)
    if not meetup:
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    if meetup.host_id != payload.host_id:
        raise HTTPException(status_code=403, detail="모임 호스트만 수정할 수 있습니다.")

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("host_id", None)
    # 비울 수 없는 칸에 null이 오면 바꾸지 않고 넘어간다
    for required in ("name", "capacity"):
        if required in updates and updates[required] is None:
            updates.pop(required)

    if "capacity" in updates:
        cap = updates["capacity"]
        if cap < 4 or cap > 20:
            raise HTTPException(status_code=400, detail="정원은 4~20명 사이로 설정해 주세요.")
        current = db.query(Participant).filter(Participant.meetup_id == meetup_id).count()
        if cap < current:
            raise HTTPException(status_code=400, detail=f"현재 참여 인원({current}명)보다 적게 정원을 줄일 수 없습니다.")

    # 시각은 값이 실제로 바뀔 때만 '지난 시각' 검사 (이름만 고칠 때 막히지 않게)
    if "meet_at" in updates and updates["meet_at"] != meetup.meet_at:
        _check_not_past(updates["meet_at"])

    # 조건을 바꾸면 호스트와 현재 참여자가 새 조건을 지키는지 확인한다
    new_gender = _clean_filter(updates["gender_filter"]) if "gender_filter" in updates else meetup.gender_filter
    new_age = _clean_filter(updates["age_filter"]) if "age_filter" in updates else meetup.age_filter
    if "gender_filter" in updates or "age_filter" in updates:
        host = db.get(User, meetup.host_id)
        if new_gender and (not host or host.gender != new_gender):
            raise HTTPException(status_code=400, detail="호스트도 성별 조건을 충족해야 합니다.")
        if new_age and (not host or host.age_group != new_age):
            raise HTTPException(status_code=400, detail="호스트도 연령대 조건을 충족해야 합니다.")
        unmet = _unmet_members(db, meetup_id, new_gender, new_age)
        if unmet:
            raise HTTPException(
                status_code=400,
                detail=f"현재 참여자 중 새 조건에 맞지 않는 사람이 {len(unmet)}명 있어 조건을 바꿀 수 없습니다.",
            )
        updates["gender_filter"] = new_gender
        updates["age_filter"] = new_age

    for k, v in updates.items():
        setattr(meetup, k, v)

    db.commit()
    db.refresh(meetup)
    return _meetup_out(db, meetup)


@router.post("/{meetup_id}/participants", response_model=ParticipantOut, status_code=201)
def join_meetup(meetup_id: int, payload: ParticipantCreate, db: Session = Depends(get_db)):
    # 모임 행을 잠가서, 동시에 여럿이 눌러도 한 명씩 정원을 확인한다
    meetup = _lock_meetup(db, meetup_id)
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
    try:
        db.commit()
    except IntegrityError:
        # 같은 사람이 거의 동시에 두 번 눌렀을 때: 이미 들어간 것으로 본다
        db.rollback()
        existing = (
            db.query(Participant)
            .filter(Participant.meetup_id == meetup_id, Participant.user_id == payload.user_id)
            .first()
        )
        if existing:
            return _participant_out(existing, user)
        raise
    db.refresh(row)
    return _participant_out(row, user)


@router.delete("/{meetup_id}/participants/{user_id}")
def leave_meetup(meetup_id: int, user_id: int, db: Session = Depends(get_db)):
    """모임에서 나간다. 호스트는 나갈 수 없다 (모임이 주인 없이 남지 않게)."""
    meetup = _lock_meetup(db, meetup_id)
    if not meetup:
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    row = (
        db.query(Participant)
        .filter(Participant.meetup_id == meetup_id, Participant.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="이 모임에 참여하고 있지 않아요.")
    if meetup.host_id == user_id:
        raise HTTPException(status_code=400, detail="호스트는 모임에서 나갈 수 없어요.")
    db.delete(row)
    db.commit()
    count = db.query(Participant).filter(Participant.meetup_id == meetup_id).count()
    return {"ok": True, "meetup_id": meetup_id, "user_id": user_id, "participant_count": count}


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
    """모임톡 메시지. 최근 100개를 오래된 것부터 돌려준다.

    (예전에는 '가장 오래된 100개'를 돌려줘서, 메시지가 100개를 넘으면 새 메시지가 화면에 안 보였다.)
    """
    if not db.get(Meetup, meetup_id):
        raise HTTPException(status_code=404, detail="모임을 찾을 수 없습니다.")
    rows = (
        db.query(Message, User)
        .join(User, User.user_id == Message.user_id)
        .filter(Message.meetup_id == meetup_id)
        .order_by(Message.created_at.desc(), Message.message_id.desc())
        .limit(100)
        .all()
    )
    rows.reverse()  # 화면에는 오래된 것부터 위에서 아래로
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
        # 권한 문제라 403 (발표 자료·API 문서의 '비참여자 403'과 맞춤)
        raise HTTPException(status_code=403, detail="모임에 참여한 뒤에 메시지를 보낼 수 있습니다.")

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
