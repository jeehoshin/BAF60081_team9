-- Supabase SQL Editor에서 실행

create table if not exists users (
  user_id serial primary key,
  nickname varchar(64) not null,
  gender varchar(16),
  age_group varchar(32),
  preferred_types varchar(128),
  preferred_regions varchar(128),
  created_at timestamp default now()
);

create table if not exists activities (
  activity_id serial primary key,
  activity_type varchar(32) not null,
  title varchar(255) not null,
  place varchar(255),
  region varchar(64),
  starts_at timestamp,
  ends_at timestamp,              -- 기간이 있는 공연·축제의 마지막 날
  cost varchar(64),
  description text,
  source varchar(32) default 'user',  -- user / API / KOPIS / 한국관광공사
  external_id varchar(64),        -- 공공 API 원본 ID ('KOPIS:PF302715', 'TOUR:2786391')
  source_url varchar(512),        -- 원본 페이지
  image_url varchar(512),         -- 포스터·대표 이미지
  lat double precision,
  lng double precision,
  created_at timestamp default now()
);

create table if not exists meetups (
  meetup_id serial primary key,
  activity_id int not null references activities(activity_id),
  host_id int not null references users(user_id),
  name varchar(128) not null,
  meet_at timestamp,
  capacity int default 4,
  place_name varchar(255),
  lat double precision,
  lng double precision,
  how text,
  gender_filter varchar(16),
  age_filter varchar(32),
  created_at timestamp default now()
);

create table if not exists participants (
  id serial primary key,
  meetup_id int not null references meetups(meetup_id),
  user_id int not null references users(user_id),
  joined_at timestamp default now(),
  vote varchar(16),
  unique (meetup_id, user_id)
);

create table if not exists likes (
  id serial primary key,
  user_id int not null references users(user_id),
  activity_id int not null references activities(activity_id),
  created_at timestamp default now(),
  unique (user_id, activity_id)
);

-- 모임 안 짧은 메시지 (발표 중 상호 소통)
create table if not exists messages (
  message_id serial primary key,
  meetup_id int not null references meetups(meetup_id),
  user_id int not null references users(user_id),
  body varchar(280) not null,
  created_at timestamp default now()
);

create index if not exists idx_messages_meetup_created
  on messages (meetup_id, created_at);

-- 이미 테이블을 만든 경우: 지도·모임 방식 컬럼 추가
alter table activities add column if not exists lat double precision;
alter table activities add column if not exists lng double precision;
alter table meetups add column if not exists place_name varchar(255);
alter table meetups add column if not exists lat double precision;
alter table meetups add column if not exists lng double precision;
alter table meetups add column if not exists how text;

-- 공공 API 수집(KOPIS·TourAPI)용 칸 (2026-10)
-- 백엔드가 시작할 때 없으면 자동으로 추가하지만, SQL Editor에서 직접 돌려도 된다.
alter table activities add column if not exists ends_at timestamp;
alter table activities add column if not exists external_id varchar(64);
alter table activities add column if not exists source_url varchar(512);
alter table activities add column if not exists image_url varchar(512);
create unique index if not exists uq_activities_external_id on activities (external_id);

-- KOPIS 공연 통계 (분석 전용, 2026-10). 백엔드가 시작할 때 없으면 자동으로 만든다.
-- kind: area(시·도별, level = 시도/권역/합계) / genre(장르별) / day(일별). 한 달 단위로 저장.
create table if not exists kopis_stats (
  id serial primary key,
  kind varchar(16) not null,
  period_from date not null,
  period_to date not null,
  label varchar(64) not null,
  level varchar(16),
  open_count integer,          -- 개막 편수 (prfprocnt)
  show_count integer,          -- 공연 건수 (prfcnt)
  performance_count integer,   -- 상연 횟수 (prfdtcnt)
  amount bigint,               -- 티켓 판매액(원)
  tickets integer,             -- 예매 수 (취소 포함)
  cancels integer,             -- 취소 수
  audience integer,            -- 순 관객 수 (장르별은 KOPIS nmrs 원본)
  seats integer,               -- 좌석 수 (지역별만)
  amount_share double precision,    -- 판매액 비중 % (장르별만)
  audience_share double precision,  -- 관객 비중 % (장르별만)
  collected_at timestamp default now(),
  constraint uq_kopis_stats_row unique (kind, period_from, period_to, label)
);

-- 수집 실행 기록 (기획 3-6, 2026-10). POST /collect, POST /collect/kopis-stats, scripts/ 가 돌 때마다 한 줄.
-- 백엔드가 시작할 때 없으면 자동으로 만든다. 분석 페이지 '데이터 품질'의 "마지막 수집" 근거.
create table if not exists collect_runs (
  id serial primary key,
  kind varchar(16) not null,            -- activities / kopis_stats
  trigger varchar(16) default 'api',    -- api(Swagger) / cli(scripts/)
  dry_run boolean default false,
  started_at timestamp not null default now(),
  finished_at timestamp,
  window_from date,                     -- 수집 대상 기간
  window_to date,
  collected integer default 0,          -- 받아서 저장 대상으로 남은 건수
  inserted integer default 0,
  updated integer default 0,
  unchanged integer default 0,
  skipped integer default 0,            -- 기간 밖·장기 행사·구 불명 등으로 뺀 건수 합
  error_count integer default 0,        -- 출처·지역 단위 오류 수
  ok boolean default true,
  details text                          -- 옵션 + 출처·지역별 결과 (JSON 문자열)
);
