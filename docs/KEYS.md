# 필요한 키·계정 체크리스트

발표/배포까지 **팀에서 발급해야 하는 것**만 정리했다.  
키 값은 `.env` / Render·Vercel Environment Variables에만 넣고, GitHub에 올리지 않는다.

---

## 1) 반드시 필요 (서비스 기동·배포)

| # | 이름 (환경변수) | 어디에 씀 | 발급처 | 누가 | 상태 |
|---|-----------------|-----------|--------|------|------|
| 1 | `DATABASE_URL` | FastAPI → Supabase PostgreSQL 연결 | [Supabase](https://supabase.com) → Project → **Project Settings → Database → Connection string (URI)** | 지호(프로젝트 생성) → 동주(Render에 등록) | ☐ |
| 2 | `CORS_ORIGINS` | 백엔드가 Vercel 프론트 허용 | 키 아님. Vercel 배포 URL을 콤마로 넣음. 예: `https://gachi-galae.vercel.app` | 지호 | ☐ |
| 3 | `API_BASE_URL` | 프론트(`frontend/config.js`)가 Render API 호출 | 키 아님. Render 서비스 URL. 예: `https://gachi-galae-api.onrender.com` | 지호 | ☐ |

### Supabase `DATABASE_URL` 고르는 법

1. Supabase 대시보드 → **Project Settings → Database**
2. **Connection string** → URI
3. 발표/Render에서는 **Transaction pooler** 권장 (포트 `6543`)
4. `[YOUR-PASSWORD]`를 DB 비밀번호로 바꾸고, 끝에 `?sslmode=require` 붙이기

예시 형태:

```text
postgresql://postgres.xxxx:비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres?sslmode=require
```

Direct 연결(포트 `5432`)도 가능하지만, Render 무료 플랜에서는 pooler가 더 안정적인 경우가 많다.

### Supabase에서 추가로 쓸 수 있는 값 (선택)

| 이름 | 용도 | 비고 |
|------|------|------|
| Project URL | 대시보드 참고용 | FastAPI SQLAlchemy 경로에서는 필수 아님 |
| `anon` / `service_role` key | Supabase JS 클라이언트로 프론트가 DB에 직접 붙을 때 | **이 프로젝트는 FastAPI만 DB에 붙이므로 기본 불필요**. 노출 주의(`service_role`은 절대 프론트에 넣지 말 것) |

---

## 2) 데이터 수집용 공공 API 키 (영선)

| # | 이름 (환경변수) | API 정식 명칭 | 제공 기관 | 발급처 | 담당 데이터 | 상태 |
|---|-----------------|---------------|-----------|--------|-------------|------|
| 4 | `TOUR_API_KEY` | 한국관광공사_국문 관광정보 서비스_GW | 한국관광공사 | [공공데이터포털](https://www.data.go.kr) 활용신청 | 축제·행사 | ☐ (문서상 10/6 발급) |
| 5 | `KOPIS_API_KEY` | 공연예술통합전산망(KOPIS) 오픈 API | (재)예술경영지원센터 | [KOPIS](https://www.kopis.or.kr) 오픈API (별도 가입) | 공연 | ☐ (문서상 10/7 발급) |
| 6 | `CULTURE_API_KEY` | 한국문화정보원_한눈에보는문화정보조회서비스 | 한국문화정보원 | [공공데이터포털](https://www.data.go.kr) | 전시 | ☐ (문서상 10/6 발급) |

> 세 키는 **수집 스크립트(`scripts/collect_activities.py`)** 전용이다.  
> 웹 시연만 먼저 할 때는 더미/시드 데이터로도 동작하며, 발표 자료에는 출처(명칭·기관·URL)를 반드시 적는다.

엔드포인트 참고:

- TourAPI: `https://apis.data.go.kr/B551011/KorService2`
- KOPIS: `https://www.kopis.or.kr` 오픈 API (상세 URL 확인 필요)
- 문화정보: `https://apis.data.go.kr/B553457/cultureinfo`

---

## 3) 배포 계정 (키 파일은 아님, 로그인 필요)

| # | 서비스 | 용도 | 담당 | 상태 |
|---|--------|------|------|------|
| 7 | GitHub 계정 + 퍼블릭 저장소 | 소스 공유, Vercel/Render 연동 | 지호 | ☐ |
| 8 | [Render](https://render.com) 계정 | FastAPI 배포 → Swagger UI 주소 | 지호(+동주) | ☐ |
| 9 | [Vercel](https://vercel.com) 계정 | HTML 프론트 배포 → 서비스/QR URL | 지호 | ☐ |
| 10 | Supabase 프로젝트 | PostgreSQL DB | 지호 | ☐ |

---

## 4) 어디에 무엇을 넣나

### 로컬 `.env` (루트, gitignore됨)

```env
DATABASE_URL=postgresql://...pooler.supabase.com:6543/postgres?sslmode=require
CORS_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
TOUR_API_KEY=...
KOPIS_API_KEY=...
CULTURE_API_KEY=...
USE_MEMORY=0
```

### Render (Web Service 환경변수)

| 변수 | 값 |
|------|----|
| `DATABASE_URL` | Supabase URI |
| `CORS_ORIGINS` | Vercel URL (+ 로컬 테스트 URL) |
| `USE_MEMORY` | `0` |

### Vercel / 프론트

| 위치 | 내용 |
|------|------|
| `frontend/config.js` → `API_BASE_URL` | Render URL (예: `https://xxx.onrender.com`) |

공공 API 키는 **Vercel에 넣지 않는다** (프론트 노출 금지).

---

## 5) 최소 발급 순서 (이번 주말)

1. Supabase 프로젝트 생성 → `DATABASE_URL` 확보 → `docs/db_schema.sql` 실행  
2. Render에 FastAPI 올리고 `DATABASE_URL` / `CORS_ORIGINS` 설정  
3. Vercel에 `frontend` 올리고 `config.js`의 `API_BASE_URL`을 Render로 변경  
4. 팀원 전원 QR 등록 → 모임 참여 → 라이브 보드에서 숫자가 변하는지 확인  
5. (병렬) 공공 API 3종 호출 테스트 후 수집 스크립트에 키 연결  

---

## 한 줄 요약

- **서비스가 돌아가려면**: `DATABASE_URL` + Render URL + Vercel URL(+CORS)  
- **행사 실데이터를 넣으려면**: `TOUR_API_KEY`, `KOPIS_API_KEY`, `CULTURE_API_KEY`  
- **프론트에 넣으면 안 되는 것**: 모든 API 키, Supabase `service_role`, DB 비밀번호  
