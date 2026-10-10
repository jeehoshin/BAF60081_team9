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

무료 플랜은 잠들면 첫 응답이 느리다. **발표 직전 `/health` 한 번 호출**해 깨워 둔다.

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
5. `stats.html`에서 분포가 바뀌는 장면 보여주기

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
