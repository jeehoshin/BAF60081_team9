# 배포 가이드 (Supabase + Render + Vercel)

목표: **한 개의 공유 DB(Supabase)** 위에 FastAPI(Render)와 HTML(Vercel)을 올려, 발표장에서 모두가 같은 서비스에 들어와 등록·모임·채팅이 보이게 한다.

```
[휴대폰 QR] → Vercel(frontend) → Render(FastAPI) → Supabase(PostgreSQL)
                                      ↑
                              Swagger /docs
```

키 발급 목록은 [KEYS.md](KEYS.md) 참고.

---

## 1. Supabase

1. 프로젝트 생성 (리전: Northeast Asia / Seoul 가능하면 선택)
2. **SQL Editor**에서 `docs/db_schema.sql` 전체 실행
3. **Project Settings → Database → Connection string (URI)** 복사  
   - Render용: **Transaction pooler** + `?sslmode=require`
4. DB 비밀번호를 팀 시크릿 채널로만 공유 (단톡 평문 지양)

---

## 2. Render (백엔드)

1. New → Web Service → GitHub 저장소 연결
2. Root Directory: `backend`
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Environment

| Key | Value |
|-----|--------|
| `DATABASE_URL` | Supabase URI |
| `CORS_ORIGINS` | `https://<vercel-app>.vercel.app` (로컬 테스트면 함께 콤마 추가) |
| `USE_MEMORY` | `0` |
| `KOPIS_API_KEY` | (공공 API 수집용) KOPIS 인증키 |
| `TOUR_API_KEY` | (공공 API 수집용) TourAPI Decoding 키 |
| `COLLECT_TOKEN` | (공공 API 수집용) `POST /collect` 실행 비밀 문자열 |

6. 배포 후 확인
   - `https://<service>.onrender.com/health` → `"mode":"database"`
   - `https://<service>.onrender.com/docs` → Swagger (발표 자료 주소)

무료 플랜은 15분 쉬면 잠들어 첫 응답이 30~60초 걸린다. 세 겹으로 대비한다.
- GitHub Actions `keep-warm`이 한국 시간 08~22시에 10분마다 `/health`를 불러 잠들지 않게 한다 (`.github/workflows/keep-warm.yml`).
- 그래도 **발표 직전 `/health`를 직접 한 번 열어** `"mode":"database"`를 확인한다 (아래 6장).
- 혹시 늦으면 화면 아래에 "서버를 깨우는 중이에요…" 안내가 뜬다 (`app.js`). 1분 안에 풀린다.

7. 공공 API 행사 넣기: Swagger `POST /collect` (`x-collect-token` 입력, 처음엔 `dry_run=true`) → [COLLECT.md](COLLECT.md)
   - 이번 버전부터 시작할 때 `activities`에 새 칸(ends_at 등)이 없으면 자동으로 추가된다

---

## 3. Vercel (프론트)

1. Import GitHub 저장소
2. Root Directory: `frontend`
3. Framework: Other (빌드 명령 없음)
4. `frontend/config.js`의 `API_BASE_URL`을 Render URL로 수정 후 커밋·배포

```js
window.APP_CONFIG = {
  API_BASE_URL: "https://<service>.onrender.com",
};
```

5. 배포 URL 확인 후 Render `CORS_ORIGINS`에 그 URL을 넣는다 (순서: Vercel 먼저 올려 URL 확보 → Render CORS 수정 → 재배포).

---

## 4. 발표 당일 플로우

1. 프로젝터: `live.html` (라이브 보드)
2. 보조 화면/인쇄: `qr.html` (등록 QR)
3. 청중: QR → 닉네임 등록 → 활동 선택 → 모임 참여 → 메시지
4. 라이브 보드에서 이용자·참여·메시지 카운트가 올라가는지 확인
5. `stats.html`에서 분포가 바뀌는 장면 보여주기 — 맨 위 **"오늘 QR 참여자만"** 버튼을 누르면 미리 들어 있던 데이터를 빼고 오늘 청중 숫자만 보인다

---

## 6. 발표 전 체크 (전날 저녁 + 당일 30분 전)

| 순서 | 할 일 | 확인 |
|---|---|---|
| 1 | Supabase에 `docs/cleanup_test_data.sql` 실행 (지어낸 행사·테스트 이용자 정리) | `stats.html` 데이터 품질 표에 `API` 출처가 없음 |
| 2 | Swagger `POST /collect` (`days=15`쯤, 11/1까지 들어오게) → 이어서 `POST /collect/kopis-stats` | 응답의 `inserted`/`updated`, `stats.html` "최근 수집 기록"에 줄이 생김 |
| 3 | `https://baf60081-team9.onrender.com/health` 열기 | `"mode":"database"` |
| 4 | Vercel 주소에서 `index.html` → 활동 하나 → 모임 참여 → `talk.html` 메시지 1개 | 라이브 보드에 뜸 |
| 5 | `stats.html` 맨 위 "오늘 QR 참여자만" 눌러 보기 | 방금 만든 것만 세어짐 |
| 6 | GitHub → Actions → `backend-tests`가 초록인지 | main 최신 커밋에 초록 체크 |
| 7 | 발표 노트북에서 `live.html`, `qr.html`, `stats.html` 탭을 미리 열어 둔다 | — |

---

## 5. 로컬에서 팀 DB에 붙기

```bash
cp .env.example .env
# DATABASE_URL, CORS_ORIGINS, USE_MEMORY=0 설정

cd backend
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

다른 터미널:

```bash
cd frontend
# config.js → http://127.0.0.1:8000
npx --yes serve -l 5500
```

로컬 프론트도 같은 Supabase를 보면, 팀원 화면과 데이터가 공유된다.
