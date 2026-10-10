# 공공 API 수집 (KOPIS · 한국관광공사 TourAPI)

서울·대전의 공연·축제·전시를 공공 API에서 받아 `activities` 테이블에 넣는다.
받은 행사는 활동 목록·상세·분석(출처별 건수)에 바로 나온다.

| 출처 (`source`) | API | 받는 것 | 저장 유형 |
|---|---|---|---|
| `KOPIS` | 공연예술통합전산망 오픈API (공연목록 → 공연상세 → 공연시설상세) | 공연. 장르 9개마다 지역별 최대 6건 | 공연 |
| `한국관광공사` | 국문 관광정보 서비스_GW (KorService2) `searchFestival2` | 축제·공연·행사 | 축제 / 공연 / 전시 |

---

## 1. Render에 환경변수 넣기 (처음 한 번)

Render → 백엔드 서비스 → **Environment** → Add Environment Variable

| Key | Value |
|---|---|
| `KOPIS_API_KEY` | KOPIS에서 메일로 받은 인증키 |
| `TOUR_API_KEY` | 공공데이터포털 → 마이페이지 → 활용신청 현황 → 한국관광공사_국문 관광정보 서비스_GW → **일반 인증키 (Decoding)** |
| `COLLECT_TOKEN` | 팀만 아는 아무 문자열. 아무나 수집 버튼을 누르지 못하게 막는 비밀번호 |

저장하면 재배포된다. 키 값은 GitHub, 단톡방, `frontend/config.js`에 올리지 않는다.

## 2. Swagger에서 수집하기

1. Render 주소 뒤에 `/docs`를 붙여 연다. 지금 `frontend/config.js` 기준으로는 `https://baf60081-team9.onrender.com/docs` (서버가 잠들어 있으면 첫 화면까지 30초~1분)
2. **collect → POST /collect → Try it out**
3. `x-collect-token`에 `COLLECT_TOKEN` 값 입력
4. 처음에는 `dry_run`을 **true**로 두고 Execute → 저장하지 않고 무엇을 받는지만 본다
5. 괜찮으면 `dry_run`을 **false**로 바꿔 다시 Execute → 저장
6. 활동 화면 새로고침

결과 읽는 법

| 항목 | 뜻 |
|---|---|
| `collected` | 저장 대상 행사 수 |
| `inserted` / `updated` / `unchanged` | 새로 넣음 / 내용이 바뀌어 고침 / 그대로 |
| `results[].error` | 출처·지역별 오류. 하나가 실패해도 나머지는 저장된다 |
| `results[].skipped` | 뺀 이유별 건수 (기간 밖, 장기 행사, 구를 알 수 없음 등) |
| `sample` | 받은 행사 앞 10개 |

여러 번 눌러도 같은 행사가 두 번 생기지 않는다 (원본 ID `external_id`로 알아봄).
발표 전날 한 번 더 누르면 최신 정보로 바뀐다.

## 3. 무엇을 받고 무엇을 빼나

- 기간: 오늘부터 30일 뒤까지와 하루라도 겹치는 행사 (`days`, 최대 60)
- 지역: 주소에서 구를 뽑아 `region`에 'OO구'로 저장. 서울·대전 밖이거나 구를 알 수 없으면 뺀다
- 90일 넘는 장기·상설 행사와 KOPIS 오픈런은 뺀다 (`max_span_days`, 0이면 제한 없음)
- 날짜는 시작일 00:00 ~ 종료일 23:59:59로 저장한다. 화면에는 "10월 14일 (수) ~ 10월 17일 (토)"처럼 나온다
- 끝난 행사는 지우지 않고 목록 맨 뒤로 보낸다 (모임이 걸려 있을 수 있어서)
- TourAPI 분류: `EV01` 축제 → 축제, `EV02` 공연 → 공연, `EV03` 행사 → 제목에 '전시·특별전·展' 등이 있으면 전시, 아니면 축제
- '중구'는 서울·대전에 다 있어서 지역 필터에서 같이 나온다

## 4. 출처 표시 (필수)

- KOPIS: 설명 끝에 `출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr)`이 자동으로 붙고, 상세 화면에 KOPIS 원본 링크가 나온다
- 한국관광공사: 설명 끝에 `출처: 한국관광공사 TourAPI`. 대표 이미지는 공공누리 유형을 따르니 자르거나 고치지 않는다
- 발표 자료의 데이터 출처에도 두 API의 이름·기관·주소를 적는다
- 기획([PLANNING.md](PLANNING.md))은 KOPIS 자료 상세 화면에 집계기간, 집계대상, 연계 예매처 발권 기준 안내도 넣기로 했다. 수집기는 출처 문구만 붙이므로 안내 문구는 화면에 따로 넣어야 한다 (정확한 문구는 영선 확인)

