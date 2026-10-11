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
| kopis_stats | id (+ unique kind, period_from, period_to, label) | — | kind, label, level, amount, performance_count, audience | KOPIS 통계 수집 (`POST /collect/kopis-stats`) |

## activities의 공공 API 칸

| 칸 | 내용 |
|----|------|
| `ends_at` | 기간이 있는 공연·축제의 마지막 날 (시작은 00:00, 끝은 23:59:59로 저장) |
| `external_id` | 원본 ID. `KOPIS:PF302715`, `TOUR:2786391`. 다시 수집할 때 같은 행을 고쳐 쓰는 기준 (사용자 활동은 NULL) |
| `source_url` | 원본 페이지 링크 (KOPIS) |
| `image_url` | 포스터·대표 이미지 |
| `source` | `user` / `API`(시드) / `KOPIS` / `한국관광공사` / `한국문화정보원` |

기존 Supabase 테이블에 이 칸이 없으면 백엔드가 시작할 때 자동으로 추가한다 (`database.ensure_schema`).

## kopis_stats (KOPIS 공연 통계, 분석 전용)

전국 단위 집계라 다른 테이블과 연결하지 않는다. 한 달 단위로 받아 (종류, 기간, 이름)마다 한 행.

| 칸 | 내용 |
|----|------|
| `kind` | `area`(시·도별) / `genre`(장르별) / `day`(일별) |
| `period_from`, `period_to` | 집계 달의 1일과 말일 |
| `label` | 시·도 이름 / 장르 / `YYYY-MM-DD` |
| `level` | `area`만: `시도` / `권역`(경기/인천 등 소계) / `합계`. 비중은 `시도` 줄을 `합계` 줄로 나눈다 |
| `open_count`, `show_count`, `performance_count` | 개막 편수, 공연 건수, 상연 횟수 |
| `amount` | 티켓 판매액(원) |
| `tickets`, `cancels`, `audience` | 예매 수(취소 포함), 취소 수, 순 관객 수. KOPIS 항목 이름이 API마다 달라서(지역별 `nmrs`=예매, 일별 `nmrs`=순 관객) 여기서 뜻을 맞춘다. 장르별은 `audience`에 KOPIS `nmrs` 원본 |
| `seats` | 좌석 수 (`area`만) |
| `amount_share`, `audience_share` | KOPIS가 계산해 주는 비중 % (`genre`만) |

## 관계

- users ↔ meetups : 다대다 → participants
- users ↔ activities : 다대다 → likes (선택)
- meetups → activities : 다대일
- meetups → messages : 일대다 (참여 후에만 작성)
