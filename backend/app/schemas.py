from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 팀 공통 선택지 (docs/PLANNING.md 5장). 화면의 '선택 안 함'은 빈 값(None)으로 저장한다.
GENDERS = ("남", "여")
AGE_GROUPS = ("20대", "30대", "40대", "50대 이상")
_EMPTY_CHOICES = ("", "선택 안 함", "무관")


def _choice_or_none(value: str | None, allowed: tuple[str, ...], label: str) -> str | None:
    """선택지 값만 통과시킨다. 비었거나 '선택 안 함'/'무관'이면 None."""
    if value is None:
        return None
    value = value.strip()
    if value in _EMPTY_CHOICES:
        return None
    if value not in allowed:
        raise ValueError(f"{label}은(는) {', '.join(allowed)} 중에서 골라 주세요.")
    return value


def _clean_text(value: str | None) -> str | None:
    """앞뒤 공백을 지우고, 비면 None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class UserCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=64)
    gender: str | None = None
    age_group: str | None = None
    preferred_types: str | None = Field(default=None, max_length=128)
    preferred_regions: str | None = Field(default=None, max_length=128)

    @field_validator("nickname")
    @classmethod
    def _nickname(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("닉네임을 입력해 주세요.")
        return v

    @field_validator("gender")
    @classmethod
    def _gender(cls, v: str | None) -> str | None:
        return _choice_or_none(v, GENDERS, "성별")

    @field_validator("age_group")
    @classmethod
    def _age_group(cls, v: str | None) -> str | None:
        return _choice_or_none(v, AGE_GROUPS, "연령대")


class UserUpdate(BaseModel):
    """내 정보 수정. 보낸 칸만 바뀐다 (빈 문자열은 '지움'으로 처리).

    합류(UserCreate)와 같은 선택지만 받는다. 예전에는 검사가 없어서 '10대'·'기타'도 저장됐다.
    """

    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    gender: str | None = None
    age_group: str | None = None
    preferred_types: str | None = Field(default=None, max_length=128)
    preferred_regions: str | None = Field(default=None, max_length=128)

    @field_validator("gender")
    @classmethod
    def _gender(cls, v: str | None) -> str | None:
        return _choice_or_none(v, GENDERS, "성별")

    @field_validator("age_group")
    @classmethod
    def _age_group(cls, v: str | None) -> str | None:
        return _choice_or_none(v, AGE_GROUPS, "연령대")


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
    """이용자가 직접 올리는 활동(러닝). source는 받지 않고 서버가 'user'로 고정한다."""

    activity_type: str
    title: str = Field(min_length=1, max_length=255)
    place: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cost: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=512)
    image_url: str | None = Field(default=None, max_length=512)
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


class _MeetupFields(BaseModel):
    """모임 만들기·수정에서 같이 쓰는 입력 검사."""

    @field_validator("name", check_fields=False)
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("모임 이름을 입력해 주세요.")
        if len(v) > 128:
            raise ValueError("모임 이름은 128자 이내로 입력해 주세요.")
        return v

    @field_validator("place_name", check_fields=False)
    @classmethod
    def _place_name(cls, v: str | None) -> str | None:
        v = _clean_text(v)
        if v is not None and len(v) > 255:
            raise ValueError("집결 장소는 255자 이내로 입력해 주세요.")
        return v

    @field_validator("how", check_fields=False)
    @classmethod
    def _how(cls, v: str | None) -> str | None:
        v = _clean_text(v)
        if v is not None and len(v) > 1000:
            raise ValueError("진행 방식은 1000자 이내로 입력해 주세요.")
        return v

    @field_validator("gender_filter", check_fields=False)
    @classmethod
    def _gender_filter(cls, v: str | None) -> str | None:
        return _choice_or_none(v, GENDERS, "성별 조건")

    @field_validator("age_filter", check_fields=False)
    @classmethod
    def _age_filter(cls, v: str | None) -> str | None:
        return _choice_or_none(v, AGE_GROUPS, "연령대 조건")


class MeetupCreate(_MeetupFields):
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


class MeetupUpdate(_MeetupFields):
    host_id: int
    name: str | None = None
    meet_at: datetime | None = None
    capacity: int | None = None
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
    gender: str | None = None


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
