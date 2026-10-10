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
  cost varchar(64),
  description text,
  source varchar(32) default 'user',
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
