# DB 테이블 문서 (초안)

PostgreSQL (Supabase). SQL 생성 스크립트: [db_schema.sql](db_schema.sql)

| 테이블 | PK | FK | 주요 컬럼 | 채우는 방식 |
|--------|----|----|-----------|-------------|
| users | user_id | — | nickname, gender, age_group, preferred_* | QR 등록 |
| activities | activity_id | — | type, title, place, region, starts_at, cost, source | API 배치 / 사용자 |
| meetups | meetup_id | activity_id, host_id | name, meet_at, capacity, filters | 모임 개설 |
| participants | id (+ unique meetup_id,user_id) | meetup_id, user_id | joined_at, vote | 참여 버튼 |
| likes | id (+ unique user_id,activity_id) | user_id, activity_id | created_at | 좋아요 (선택) |
| messages | message_id | meetup_id, user_id | body, created_at | 모임 채팅 (발표 소통) |

## 관계

- users ↔ meetups : 다대다 → participants
- users ↔ activities : 다대다 → likes (선택)
- meetups → activities : 다대일
- meetups → messages : 일대다 (참여 후에만 작성)
