# 같이 갈래? — GitHub 저장소 생성 요청 / 로컬 스택 정리

9조 시연 서비스 코드가 로컬(`C:\cloud\team_project`)에 다 만들어져 있어.
아직 git 저장소가 아니고 원격도 없어서, **빈 GitHub 저장소만 만들어서 나를 초대**해주면 내가 바로 push할게.

---

## 1. 부탁할 것 (5분)

1. GitHub에서 **New repository**
   - 이름 예시: `gachi-galae` (팀에서 정한 이름이면 아무거나)
   - **Public** (Vercel·Render 무료 연동 편함)
   - ⚠️ **README / .gitignore / License 전부 체크 해제** → 완전히 빈 저장소로
2. **Settings → Collaborators → Add people** 로 나를 초대 (권한: Write 이상)
3. 저장소 URL 알려주기 (`https://github.com/<계정>/gachi-galae.git`)

그 다음은 내가 로컬에서:

```bash
cd C:\cloud\team_project
git init -b main
git add .
git commit -m "init: 같이 갈래? 시연 서비스"
git remote add origin https://github.com/<계정>/gachi-galae.git
git push -u origin main
```

`.env`, `.venv`, `__pycache__`, `node_modules`, `.vercel` 은 `.gitignore`에 있어서 **키·가상환경은 올라가지 않아.**

### (대안) 같이 보낸 zip으로 네가 직접 올리는 경우

zip(`gachi-galae_handoff.zip`)에는 키·가상환경을 뺀 전체 코드가 들어 있어.
압축 풀고 그 폴더(README.md가 있는 위치)에서 위 명령을 그대로 실행하면 돼.

### 화면 미리보기 (백엔드 없이)

`frontend/*.html`을 더블클릭하면 디자인은 보이지만, 데이터는 백엔드(8000)가 떠 있어야 나와.
제대로 보려면 아래 5번 "로컬 실행법"대로 백엔드 + 프론트를 둘 다 띄우면 돼.

---

## 2. 전체 구조

```
이용자(QR/폰) ──► Vercel (frontend/, 정적 HTML)
                    │  fetch (API_BASE_URL)
                    ▼
               Render (backend/, FastAPI)
                    │  SQLAlchemy + psycopg2
                    ▼
               Supabase (PostgreSQL)

지도 타일: OpenStreetMap (키 불필요)
공공 API 3종 → scripts/collect_activities.py → Supabase (수집 골격만 있음)
```

| 계층 | 기술 | 배포 | 위치 |
|------|------|------|------|
| 프론트 | 순수 HTML / CSS / JS (빌드 없음) + Leaflet 1.9.4 + qrcodejs (CDN) | Vercel | `frontend/` |
| 백엔드 | FastAPI 0.115.6 · Uvicorn 0.32.1 · SQLAlchemy 2.0.36 · Pydantic 2.10.3 | Render | `backend/` |
| DB | PostgreSQL (Supabase, pooler 6543) / 로컬은 메모리 SQLite | Supabase | `docs/db_schema.sql` |
| 수집 | Python 스크립트 (httpx) | 로컬 실행 | `scripts/` |

---

## 3. 내 로컬 환경 (실제 확인한 버전)

| 항목 | 버전 / 값 |
|------|-----------|
| OS | Windows 11 (PowerShell) |
| Python (backend/.venv) | 3.13.5 — Render는 `runtime.txt` 기준 **3.12.7** |
| Node / npm | v24.11.1 / 11.6.2 (프론트 로컬 서빙용 `npx serve`만 사용) |
| gh CLI | 2.89.0 (로그인 안 됨) |
| 백엔드 로컬 | `http://127.0.0.1:8000` (Swagger: `/docs`) — `USE_MEMORY=1` 메모리 DB + 시드 데이터 |
| 프론트 로컬 | `http://127.0.0.1:5500` (`frontend/serve.json`으로 clean URL 끔) |

---

## 4. 폴더 / 파일

