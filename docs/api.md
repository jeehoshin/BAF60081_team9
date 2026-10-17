# API 설명 문서 (초안)

Base URL 예시: `https://YOUR_SERVICE.onrender.com`  
Swagger UI: `{BASE}/docs`

## POST /users

QR 이용자 등록. `gender`는 `남`·`여`, `age_group`은 `20대`·`30대`·`40대`·`50대 이상`만 받는다(그 외 `422`). 빈 값이나 `선택 안 함`은 `null`로 저장. 같은 닉네임(대소문자·앞뒤 공백 무시)은 `409`.

**입력**

```json
{
  "nickname": "민수",
  "gender": "남",
  "age_group": "20대",
  "preferred_types": "공연,축제",
  "preferred_regions": "마포구"
}
```

**응답** `201` — `user_id`, `nickname`, …

## GET /users/{user_id} · PATCH /users/{user_id}

내 정보 조회·수정. 합류 화면(`register.html`)에서 이미 합류한 사람이 연령대·성별을 나중에 채울 때 쓴다.
같은 `user_id`를 유지하므로 참여한 모임·메시지는 그대로 남는다.

**PATCH 입력** — 보낸 칸만 바뀐다. 빈 문자열·`"선택 안 함"`은 지움(`null`)으로 저장. `nickname`은 비울 수 없다 (`400`).

```json
{ "gender": "여", "age_group": "30대" }
```

**응답** `200` — `POST /users`와 같은 모양. 없는 이용자면 `404`.

## GET /activities

활동 목록. 쿼리: `region`, `city`, `type`, `date_from`, `date_to`, `limit`(기본 1000, 최대 2000), `offset`(기본 0).

- `city`(`서울`/`대전`): 그 도시의 구만. `region=중구`처럼 두 도시에 다 있는 구를 가를 때 같이 보낸다 (좌표가 있으면 위도로, 없으면 구 이름만 믿음). 다른 값은 `422`
- 날짜 조건은 **기간 겹침**으로 거른다 (공연·축제는 `starts_at`~`ends_at` 기간이 범위와 하루라도 겹치면 나옴)
- 정렬: 지금 볼 수 있거나 곧 시작하는 것 먼저, 이미 끝난 것은 맨 뒤
- 응답에 `ends_at`, `external_id`, `source_url`, `image_url`이 추가됐다 (사용자 활동은 대부분 `null`)
- `source`: `user` · `API`(시드) · `KOPIS` · `한국관광공사`

## POST /collect

공공 API(KOPIS 공연, 한국관광공사 TourAPI 축제·공연·행사, 한국문화정보원 전시)에서 서울·대전 행사를 받아 저장한다.
헤더 `x-collect-token`에 Render 환경변수 `COLLECT_TOKEN` 값을 넣어야 실행된다. 자세한 건 [COLLECT.md](COLLECT.md).

| 쿼리 | 기본값 | 설명 |
|------|--------|------|
| `sources` | `kopis,tour,culture` | 받을 출처 (KOPIS 공연 · 한국관광공사 축제·행사 · 한국문화정보원 전시) |
| `areas` | `서울,대전` | 받을 지역 |
| `days` | `30` | 오늘부터 며칠 뒤까지 (1~60) |
| `kopis_per_genre` | `6` | KOPIS 장르(9개)마다 지역별 최대 건수 |
| `max_span_days` | `90` | 이보다 긴 장기·상설 행사 제외 (0 = 제한 없음) |
| `dry_run` | `false` | `true`면 저장하지 않고 결과만 |

**응답** `200` — `collected`, `inserted`, `updated`, `unchanged`, 출처·지역별 `results`(받은 수, 뺀 이유, 오류), `sample`

- `401` 토큰 불일치 · `503` `COLLECT_TOKEN` 미설정 · `422` 잘못된 옵션

## GET /activities/{activity_id}

활동 상세 + 모임 목록 + 좋아요 수.

## POST /activities

사용자 활동 등록. 유형은 `러닝`만 가능하고(그 외 `400`), `source`는 보내도 무시하고 항상 `user`로 저장한다.

## POST /meetups

모임 개설. 호스트는 자동 참여. 정원(`capacity`)은 4~20명(기본 4명), 성별(`gender_filter`)·연령대(`age_filter`) 조건 설정 가능. 이름은 1~128자, 이미 지난 `meet_at`은 `400`(5분 여유).

