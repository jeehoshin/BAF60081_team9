from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16))
    age_group: Mapped[str | None] = mapped_column(String(32))
    preferred_types: Mapped[str | None] = mapped_column(String(128))
    preferred_regions: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    hosted_meetups = relationship("Meetup", back_populates="host")
    participations = relationship("Participant", back_populates="user")
    likes = relationship("Like", back_populates="user")
    messages = relationship("Message", back_populates="user")


class Activity(Base):
    __tablename__ = "activities"

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 공연/축제/전시/러닝
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    place: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(64))  # 서울 구
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    cost: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="user")  # API / user
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    meetups = relationship("Meetup", back_populates="activity")
    likes = relationship("Like", back_populates="activity")


class Meetup(Base):
    __tablename__ = "meetups"

    meetup_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    meet_at: Mapped[datetime | None] = mapped_column(DateTime)
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    place_name: Mapped[str | None] = mapped_column(String(255))  # 집결 장소
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    how: Mapped[str | None] = mapped_column(Text)  # 진행 방식 (예: 정문 집결 → 도보 이동)
    gender_filter: Mapped[str | None] = mapped_column(String(16))
    age_filter: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    activity = relationship("Activity", back_populates="meetups")
    host = relationship("User", back_populates="hosted_meetups")
    participants = relationship("Participant", back_populates="meetup")
    messages = relationship("Message", back_populates="meetup")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("meetup_id", "user_id", name="uq_meetup_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetups.meetup_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    vote: Mapped[str | None] = mapped_column(String(16))  # approve / reject (optional)

    meetup = relationship("Meetup", back_populates="participants")
    user = relationship("User", back_populates="participations")


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "activity_id", name="uq_like_user_activity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="likes")
    activity = relationship("Activity", back_populates="likes")


class Message(Base):
    """모임 안 짧은 메시지 — 발표 중 상호 소통용."""

    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetups.meetup_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    body: Mapped[str] = mapped_column(String(280), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    meetup = relationship("Meetup", back_populates="messages")
    user = relationship("User", back_populates="messages")
