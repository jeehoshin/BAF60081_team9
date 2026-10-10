from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Like, Meetup, Participant
from app.schemas import (
    ActivityCreate,
    ActivityDetailOut,
    ActivityOut,
    LikeCreate,
    MeetupOut,
)

router = APIRouter(prefix="/activities", tags=["activities"])


def _meetup_out(db: Session, meetup: Meetup) -> MeetupOut:
    count = db.query(Participant).filter(Participant.meetup_id == meetup.meetup_id).count()
    data = MeetupOut.model_validate(meetup)
    data.participant_count = count
    return data


@router.get("", response_model=list[ActivityOut])
def list_activities(
    region: str | None = None,
    activity_type: str | None = Query(None, alias="type"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Activity)
    if region:
        q = q.filter(Activity.region == region)
    if activity_type:
        q = q.filter(Activity.activity_type == activity_type)
    if date_from:
        q = q.filter(Activity.starts_at >= date_from)
    if date_to:
        q = q.filter(Activity.starts_at <= date_to)
    return q.order_by(Activity.starts_at.asc().nullslast()).all()


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
        meetups=[_meetup_out(db, m) for m in meetups],
        like_count=like_count,
    )


@router.post("", response_model=ActivityOut, status_code=201)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    activity = Activity(**payload.model_dump())
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