```json
{
  "activity_id": 1,
  "host_id": 1,
  "name": "같이 가요",
  "meet_at": "2026-10-12T18:30:00",
  "capacity": 4,
  "gender_filter": "여",
  "age_filter": "30대"
}
```

## PATCH /meetups/{meetup_id}

모임 정보 수정 (호스트 전용). `host_id`가 모임 개설자와 일치해야 수정된다 (`403` 호스트 불일치). 조건을 바꿀 때 호스트나 현재 참여자 중 새 조건에 맞지 않는 사람이 있으면 `400`. `meet_at`은 값이 바뀔 때만 지난 시각인지 검사한다.

```json
{
  "host_id": 1,
  "name": "정문 시계탑 집결 후 같이 관람",
  "meet_at": "2026-10-12T18:00:00",
  "capacity": 6,
  "place_name": "정문 시계탑 앞",
  "how": "입구 집결 → 관람 → 저녁",
  "gender_filter": null,
  "age_filter": "20대"
}
```

## DELETE /meetups/{meetup_id}/participants/{user_id}

모임 나가기. 호스트는 나갈 수 없다(`400`). 참여하지 않은 이용자·없는 모임은 `404`.

**응답** `200` — `{"ok": true, "meetup_id": 3, "user_id": 2, "participant_count": 3}`

## POST /meetups/{meetup_id}/participants

모임 참여. 성별·연령대 조건이 있는 모임은 이용자의 성별·연령대가 입력되어 있고 조건과 일치해야 참여 가능.

```json
{ "user_id": 2 }
```

## POST /activities/{activity_id}/likes

좋아요 (선택 기능).

```json
{ "user_id": 2 }
```

## GET /stats/activities | /stats/meetups | /stats/users

분석 페이지용 집계.

- `/stats/meetups`, `/stats/users`는 쿼리 `since`(한국 시간, 예 `2026-10-21T00:00:00`)를 받는다. 발표 때 분석 페이지의 **"오늘 QR 참여자만"** 버튼이 오늘 0시를 넣어 부른다.
  - users: 그 이후 등록한 이용자만 (`total`, `by_age_group`, `by_gender`)
  - meetups: 그 이후 만든 모임 수(`open_meetups`), 그 이후 참여 건수(`participants`), 충원율은 그 기간에 만든 모임의 정원 대비
  - 응답 `since`에 적용된 값이 다시 들어 있다 (안 주면 `null`)

## GET /stats/regions

지표 G. **구별 인구 10만 명당 활동 수**로 서울·대전을 비교한다. 활동은 수집된 공연·축제·전시와 사용자 러닝을 모두 센다.

| 쿼리 | 기본값 | 설명 |
|------|--------|------|
| `include_ended` | `true` | `false`면 오늘 기준 끝난 행사는 빼고 센다 |

| 응답 칸 | 내용 |
|---------|------|
| `cities[]` | 도시마다 `population`, `activities`(활동 수), `per_100k`, 구 목록 `districts[]`(`key`, `count`, `population`, `per_100k`; 10만 명당 큰 순), 활동이 있는 구 수, 가장 많은 구 `top_district`, 상위 3개 구 집중도 `top3_share`(%) |
| `highlights` | 서울·대전 10만 명당 값과 그 비율(`seoul_vs_daejeon_ratio`), 도시별 활동 수 |
| `counted`, `unknown_region` | 센 활동 수와 구를 몰라서 뺀 수 |
| `population_basis` | 인구 출처·기준월. 구별 인구는 `backend/app/population.py`의 `DISTRICTS` |

두 도시에 다 있는 **'중구'**는 위도(서울 ≥ 37.3, 대전 ≤ 37.0)로 가르고, 좌표가 없으면 장소·설명 글자에 '대전'/'서울'이 있는지로 정한다. 그래도 모르면 뺀다.

## GET /stats/collect-runs

수집 실행 기록 (기획 3-6). `POST /collect`, `POST /collect/kopis-stats`, `scripts/` 실행마다 `collect_runs`에 한 줄씩 쌓인다 (`dry_run`도 기록).

| 응답 칸 | 내용 |
|---------|------|
| `total` | 기록 수 |
| `last_activities`, `last_kopis_stats` | 종류별 **마지막 실제 저장** 실행 (`dry_run` 제외). 없으면 `null` |
| `recent[]` | 최근 실행(기본 20, `limit`로 조절). 각 줄: `kind`(`activities`/`kopis_stats`), `trigger`(`api`=Swagger / `cli`=스크립트), `dry_run`, `started_at`, `seconds`, `window`, `collected`(남긴 건수), `inserted`, `updated`, `unchanged`, `skipped`(뺀 건수 합), `error_count`, `ok`, `results`(출처·지역별 받은 수·뺀 이유별 수·오류) |

