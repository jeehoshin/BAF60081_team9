from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, Meetup, Participant, User
from app.schemas import StatsBucket

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/activities")
def activity_stats(db: Session = Depends(get_db)):
    by_region = (
        db.query(Activity.region, func.count(Activity.activity_id))
        .group_by(Activity.region)
        .all()
    )
    by_type = (
        db.query(Activity.activity_type, func.count(Activity.activity_id))
        .group_by(Activity.activity_type)
        .all()
    )
    by_source = (
        db.query(Activity.source, func.count(Activity.activity_id))
        .group_by(Activity.source)
        .all()
    )
    return {
        "total": db.query(Activity).count(),
        "by_region": [StatsBucket(key=k or "미상", count=c) for k, c in by_region],
        "by_type": [StatsBucket(key=k or "미상", count=c) for k, c in by_type],
        "by_source": [StatsBucket(key=k or "미상", count=c) for k, c in by_source],
    }


@router.get("/meetups")
def meetup_stats(db: Session = Depends(get_db)):
    meetup_count = db.query(Meetup).count()
    participant_count = db.query(Participant).count()
    capacities = db.query(Meetup.capacity).all()
    total_capacity = sum(c[0] for c in capacities) or 0
    fill_rate = round(participant_count / total_capacity * 100, 1) if total_capacity else 0.0
    return {
        "open_meetups": meetup_count,
        "participants": participant_count,
        "avg_fill_rate_percent": fill_rate,
    }


@router.get("/users")
def user_stats(db: Session = Depends(get_db)):
    by_age = db.query(User.age_group, func.count(User.user_id)).group_by(User.age_group).all()
    by_gender = db.query(User.gender, func.count(User.user_id)).group_by(User.gender).all()
    return {
        "total": db.query(User).count(),
        "by_age_group": [StatsBucket(key=k or "미상", count=c) for k, c in by_age],
        "by_gender": [StatsBucket(key=k or "미상", count=c) for k, c in by_gender],
    }
