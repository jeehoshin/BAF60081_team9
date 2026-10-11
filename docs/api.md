# API 설명 문서 (초안)

Base URL 예시: `https://YOUR_SERVICE.onrender.com`  
Swagger UI: `{BASE}/docs`

## POST /users

QR 이용자 등록.

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

## GET /activities

활동 목록. 쿼리: `region`, `type`, `date_from`, `date_to`.

- 날짜 조건은 **기간 겹침**으로 거른다 (공연·축제는 `starts_at`~`ends_at` 기간이 범위와 하루라도 겹치면 나옴)
- 정렬: 지금 볼 수 있거나 곧 시작하는 것 먼저, 이미 끝난 것은 맨 뒤
- 응답에 `ends_at`, `external_id`, `source_url`, `image_url`이 추가됐다 (사용자 활동은 대부분 `null`)
- `source`: `user` · `API`(시드) · `KOPIS` · `한국관광공사`

## POST /collect

공공 API(KOPIS 공연, 한국관광공사 TourAPI 축제·공연·행사)에서 서울·대전 행사를 받아 저장한다.
헤더 `x-collect-token`에 Render 환경변수 `COLLECT_TOKEN` 값을 넣어야 실행된다. 자세한 건 [COLLECT.md](COLLECT.md).

| 쿼리 | 기본값 | 설명 |
|------|--------|------|
| `sources` | `kopis,tour` | 받을 출처 |
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

사용자 활동 등록 (러닝 등). `source` 기본값 `user`.

## POST /meetups

모임 개설. 호스트는 자동 참여.

```json
{
  "activity_id": 1,
  "host_id": 1,
  "name": "같이 가요",
  "meet_at": "2026-10-12T18:30:00",
  "capacity": 4
}
```

## POST /meetups/{meetup_id}/participants

모임 참여.

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

## GET /live

발표용 라이브 보드. 최근 등록·참여·메시지·열린 모임 + 카운트.

## GET/POST /meetups/{meetup_id}/messages

모임 채팅. 참여한 이용자만 POST 가능.

```json
{ "user_id": 2, "body": "6시 정문에서 만나요!" }
```

## GET /meetups/{meetup_id}/participants

참여자 목록 (nickname, age_group 포함).