같은 내용이 `GET /stats/quality` 응답의 `collect_runs`(최근 10건)에도 들어 있다.

## GET /stats/kopis

KOPIS 공연 통계(전국) 집계. 분석 페이지 지표 A(시·도별), B(장르별), C(요일별)에 쓴다. 저장된 달을 모두 합쳐 계산한다.

| 응답 칸 | 내용 |
|---------|------|
| `available` | 통계가 저장돼 있으면 `true`. 없으면 `false`와 `message` |
| `period` | 집계 기간 (`from`, `to`) |
| `by_area` | 시·도별 판매액·상연 횟수·순 관객 수와 비중(%). 권역 소계·합계 줄은 빼고, 비중은 합계 줄로 나눈 값. 판매액 큰 순 |
| `by_genre` | 장르별 판매액·상연 횟수와 각각의 비중(%) |
| `by_weekday` | 월~일, 요일별 하루 평균 상연 횟수·순 관객 수·판매액 |
| `highlights` | 서울·대전 판매액 비중, 서울·대전 상연 횟수 비중, 주말(토·일) 관객 비중, 서울·대전·전국의 인구 10만 명당 판매액·상연 횟수·관객 수 |
| `by_area[].population`, `*_per_100k` | 시·도 주민등록 인구와 인구 10만 명당 판매액(`amount_per_100k`)·상연 횟수·관객 수. 권역 소계처럼 인구가 없는 줄은 `null` |
| `population_basis` | 인구 출처(행정안전부 주민등록 인구통계)와 기준월(`2026-09`) |
| `notice`, `attribution` | KOPIS 집계 안내 문구와 출처. 화면에 그대로 표시 |

## GET /stats/quality

데이터 품질 지표. 분석 페이지 '데이터 품질' 표와 발표용.

| 응답 칸 | 내용 |
|---------|------|
| `total`, `by_source[]` | 건수, 이미지·좌표·장소가 빈 건수와 비율(%), 오늘 기준 `status`(진행 중 `ongoing` · 예정 `upcoming` · 종료 `ended` · 날짜 없음 `unknown`) 건수와 비율 |
| `cross_source_duplicates` | 서로 다른 공공 API 출처 사이의 중복 후보 수(`count`), 공공 자료 전체(`public_total`) 대비 비율, 판단 기준(`rule`), 후보 짝 목록(`pairs`, 최대 30) |
| `legacy_sources`, `notes` | 공공 API·사용자 등록이 아닌 출처(예전 시드 `API` 등). 정리 대상 |
| `collect_runs` | 수집 기록 요약 (`GET /stats/collect-runs`와 같은 모양, 최근 10건) |

중복 판단 기준: 제목에서 `[지역]`·`(회차)` 괄호, 연도, '제N회', 공백·기호를 지운 뒤 같거나 한쪽이 다른 쪽을 포함(4글자 이상) + 기간이 하루라도 겹침 + 같은 구.

## POST /collect/kopis-stats

KOPIS 통계 API(시·도별 `prfstsArea`, 장르별 `prfstsCate`, 일별 `prfstsTotal`)에서 지난달부터 거꾸로 `months`개월(기본 3, 이번 달 제외)을 받아 `kopis_stats`에 저장한다. 같은 달을 다시 받으면 그 달 행을 새로 바꾼다. `POST /collect`와 같은 `x-collect-token`이 필요하다.

| 쿼리 | 기본값 | 설명 |
|------|--------|------|
| `months` | `3` | 몇 달 (1~12) |
| `dry_run` | `false` | `true`면 저장하지 않고 결과만 |

**응답** `200` — `period`, `collected`(받은 줄), `saved`, 종류·달별 `results`(받은 줄, 오류), `check.seoul_amount_share_percent`

- `401` 토큰 불일치 · `503` `COLLECT_TOKEN` 또는 `KOPIS_API_KEY` 미설정

## GET /live

발표용 라이브 보드. 최근 등록·참여·메시지·열린 모임(`meetup_id`, `activity_id` 포함) + 카운트.

## GET/POST /meetups/{meetup_id}/messages

모임 채팅. 참여한 이용자만 POST 가능.

```json
{ "user_id": 2, "body": "6시 정문에서 만나요!" }
```

## GET /meetups/{meetup_id}/participants

참여자 목록 (`nickname`, `age_group`, `gender` 포함).
