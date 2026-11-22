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
| collect_runs | id | — | kind, trigger, dry_run, started_at, window_*, collected, inserted, updated, skipped, error_count, details | 수집 실행 기록 (`POST /collect`, `POST /collect/kopis-stats`, `scripts/`) |

## activities의 공공 API 칸

| 칸 | 내용 |
|----|------|
| `ends_at` | 기간이 있는 공연·축제의 마지막 날 (시작은 00:00, 끝은 23:59:59로 저장) |
| `external_id` | 원본 ID. `KOPIS:PF302715`, `TOUR:2786391`. 다시 수집할 때 같은 행을 고쳐 쓰는 기준 (사용자 활동은 NULL) |
| `source_url` | 원본 페이지 링크 (KOPIS) |
| `image_url` | 포스터·대표 이미지 |
| `source` | `user` / `API`(시드) / `KOPIS` / `한국관광공사` / `한국문화정보원` |

기존 Supabase 테이블에 이 칸이 없으면 백엔드가 시작할 때 자동으로 추가한다 (`database.ensure_schema`).

## activities의 상세 설명·관람 조건 칸 (2026-11)

RAG·텍스트 분석과 "아이랑", "짧은 공연" 같은 조건 검색에 쓴다. 모두 비워 둘 수 있다.

| 칸 | 내용 | 어디서 |
|----|------|--------|
| `detail_text` | 줄거리·개요·전시 설명. 태그를 뺀 글자, 최대 4,000자 | KOPIS `sty` · 한국관광공사 `overview` · 한국문화정보원 `contents1` |
| `detail_source` | 위 설명이 어느 칸에서 왔는지 (`sty` / `overview` / `contents1`). 설명이 없으면 NULL | |
| `text_hash` | `detail_text`의 sha256. 같으면 임베딩을 다시 만들 필요가 없다 | |
| `min_age_months` | 관람 가능 최소 나이(개월). 전체 관람가 0, `24개월 이상` 24, `만 7세 이상` 84, `초등학생 이상` 84. 모르면 NULL | KOPIS `prfage` |
| `runtime_min` | 러닝타임(분). `1시간 30분` 90 (괄호 속 인터미션은 뺌) | KOPIS `prfruntime` |
| `intro_images` | 소개 이미지 주소 목록 (JSON 배열). 줄거리 대신 이미지만 있는 공연이 많아, 나중에 이미지 글자 인식·이미지 임베딩에 쓸 수 있게 남긴다 | KOPIS `styurls` |
| `detail_checked_at` | 상세를 마지막으로 확인한 때. 30일 안에 확인한 행사는 다시 부르지 않는다 | |

- KOPIS는 원래 부르던 공연상세에서 함께 꺼내서 호출이 늘지 않는다.
- 한국관광공사·한국문화정보원은 상세를 따로 불러야 해서 **새 행사나 30일 넘게 확인하지 않은 행사만** 부른다 (한 번에 출처·지역마다 최대 150건, 나머지는 다음 수집으로).
- 설명이 큰 기관에 몰려 있다 (2026-11 샘플 실측: 한국관광공사 30건 중 29건이 200자 이상, KOPIS 40건 중 7건, 한국문화정보원 30건 중 5건). 그래서 검색은 조건 필터를 먼저 쓰고 설명은 보조로 쓴다.
- 매일 자동 수집 요약(GitHub Actions)과 `POST /collect` 응답의 `text_coverage`에 출처별 충족률이 남는다.

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

## collect_runs (수집 실행 기록, 기획 3-6)

수집이 돌 때마다 한 줄. 다른 테이블과 연결하지 않는다. 분석 페이지 '데이터 품질'의 "최근 수집 기록"과 `GET /stats/collect-runs`에 쓴다.

| 칸 | 내용 |
|----|------|
| `kind` | `activities`(행사 수집) / `kopis_stats`(KOPIS 통계) |
| `trigger` | `api`(Swagger) / `cli`(`scripts/`) |
| `dry_run` | 미리보기 실행이면 `true` (저장 안 함). "마지막 실제 수집"을 고를 때는 뺀다 |
| `started_at`, `finished_at` | 시작·끝 시각 (KST) |
| `window_from`, `window_to` | 수집 대상 기간 (행사: 오늘~N일, 통계: 받은 달의 처음~끝) |
| `collected` | API에서 받아 저장 대상으로 남은 건수 |
| `inserted`, `updated`, `unchanged` | 새로 넣음 / 내용이 바뀌어 고침 / 그대로 (통계는 `inserted`에 저장 행 수) |
| `skipped` | 기간 밖·장기 행사·구 불명 등으로 뺀 건수 합. 이유별 수는 `details`의 `results[].skipped` |
| `error_count`, `ok` | 출처·지역 단위 오류 수, 오류가 없으면 `ok=true` |
| `details` | 그때의 옵션과 출처·지역별 결과 전체 (JSON 문자열) |

## 관계

- users ↔ meetups : 다대다 → participants
- users ↔ activities : 다대다 → likes (선택)
- meetups → activities : 다대일
- meetups → messages : 일대다 (참여 후에만 작성)
