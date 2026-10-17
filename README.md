# 같이 갈래? (Activity First) — 9조

날짜·지역·취향에 맞는 활동(공연·축제·전시·러닝)을 찾고, **함께할 사람과 실시간으로 연결**하는 시연용 서비스.

## 아키텍처

| 계층 | 기술 | 배포 |
|------|------|------|
| 프론트 | HTML/CSS/JS | **Vercel** |
| 백엔드 | FastAPI | **Render** |
| DB | PostgreSQL | **Supabase** |
| 수집 | KOPIS(공연·공연 통계) · 한국관광공사 TourAPI(축제·행사) · 한국문화정보원(전시) | Swagger `POST /collect`, `POST /collect/kopis-stats` 또는 로컬 스크립트 |

```
이용자(QR) → Vercel → Render(FastAPI) → Supabase
KOPIS·TourAPI·한국문화정보원 → POST /collect (또는 scripts/collect_activities.py) → Supabase activities
KOPIS 통계(시·도·장르·일별) → POST /collect/kopis-stats (또는 scripts/collect_kopis_stats.py) → Supabase kopis_stats
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
| 수집시 | `CULTURE_API_KEY` | 한국문화정보원 전시 (공공데이터포털 키, TourAPI와 같은 키여도 됨) |

## 공공 API 수집

공공 API 세 곳에서 **서울·대전** 행사를 받아 `activities`에 넣고, KOPIS 통계는 따로 `kopis_stats`에 쌓는다.

| 출처 | 받는 것 | 저장 위치 | 실행 |
|------|---------|-----------|------|
| KOPIS 공연예술통합전산망 | 공연 목록·상세·공연장 위치 | `activities` (`source`=KOPIS) | `POST /collect` |
| 한국관광공사 TourAPI | 축제·공연·행사 | `activities` (`source`=한국관광공사) | `POST /collect` |
| 한국문화정보원 한눈에보는문화정보 | 전시 | `activities` (`source`=한국문화정보원) | `POST /collect` |
| KOPIS 공연 통계 (전국) | 시·도별·장르별·일별 판매액·상연 횟수·관객 수 | `kopis_stats` | `POST /collect/kopis-stats` |

- Render에 `KOPIS_API_KEY`·`TOUR_API_KEY`·`CULTURE_API_KEY`·`COLLECT_TOKEN`을 넣고 Swagger에서 실행한다 (처음엔 `dry_run=true`).
- 다시 실행해도 같은 행사가 두 번 생기지 않는다 (`external_id`로 알아보고 고쳐 씀).
- 자세한 방법·오류 대처·출처 표시: **[docs/COLLECT.md](docs/COLLECT.md)**

### 분석 페이지 (`stats.html`)에서 보여 주는 것

| 지표 | API | 설명 |
|------|-----|------|
| 수집 활동·모임·이용자 현황 | `GET /stats/activities`, `/stats/meetups`, `/stats/users` | 지역·유형별 활동 수, 모임 충원율, 연령대·성별 분포. **"오늘 QR 참여자만"** 버튼(`since`)으로 발표 당일 청중 데이터만 따로 봄 |
| 구별 인구 10만 명당 활동 수 | `GET /stats/regions` | 서울 25개 구·대전 5개 구의 활동 수를 구 주민등록 인구로 나눠 서울 vs 대전 비교 (지표 G) |
| 공연 시장 (KOPIS 통계) | `GET /stats/kopis` | 시·도별 판매액 비중, 장르별 상연 횟수·판매액, 요일별 관객 |
| 인구 10만 명당 서울 vs 대전 | `GET /stats/kopis` | 판매액·상연 횟수·관객 수를 시·도 주민등록 인구(행정안전부, 2026년 9월 말)로 나눔 |
| 데이터 품질 | `GET /stats/quality` | 출처별 수집 건수, 이미지·좌표 빈 비율, 진행 중·예정·종료 비율, 출처 간 중복 후보, **최근 수집 기록**(`collect_runs`: 언제, 몇 건 받아 몇 건 저장·제외) |

## 시연 화면

| 페이지 | 역할 |
|--------|------|
| `register.html` / `qr.html` | QR 이용자 등록 |
| `index.html` | 활동 탐색 (지역은 대전 전체/서울 전체/구 단위, 날짜 빠른 필터) |
| `map.html` | 지도 + 타임라인 (누가/언제/어디서/어떻게), 지도에서 모임 개설 |
| `talk.html` | 모임톡 (버블 채팅) |
| `activity.html` | 활동 상세 + 모임 참여 |
| `live.html` | 발표용 라이브 보드 (등록·참여·메시지 실시간) |
| `stats.html` | 수집/이용 데이터 분석 (KOPIS 통계, 인구 10만 명당 비교, 데이터 품질) |
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

## 테스트

```bash
cd backend
python -m unittest discover tests -v   # 인증키·인터넷 없이 돌아간다
```

PR을 올리면 GitHub Actions(`backend-tests`)가 같은 테스트를 자동으로 돌려 PR 화면에 초록/빨강으로 표시한다.
`keep-warm` 워크플로는 한국 시간 08~22시에 10분마다 Render `/health`를 불러 서버가 잠들지 않게 한다.

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
- 공공 API 자료는 출처 표시 필수: KOPIS·한국관광공사·한국문화정보원 (설명 끝에 자동으로 붙음). KOPIS 통계는 분석 화면에 집계 기준 안내 문구를 함께 표시
- 인구 자료 출처: 행정안전부 주민등록 인구통계 (분석 화면에 기준월 표시)
- QR은 닉네임 권장, 실이용자 개인정보 AI 입력 금지
- Supabase `service_role` 키는 이 구조에서 프론트에 넣지 않음