```
backend/
  app/
    main.py        앱 생성, CORS, 라우터 등록, 시작 시 테이블 생성 + 시드
    config.py      환경변수 (DATABASE_URL, CORS_ORIGINS, USE_MEMORY)
    database.py    Supabase 연결 (sslmode 자동), 없으면 메모리 SQLite
    models.py      users, activities, meetups, participants, likes, messages
    schemas.py     요청/응답 스키마
    seed.py        KAIST 주변 좌표 시드 (유저 5, 활동 5, 모임 4, 메시지 3)
    routers/
      users.py       POST/GET /users
      activities.py  활동 목록·상세·등록·좋아요
      meetups.py     모임 목록·개설·참여·채팅
      map.py         지도용 카드 (누가/언제/어디서/어떻게), 내 모임톡 목록
      stats.py       분석 지표
      live.py        발표용 라이브 보드
  requirements.txt
  runtime.txt      python-3.12.7
frontend/
  config.js        API_BASE_URL  ← 배포 시 Render 주소로 변경
  app.js           공통 (API 호출, 로그인 저장, 상단 내비, 마스코트)
  index.html       활동 탐색        (home.js)
  map.html         지도 + 타임라인, 지도 클릭으로 모임 개설 (map.js)
  talk.html        모임톡 버블 채팅  (talk.js)
  activity.html    활동 상세 + 모임 참여
  create.html      활동 올리기
  register.html    닉네임 합류 (QR 진입점)
  qr.html          발표용 QR
  live.html        발표용 라이브 보드
  stats.html       분석
  mascot.svg       넙죽이 스타일 이미지 (공식 PNG는 assets/nubzuki.png에 넣으면 자동 교체)
  styles.css, vercel.json, serve.json
scripts/collect_activities.py   공공 API 수집 골격 (파서 TODO)
docs/   KEYS.md · DEPLOY.md · api.md · db.md · db_schema.sql · team09_progress.html
render.yaml   Render 블루프린트 (rootDir=backend, /health, TZ=Asia/Seoul)
.env.example  환경변수 템플릿
```

---

## 5. 로컬 실행법

```powershell
# 백엔드
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:USE_MEMORY="1"      # Supabase 없이 UI만 볼 때. 팀 공유 DB면 .env에 DATABASE_URL + USE_MEMORY=0
uvicorn app.main:app --reload --port 8000

# 프론트 (다른 터미널)
cd frontend
npx --yes serve -l 5500
```

---

## 6. 키 / 환경변수 (값은 절대 GitHub에 올리지 않음)

| 변수 | 필수 | 넣는 곳 | 내용 |
|------|------|---------|------|
| `DATABASE_URL` | ✅ | 로컬 `.env`, Render | Supabase Transaction pooler URI (6543) |
| `CORS_ORIGINS` | ✅ | Render | Vercel 배포 URL (콤마 구분) |
| `USE_MEMORY` | ✅ | Render | `0` |
| `API_BASE_URL` | ✅ | `frontend/config.js` | Render 서비스 URL (키 아님) |
| `TOUR_API_KEY` | 수집 시 | 로컬 `.env` | 한국관광공사 TourAPI |
| `KOPIS_API_KEY` | 수집 시 | 로컬 `.env` | KOPIS 공연 |
| `CULTURE_API_KEY` | 수집 시 | 로컬 `.env` | 한국문화정보원 전시 |

- 지도(OpenStreetMap)·QR은 **키 불필요**
- Supabase `anon` / `service_role` 키는 이 구조에서 **안 씀** (FastAPI만 DB 접근)
- 자세한 발급처: `docs/KEYS.md`

---

## 7. 저장소 생긴 뒤 배포 순서

1. Supabase SQL Editor에서 `docs/db_schema.sql` 실행
2. Render → New → Blueprint → 이 저장소 선택 (`render.yaml` 자동 인식) → `DATABASE_URL`, `CORS_ORIGINS` 입력
3. Vercel → Import → 이 저장소, **Root Directory = `frontend`**, Framework = Other
4. `frontend/config.js`의 `API_BASE_URL`을 Render URL로 바꿔 push → Vercel 자동 재배포
5. Render `CORS_ORIGINS`에 Vercel URL 넣고 재배포

자세한 건 `docs/DEPLOY.md`.
