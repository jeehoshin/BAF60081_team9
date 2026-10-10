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
