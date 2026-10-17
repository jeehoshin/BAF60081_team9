from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Like, Meetup, Participant, now_kst
from app.schemas import (
    ActivityCreate,
    ActivityDetailOut,
    ActivityOut,
    LikeCreate,
    MeetupOut,
)

router = APIRouter(prefix="/activities", tags=["activities"])


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


@router.get("", response_model=list[ActivityOut])
def list_activities(
    region: str | None = None,
    activity_type: str | None = Query(None, alias="type"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(1000, ge=1, le=2000, description="최대 몇 건까지 (기본 1000)"),
    offset: int = Query(0, ge=0, description="앞에서 몇 건 건너뛸지"),
    db: Session = Depends(get_db),
):
    q = db.query(Activity)
    if region:
        q = q.filter(Activity.region == region)
    if activity_type:
        q = q.filter(Activity.activity_type == activity_type)
    # 기간이 있는 공연·축제는 기간이 조회 범위와 하루라도 겹치면 보여준다
    last_day = func.coalesce(Activity.ends_at, Activity.starts_at)
    if date_from:
        q = q.filter(last_day >= date_from)
    if date_to:
        q = q.filter(Activity.starts_at <= date_to)
    # 정렬: 지금 볼 수 있거나 곧 시작하는 것 먼저, 이미 끝난 것은 맨 뒤
    now = now_kst()
    is_over = case((last_day < now, 1), else_=0)
    next_time = case((Activity.starts_at < now, now), else_=Activity.starts_at)
    return q.order_by(
        is_over.asc(),
        next_time.asc().nullslast(),
        Activity.ends_at.asc().nullslast(),
        Activity.activity_id.asc(),
    ).offset(offset).limit(limit).all()


@router.get("/{activity_id}", response_model=ActivityDetailOut)
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="활동을 찾을 수 없습니다.")
    meetups = (
        db.query(Meetup)
        .filter(Meetup.activity_id == activity_id)
        .order_by(Meetup.meet_at.asc().nullslast())
        .all()
    )
    like_count = db.query(Like).filter(Like.activity_id == activity_id).count()
    return ActivityDetailOut(
        activity=ActivityOut.model_validate(activity),
        meetups=_meetup_outs(db, meetups),
        like_count=like_count,
    )


@router.post("", response_model=ActivityOut, status_code=201)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    """이용자가 직접 올리는 활동. 러닝만 가능하고, 출처(source)는 항상 'user'로 저장한다."""
    if payload.activity_type != "러닝":
        raise HTTPException(
            status_code=400,
            detail="공연·축제·전시는 공공 API에서 자동으로 수집됩니다. 직접 등록은 '러닝'만 가능합니다.",
        )
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목을 입력해 주세요.")
    data = payload.model_dump()
    data["title"] = title
    data["source"] = "user"
    activity = Activity(**data)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.post("/{activity_id}/likes", status_code=201)
def like_activity(activity_id: int, payload: LikeCreate, db: Session = Depends(get_db)):
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="활동을 찾을 수 없습니다.")
    existing = (
        db.query(Like)
        .filter(Like.activity_id == activity_id, Like.user_id == payload.user_id)
        .first()
    )
    if existing:
        return {"ok": True, "already": True}
    db.add(Like(user_id=payload.user_id, activity_id=activity_id))
    db.commit()
    return {"ok": True, "already": False}