## 5. 오류가 나면

| 메시지 | 원인 | 해결 |
|---|---|---|
| `TOUR_API_KEY가 없어서 건너뛰었어요` | Render에 키가 없음 | 1번 다시 |
| `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | 승인 직후라 아직 반영 전, 또는 키를 잘못 넣음 | 1~2시간 뒤 다시. Decoding 키 확인 |
| `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR` | TourAPI 하루 1,000건 초과 | 내일 다시 (한 번 수집에 지역당 1~3건 씀) |
| `KOPIS 오류 …` / `KOPIS 요청 실패` | KOPIS 키 오타·만료·승인 취소 | KOPIS 키는 발급 후 1년 유효, 3개월 넘게 안 쓰면 승인이 취소된다. 연장·문의는 kopis@gokams.or.kr |
| `KOPIS가 요청이 너무 잦다고 잠깐 막았어요 (Request Blocked)` | KOPIS는 1초에 10건쯤 넘게 부르면 잠깐 막는다. 수집기가 1초에 4건으로 천천히 부르고 막히면 다시 부르지만, 그래도 막힌 경우 | 1~2분 뒤 다시. 여러 사람이 동시에 수집을 누르지 않는다 |
| `401 x-collect-token …` | 토큰이 다름 | Render의 `COLLECT_TOKEN` 값 확인 |
| `503 COLLECT_TOKEN이 설정되지 않아…` | 토큰을 안 넣음 | 1번 다시 |

## 6. 로컬에서 돌리기 (개발자용)

```bash
cp .env.example .env     # KOPIS_API_KEY, TOUR_API_KEY, DATABASE_URL, USE_MEMORY=0
pip install -r backend/requirements.txt
python scripts/collect_activities.py --dry-run     # 저장 없이 확인
python scripts/collect_activities.py               # 저장
python scripts/collect_activities.py --sources kopis --areas 대전 --days 14
```

키 없이 파서·저장 로직만 확인: `cd backend && python -m unittest discover tests -v`

## 7. DB에서 바뀐 것

`activities`에 칸 4개가 생겼다. 백엔드가 시작할 때 없으면 자동으로 추가한다 (기존 데이터는 그대로).
SQL Editor에서 직접 하려면 `docs/db_schema.sql` 맨 아래를 실행한다.

| 칸 | 내용 |
|---|---|
| `ends_at` | 기간이 있는 행사의 마지막 날 |
| `external_id` | 원본 ID (`KOPIS:PF302715`, `TOUR:2786391`). 고유 인덱스 |
| `source_url` | 원본 페이지 (KOPIS만) |
| `image_url` | 포스터·대표 이미지 |

`GET /activities`의 `date_from`·`date_to`는 기간 겹침으로 거른다. 정렬은 지금 볼 수 있거나 곧 시작하는 것이 먼저, 끝난 것이 맨 뒤다.

## 참고: 실제 호출

```text
KOPIS    https://kopis.or.kr/openApi/restful/pblprfr?service=KEY&stdate=YYYYMMDD&eddate=YYYYMMDD&cpage=1&rows=18&shcate=AAAA&signgucode=11
         → pblprfr/{mt20id} (공연시간·관람료·시설ID) → prfplc/{mt10id} (주소·위경도)
TourAPI  https://apis.data.go.kr/B551011/KorService2/searchFestival2?serviceKey=KEY&MobileOS=ETC&MobileApp=gachigalae
         &_type=json&arrange=A&numOfRows=100&pageNo=1&eventStartDate=YYYYMMDD&lDongRegnCd=11
```

- 지역코드는 둘 다 서울 `11`, 대전 `30`
- TourAPI 지역 필터는 `areaCode`가 아니라 `lDongRegnCd`(법정동 시도코드)를 쓴다. 2026년 9월 법정동 체계 이관 뒤로 `areacode`가 빈 콘텐츠가 많아져 `areaCode`로 거르면 상당수가 빠진다
- 코드: `backend/app/collectors/` (kopis.py, tourapi.py, runner.py), Swagger 라우터 `backend/app/routers/collect.py`
