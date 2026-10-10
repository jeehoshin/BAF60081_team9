from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)
    gender: str | None = None
    age_group: str | None = None
    preferred_types: str | None = None
    preferred_regions: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    nickname: str
    gender: str | None = None
    age_group: str | None = None
    preferred_types: str | None = None
    preferred_regions: str | None = None
    created_at: datetime


class ActivityCreate(BaseModel):
    activity_type: str
    title: str
    place: str | None = None
    region: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cost: str | None = None
    description: str | None = None
    source: str = "user"
    source_url: str | None = None
    image_url: str | None = None
    lat: float | None = None
    lng: float | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: int
    activity_type: str
    title: str
    place: str | None = None
    region: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cost: str | None = None
    description: str | None = None
    source: str
    external_id: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    created_at: datetime


class MeetupCreate(BaseModel):
    activity_id: int
    host_id: int
    name: str
    meet_at: datetime | None = None
    capacity: int = 4
    place_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    how: str | None = None
    gender_filter: str | None = None
    age_filter: str | None = None


class MeetupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meetup_id: int
    activity_id: int
    host_id: int
    name: str
    meet_at: datetime | None = None
    capacity: int
    place_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    how: str | None = None
    gender_filter: str | None = None
    age_filter: str | None = None
    created_at: datetime
    participant_count: int = 0


class ParticipantCreate(BaseModel):
    user_id: int
    vote: str | None = None


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meetup_id: int
    user_id: int
    joined_at: datetime
    vote: str | None = None
    nickname: str | None = None
    age_group: str | None = None


class LikeCreate(BaseModel):
    user_id: int


class MessageCreate(BaseModel):
    user_id: int
    body: str = Field(min_length=1, max_length=280)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    meetup_id: int
    user_id: int
    body: str
    created_at: datetime
    nickname: str | None = None


class ActivityDetailOut(BaseModel):
    activity: ActivityOut
    meetups: list[MeetupOut]
    like_count: int = 0


class StatsBucket(BaseModel):
    key: str
    count: int
