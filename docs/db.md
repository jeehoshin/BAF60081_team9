# DB 테이블 문서 (초안)

PostgreSQL (Supabase). SQL 생성 스크립트: [db_schema.sql](db_schema.sql)

| 테이블 | PK | FK | 주요 컬럼 | 채우는 방식 |
|--------|----|----|-----------|-------------|
| users | user_id | — | nickname, gender, age_group, preferred_* | QR 등록 |
| activities | activity_id (+ unique external_id) | — | type, title, place, region, starts_at, ends_at, cost, source, external_id, source_url, image_url | 공공 API 수집 (`POST /collect`) / 사용자 |
| meetups | meetup_id | activity_id, host_id | name, meet_at, capacity, filters | 모임 개설 |
| participants | id (+ unique meetup_id,user_id) | meetup_id, user_id | joined_at, vote | 참여 버튼 |
| likes | id (+ unique user_id,activity_id) | user_id, activity_id | created_at | 좋아요 (선택) |
| messages | message_id | meetup_id, user_id | body, created_at | 모임 채팅 (발표 소통) |

## activities의 공공 API 칸

| 칸 | 내용 |
|----|------|
| `ends_at` | 기간이 있는 공연·축제의 마지막 날 (시작은 00:00, 끝은 23:59:59로 저장) |
| `external_id` | 원본 ID. `KOPIS:PF302715`, `TOUR:2786391`. 다시 수집할 때 같은 행을 고쳐 쓰는 기준 (사용자 활동은 NULL) |
| `source_url` | 원본 페이지 링크 (KOPIS) |
| `image_url` | 포스터·대표 이미지 |
| `source` | `user` / `API`(시드) / `KOPIS` / `한국관광공사` |

기존 Supabase 테이블에 이 칸이 없으면 백엔드가 시작할 때 자동으로 추가한다 (`database.ensure_schema`).

## 관계

- users ↔ meetups : 다대다 → participants
- users ↔ activities : 다대다 → likes (선택)
- meetups → activities : 다대일
- meetups → messages : 일대다 (참여 후에만 작성)
