# CLAUDE.md

같이 갈래? — 클라우드컴퓨팅실습(BAF60081) 9조 시연 서비스. Claude Code가 이 저장소에서 일할 때 먼저 읽는 안내다.
사람이 읽는 설명은 README.md와 docs/에 있다.

## 프로젝트

- 공연·축제·전시·러닝 활동을 찾고 → 모임을 열거나 참여하고 → 모임 채팅으로 만나는 서비스. 발표장에서 청중이 QR로 합류하면 라이브 보드(`live.html`)와 분석(`stats.html`) 숫자가 바뀌는 걸 보여준다.
- 최종 발표: 2026-10-21(수). 그 전까지는 큰 구조 변경보다 시연이 안정적으로 도는 것이 우선이다.
- 팀 5명 중 개발자는 1명이다. 설명·문서·커밋 메시지·PR 설명은 비개발자도 읽을 수 있는 쉬운 한국어로 쓴다. git 명령을 쓸 때는 무엇을 왜 하는지 한 줄로 알려준다.
- 역할: 지호(저장소 주인 `jeehoshin`, 프론트·배포), 동주(백엔드·QR), 영선(외부 API), 연경(발표), 찬휘(기획, KOPIS·TourAPI 키 보유).
- 기획 요구사항은 `docs/PLANNING.md`(기획 문서 사본)에 있다. 맨 위 '지금 코드와 다른 점'을 먼저 본다.

## 구조

| 위치 | 내용 | 배포 |
|---|---|---|
| `frontend/` | 빌드 없는 HTML/CSS/JS. 공통 함수는 `app.js`의 `window.Gachi` | Vercel (Root Directory = `frontend`) |
| `backend/app/` | FastAPI + SQLAlchemy. 기능별 API는 `routers/` | Render (`render.yaml`, Python 3.12.7, TZ=Asia/Seoul) |
| `backend/app/collectors/` | 공공 API 수집기 (KOPIS 공연, 한국관광공사 TourAPI 축제·행사, 한국문화정보원 전시) | `POST /collect` |
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
- 기획(`docs/PLANNING.md`)과 코드가 다르면 한쪽에 맞춰 임의로 고치지 않는다. 어느 쪽으로 맞출지 먼저 물어본다.
- 비밀값(`DATABASE_URL`, `KOPIS_API_KEY`, `TOUR_API_KEY`, `COLLECT_TOKEN`)은 `.env`와 Render 환경변수에만 둔다. 커밋, `frontend/`, 채팅에 넣지 않는다.
- 줄바꿈: 대부분의 파일이 CRLF다. 고치거나 새로 만드는 파일도 CRLF로 맞춘다. 원래 LF인 파일(`.env.example`, `.gitignore`, `*.json`, `docs/*.html` 등)은 그대로 둔다. 패치는 `git am --keep-cr`로 적용한다.
- `activities` 칸을 바꿀 때는 `models.py`, `schemas.py`, `docs/db_schema.sql`, 그리고 기존 Supabase 테이블용 `database._ADDED_COLUMNS`를 함께 고친다.
- 모두가 같이 쓰는 값: 유형은 `공연`/`축제`/`전시`/`러닝`, `region`은 `'OO구'` 형식(서울 25개 구 + 대전 5개 구. '중구'는 두 도시에 다 있다).
- 공연·축제·전시는 공공 API에서 받은 자료만 쓴다. 시드·문서·예시·테스트 화면 어디에도 실제처럼 보이는 행사를 지어내 넣지 않는다 (찬휘, 2026-10-11).
- 공공 API 자료는 출처를 표시한다. 수집기가 `description` 끝에 붙인다. 기획은 KOPIS 자료 상세 화면에 집계기간·집계대상·발권 기준 안내도 넣기로 했지만 아직 없다 (정확한 문구는 영선 확인).

## 공공 API 메모

- KOPIS: `https://kopis.or.kr/openApi/restful/` → `pblprfr`(목록) → `pblprfr/{mt20id}`(상세) → `prfplc/{mt10id}`(주소·위경도). 응답은 XML. 지역 `signgucode` 서울 11 / 대전 30. 키는 발급 후 1년 유효하고, 3개월 넘게 안 쓰면 승인이 취소된다. 1초에 10건쯤 넘게 부르면 HTTP 400 "Request Blocked"로 잠깐 막으므로(1초 뒤 풀림) 수집기는 1초에 4건으로 부른다 (`kopis.MIN_INTERVAL`). 서울+대전 수집 한 번에 40초쯤 걸린다.
- TourAPI: `https://apis.data.go.kr/B551011/KorService2/searchFestival2`. 지역 필터는 `areaCode`가 아니라 `lDongRegnCd`(서울 11 / 대전 30). 분류는 `lclsSystm2`(EV01 축제, EV02 공연, EV03 행사). 키는 공공데이터포털 Decoding 키. 개발계정은 하루 1,000건.
- 같은 행사는 `external_id`(`KOPIS:…`, `TOUR:…`)로 알아보고 고쳐 쓴다. 끝난 행사는 지우지 않는다 (모임이 걸려 있을 수 있다).

## 진행 상황 (2026-10-11 기준)

- [ ] `feat/public-api-collect` 브랜치(공공 API 수집)를 GitHub에 올리고 PR 만들기. 찬휘 계정이 저장소 협업자 초대를 수락해야 push할 수 있다.
- [ ] Render 환경변수에 `KOPIS_API_KEY`, `TOUR_API_KEY`, `COLLECT_TOKEN`을 넣고 Swagger `POST /collect`를 `dry_run=true`로 실행하기. 로컬에서는 찬휘 키로 `--dry-run`이 됐다 (2026-10-11, 112건: KOPIS 75 + 한국관광공사 37). Render에서는 아직 안 해 봤다.
- [x] `seed.py`에서 지어낸 공연·축제·전시 3건(넙죽이 팬아트 전시, 대전 재즈 나잇, 캠퍼스 번개 버스킹)과 딸린 모임을 뺐다. 시드에는 사용자가 올린 형태의 러닝 2건만 남는다.
- [ ] 이미 시드가 들어간 Supabase DB에는 위 3건이 남아 있을 수 있다. `seed.py`를 고쳐도 기존 행은 지워지지 않으니 확인하고 정리하기.
- [ ] 기획안과 코드가 다른 점(`docs/PLANNING.md` 맨 위 표)을 어느 쪽으로 맞출지 팀에서 정하기.
- [x] 한국문화정보원 전시 API(`CULTURE_API_KEY`)를 수집기에 연결했다 (`collectors/culture.py`, 출처 `culture`, 영선, 2026-10-11). 전시는 장기 행사가 많아 `max_span_days` 기본값(90)이면 상당수가 빠진다.
- [ ] Render 환경변수에 `CULTURE_API_KEY` 넣기.
