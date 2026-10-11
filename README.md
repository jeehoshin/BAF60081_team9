# 같이 갈래? (Activity First) — 9조

날짜·지역·취향에 맞는 활동(공연·축제·전시·러닝)을 찾고, **함께할 사람과 실시간으로 연결**하는 시연용 서비스.

## 아키텍처

| 계층 | 기술 | 배포 |
|------|------|------|
| 프론트 | HTML/CSS/JS | **Vercel** |
| 백엔드 | FastAPI | **Render** |
| DB | PostgreSQL | **Supabase** |
| 수집 | KOPIS · 한국관광공사 TourAPI | Swagger `POST /collect` 또는 로컬 스크립트 |

```
이용자(QR) → Vercel → Render(FastAPI) → Supabase
KOPIS·TourAPI → POST /collect (또는 scripts/collect_activities.py) → Supabase activities
```

## 저장소 구조

```
backend/     FastAPI (Render) · 공공 API 수집기 backend/app/collectors/
frontend/    시연 화면 (Vercel)
scripts/     공공 API 수집 로컬 실행용
docs/        키 체크리스트 · 수집 · 배포 · API · DB
```

## 필요한 키 (정확히 이 목록)

자세한 발급처·체크표: **[docs/KEYS.md](docs/KEYS.md)**

| 필수 | 변수 | 용도 |
|------|------|------|
| ✅ | `DATABASE_URL` | Supabase 연결 (Render + 로컬) |
| ✅ | `CORS_ORIGINS` | Vercel URL 허용 |
| ✅ | `frontend/config.js` → `API_BASE_URL` | Render API 주소 |
| 수집시 | `TOUR_API_KEY` | 한국관광공사 TourAPI (Decoding 키) |
| 수집시 | `KOPIS_API_KEY` | KOPIS 공연 |
| 수집시 | `COLLECT_TOKEN` | Swagger `POST /collect` 실행용 비밀 문자열 |
| 선택 | `CULTURE_API_KEY` | 한국문화정보원 전시 (아직 수집기 미연결) |

## 공공 API 수집

KOPIS(공연)와 한국관광공사 TourAPI(축제·공연·행사)에서 **서울·대전** 행사를 받아 `activities`에 넣는다.
Render에 `KOPIS_API_KEY`·`TOUR_API_KEY`·`COLLECT_TOKEN`을 넣고 Swagger에서 **POST /collect** (처음엔 `dry_run=true`).
다시 실행해도 같은 행사가 두 번 생기지 않는다. 자세한 방법·오류 대처·출처 표시: **[docs/COLLECT.md](docs/COLLECT.md)**

## 시연 화면

| 페이지 | 역할 |
|--------|------|
| `register.html` / `qr.html` | QR 이용자 등록 |
| `index.html` | 활동 탐색 |
| `map.html` | 지도 + 타임라인 (누가/언제/어디서/어떻게), 지도에서 모임 개설 |
| `talk.html` | 모임톡 (버블 채팅) |
| `activity.html` | 활동 상세 + 모임 참여 |
| `live.html` | 발표용 라이브 보드 (등록·참여·메시지 실시간) |
| `stats.html` | 수집/이용 데이터 분석 |
| `create.html` | 러닝 등 사용자 활동 등록 |

발표 흐름: **프로젝터에 live → 청중 QR 등록 → 모임 참여·메시지 → 통계 변화**.

## 로컬 실행

```bash
cp .env.example .env
# USE_MEMORY=0 + DATABASE_URL(Supabase) 권장 (팀과 데이터 공유)
# UI만 볼 때는 USE_MEMORY=1

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npx --yes serve -l 5500
```

- API/Swagger: http://127.0.0.1:8000/docs  
- 프론트: http://127.0.0.1:5500  

## 배포

순서와 환경변수: **[docs/DEPLOY.md](docs/DEPLOY.md)**

1. Supabase에 `docs/db_schema.sql` 실행  
2. Render에 `backend` 배포 (`DATABASE_URL`, `CORS_ORIGINS`, `USE_MEMORY=0`)  
3. Vercel에 `frontend` 배포 (`config.js`의 API URL 수정)  

## 문서

- [로컬 스택 정리 / 저장소 인계](docs/HANDOFF.md)
- [기획 요구사항 (기획 문서 사본)](docs/PLANNING.md)
- [키 체크리스트](docs/KEYS.md)
- [공공 API 수집](docs/COLLECT.md)
- [배포](docs/DEPLOY.md)
- [API](docs/api.md)
- [DB](docs/db.md)
- [진행 현황 HTML](docs/team09_progress.html) (있으면)

## 보안

- `.env` / Render·Vercel 시크릿에만 키 보관. GitHub 커밋 금지 (공공 API 키는 Vercel·`config.js`에도 넣지 않음)
- 공공 API 자료는 출처 표시 필수: KOPIS·한국관광공사 (설명 끝에 자동으로 붙음)
- QR은 닉네임 권장, 실이용자 개인정보 AI 입력 금지
- Supabase `service_role` 키는 이 구조에서 프론트에 넣지 않음
