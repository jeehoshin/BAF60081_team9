from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """한국 표준시 현재 시각(timezone-naive). Render 서버 기본 시간대가 UTC라 KST로 맞춘다."""
    return datetime.now(KST).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16))
    age_group: Mapped[str | None] = mapped_column(String(32))
    preferred_types: Mapped[str | None] = mapped_column(String(128))
    preferred_regions: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    hosted_meetups = relationship("Meetup", back_populates="host")
    participations = relationship("Participant", back_populates="user")
    likes = relationship("Like", back_populates="user")
    messages = relationship("Message", back_populates="user")


class Activity(Base):
    __tablename__ = "activities"
    # 공공 API 행사는 원본 ID로 한 번만 저장한다 (사용자 활동은 NULL이라 제약에 걸리지 않음)
    __table_args__ = (Index("uq_activities_external_id", "external_id", unique=True),)

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 공연/축제/전시/러닝
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    place: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(64))  # 서울·대전 구 ('OO구')
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)  # 기간이 있는 공연·축제의 마지막 날
    cost: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="user")  # user / KOPIS / 한국관광공사
    external_id: Mapped[str | None] = mapped_column(String(64))  # 'KOPIS:PF302715', 'TOUR:2786391'
    source_url: Mapped[str | None] = mapped_column(String(512))  # 원본 페이지
    image_url: Mapped[str | None] = mapped_column(String(512))  # 포스터·대표 이미지
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

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
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    vote: Mapped[str | None] = mapped_column(String(16))  # approve / reject (optional)

    meetup = relationship("Meetup", back_populates="participants")
    user = relationship("User", back_populates="participations")


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "activity_id", name="uq_like_user_activity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    user = relationship("User", back_populates="likes")
    activity = relationship("Activity", back_populates="likes")


class Message(Base):
    """모임 안 짧은 메시지 — 발표 중 상호 소통용."""

    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetups.meetup_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    body: Mapped[str] = mapped_column(String(280), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    meetup = relationship("Meetup", back_populates="messages")
    user = relationship("User", back_populates="messages")


class KopisStat(Base):
    """KOPIS 공연 통계 (전국 집계, 분석 전용). activities와 연결하지 않는다.

    kind: area(시·도별) / genre(장르별) / day(일별). 한 달 단위로 받아 (kind, 기간, label)마다 한 행.
    """

    __tablename__ = "kopis_stats"
    __table_args__ = (
        UniqueConstraint("kind", "period_from", "period_to", "label", name="uq_kopis_stats_row"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # area / genre / day
    period_from: Mapped[date] = mapped_column(Date, nullable=False)  # 집계 시작일 (그달 1일)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)  # 집계 끝날 (그달 말일)
    label: Mapped[str] = mapped_column(String(64), nullable=False)  # 시·도 이름 / 장르 / 'YYYY-MM-DD'
    level: Mapped[str | None] = mapped_column(String(16))  # area만: 시도 / 권역 / 합계
    open_count: Mapped[int | None] = mapped_column(Integer)  # 개막 편수 (prfprocnt)
    show_count: Mapped[int | None] = mapped_column(Integer)  # 공연 건수 (prfcnt, 장르별엔 없음)
    performance_count: Mapped[int | None] = mapped_column(Integer)  # 상연 횟수 (prfdtcnt)
    amount: Mapped[int | None] = mapped_column(BigInteger)  # 티켓 판매액(원)
    tickets: Mapped[int | None] = mapped_column(Integer)  # 예매 수, 취소 포함
    cancels: Mapped[int | None] = mapped_column(Integer)  # 취소 수
    audience: Mapped[int | None] = mapped_column(Integer)  # 순 관객 수 (장르별은 KOPIS nmrs 원본)
    seats: Mapped[int | None] = mapped_column(Integer)  # 좌석 수 (area만)
    amount_share: Mapped[float | None] = mapped_column(Float)  # 판매액 비중 % (genre만, KOPIS 계산값)
    audience_share: Mapped[float | None] = mapped_column(Float)  # 관객 비중 % (genre만, KOPIS 계산값)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)


class CollectRun(Base):
    """수집 실행 기록 (기획 3-6). POST /collect·/collect/kopis-stats·로컬 스크립트가 돌 때마다 한 행.

    데이터 품질 지표(분석 페이지)의 "마지막 수집이 언제였고, 출처별로 몇 건 받아 몇 건 저장·제외했나"의 근거.
    """

    __tablename__ = "collect_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # activities / kopis_stats
    trigger: Mapped[str] = mapped_column(String(16), default="api")  # api(Swagger) / cli(scripts/)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    window_from: Mapped[date | None] = mapped_column(Date)  # 수집 대상 기간 (행사: 오늘~N일 / 통계: 달)
    window_to: Mapped[date | None] = mapped_column(Date)
    collected: Mapped[int] = mapped_column(Integer, default=0)  # API에서 받아 저장 대상으로 남은 건수
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)  # 기간 밖·장기 행사·구 불명 등으로 뺀 건수 합
    error_count: Mapped[int] = mapped_column(Integer, default=0)  # 출처·지역 단위 오류 수
    ok: Mapped[bool] = mapped_column(Boolean, default=True)  # 오류가 하나도 없었는지
    details: Mapped[str | None] = mapped_column(Text)  # 옵션 + 출처·지역별 결과(JSON 문자열)
