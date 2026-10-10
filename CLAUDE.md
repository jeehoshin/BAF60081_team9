# CLAUDE.md

같이 갈래? — 클라우드컴퓨팅실습(BAF60081) 9조 시연 서비스. Claude Code가 이 저장소에서 일할 때 먼저 읽는 안내다.
사람이 읽는 설명은 README.md와 docs/에 있다.

## 프로젝트

- 공연·축제·전시·러닝 활동을 찾고 → 모임을 열거나 참여하고 → 모임 채팅으로 만나는 서비스. 발표장에서 청중이 QR로 합류하면 라이브 보드(`live.html`)와 분석(`stats.html`) 숫자가 바뀌는 걸 보여준다.
- 최종 발표: 2026-10-21(수). 그 전까지는 큰 구조 변경보다 시연이 안정적으로 도는 것이 우선이다.
- 팀 5명 중 개발자는 1명이다. 설명·문서·커밋 메시지·PR 설명은 비개발자도 읽을 수 있는 쉬운 한국어로 쓴다. git 명령을 쓸 때는 무엇을 왜 하는지 한 줄로 알려준다.
- 역할: 지호(저장소 주인 `jeehoshin`, 프론트·배포), 동주(백엔드·QR), 영선(외부 API), 연경(발표), 찬휘(기획, KOPIS·TourAPI 키 보유).

## 구조

| 위치 | 내용 | 배포 |
|---|---|---|
| `frontend/` | 빌드 없는 HTML/CSS/JS. 공통 함수는 `app.js`의 `window.Gachi` | Vercel (Root Directory = `frontend`) |
| `backend/app/` | FastAPI + SQLAlchemy. 기능별 API는 `routers/` | Render (`render.yaml`, Python 3.12.7, TZ=Asia/Seoul) |
| `backend/app/collectors/` | 공공 API 수집기 (KOPIS 공연, 한국관광공사 TourAPI 축제·행사) | `POST /collect` |
| `scripts/collect_activities.py` | 같은 수집기를 로컬에서 돌리는 CLI | — |
| `docs/` | KEYS(키 목록), COLLECT(수집), DEPLOY, api, db, `db_schema.sql` | — |

- DB는 Supabase PostgreSQL (Transaction pooler, 포트 6543). `DATABASE_URL`이 없거나 `USE_MEMORY=1`이면 메모리 SQLite로 뜨고, `activities`가 비어 있을 때만 `seed.py`의 시연용 데이터(KAIST 대전 주변)를 넣는다.
- 백엔드는 시작할 때 테이블을 만들고(`init_db`), 이미 있는 테이블에 빠진 칸을 추가한다(`database.ensure_schema`).

## 명령

```bash
# 백엔드 → http://127.0.0.1:8000/docs (Swagger)
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
USE_MEMORY=1 uvicorn app.main:app --reload --port 8000    # PowerShell: $env:USE_MEMORY="1"; uvicorn ...

# 프론트 (다른 터미널) → http://127.0.0.1:5500
cd frontend
npx --yes serve -l 5500

# 테스트 (인증키·인터넷 없이 돌아간다)
cd backend
python -m unittest discover tests -v
```

- `frontend/config.js`의 `API_BASE_URL`은 배포된 Render 주소다. 로컬에서 `http://127.0.0.1:8000`으로 바꿔 테스트해도 그 변경은 커밋하지 않는다.

## 지킬 것

- main에 바로 push하지 않는다. 브랜치를 만들고 PR로 올린다 (리뷰는 지호).
- 비밀값(`DATABASE_URL`, `KOPIS_API_KEY`, `TOUR_API_KEY`, `COLLECT_TOKEN`)은 `.env`와 Render 환경변수에만 둔다. 커밋, `frontend/`, 채팅에 넣지 않는다.
- 줄바꿈: 대부분의 파일이 CRLF다. 고치거나 새로 만드는 파일도 CRLF로 맞춘다. 원래 LF인 파일(`.env.example`, `.gitignore`, `*.json`, `docs/*.html` 등)은 그대로 둔다. 패치는 `git am --keep-cr`로 적용한다.
- `activities` 칸을 바꿀 때는 `models.py`, `schemas.py`, `docs/db_schema.sql`, 그리고 기존 Supabase 테이블용 `database._ADDED_COLUMNS`를 함께 고친다.
- 모두가 같이 쓰는 값: 유형은 `공연`/`축제`/`전시`/`러닝`, `region`은 `'OO구'` 형식(서울 25개 구 + 대전 5개 구. '중구'는 두 도시에 다 있다).
- 공공 API 자료는 출처를 표시한다. 수집기가 `description` 끝에 붙인다. KOPIS 예매·관객 통계를 화면에 쓰게 되면 집계기간·집계대상·발권 기준 안내도 필요하다 (`docs/COLLECT.md`).

## 공공 API 메모

- KOPIS: `https://kopis.or.kr/openApi/restful/` → `pblprfr`(목록) → `pblprfr/{mt20id}`(상세) → `prfplc/{mt10id}`(주소·위경도). 응답은 XML. 지역 `signgucode` 서울 11 / 대전 30. 키는 발급 후 1년 유효하고, 3개월 넘게 안 쓰면 승인이 취소된다.
- TourAPI: `https://apis.data.go.kr/B551011/KorService2/searchFestival2`. 지역 필터는 `areaCode`가 아니라 `lDongRegnCd`(서울 11 / 대전 30). 분류는 `lclsSystm2`(EV01 축제, EV02 공연, EV03 행사). 키는 공공데이터포털 Decoding 키. 개발계정은 하루 1,000건.
- 같은 행사는 `external_id`(`KOPIS:…`, `TOUR:…`)로 알아보고 고쳐 쓴다. 끝난 행사는 지우지 않는다 (모임이 걸려 있을 수 있다).

## 진행 상황 (2026-10-11 기준)

- [ ] `feat/public-api-collect` 브랜치(공공 API 수집)를 GitHub에 올리고 PR 만들기. 찬휘 계정이 저장소 협업자 초대를 수락해야 push할 수 있다.
- [ ] Render 환경변수에 `KOPIS_API_KEY`, `TOUR_API_KEY`, `COLLECT_TOKEN`을 넣고 Swagger `POST /collect`를 `dry_run=true`로 실행하기. 실제 키로는 아직 호출해 보지 않았다 (모의 응답 테스트만 통과).
- [ ] `seed.py`의 가짜 행사 2건(넙죽이 팬아트 전시, 대전 재즈 나잇)이 `source="API"`로 되어 있어 실제 API 자료로 오해받을 수 있다. 정리하기.
- [ ] (선택) 한국문화정보원 전시 API(`CULTURE_API_KEY`)는 수집기에 아직 연결하지 않았다.
