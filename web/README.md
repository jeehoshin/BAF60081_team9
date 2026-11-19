# 같이 갈래? AI UI 프로토타입 (web/)

금융빅데이터분석실습 5주차 아이디어·UI 공유용으로 만든 React 프로토타입이다.
6주차부터는 이 폴더를 실제 React 프론트엔드의 시작점으로 쓴다.

- **행사는 진짜다.** 배포된 백엔드 `GET /activities`에서 공공 API 자료를 받아 쓴다. 서버가 15초 안에 답하지 않으면 `src/data/snapshot.json`(2026-11-19에 받은 같은 자료)으로 보여 준다.
- **AI만 흉내다.** 문장 해석·답변·모임 초안은 `src/ai.ts`에서 규칙으로 만든다. 실제 LLM 연결은 6~7주차에 FastAPI 쪽에 붙인다.

## 화면

| 주소 | 화면 | 보여 주는 것 |
|---|---|---|
| `#search` | AI 검색 | 한 문장 → 조건 칩(✕로 바로 수정) → 결과. 확신 낮음 확인, 반영 못 한 조건 안내, 결과 없음일 때 실제 건수가 붙은 완화 제안 |
| `#ask` | AI 동행 플래너 | 문장마다 출처 번호 [1][2], 누르면 근거 카드 강조. 근거가 없으면 답변 보류 |
| `#draft-행사번호` | 모임 초안 | 말투별 초안, "AI 초안 / 직접 수정" 배지, 확인 창을 거쳐야 만들어짐(저장은 안 함) |

왼쪽 아래 **🎬 시연 상태**에서 느린 응답 · 요청 한도 초과(429) · 서버 연결 실패 · 결과 없음 · AI 확신 낮음을 골라 다음 AI 요청에 강제로 보여 줄 수 있다.

## 실행

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # 타입 검사 + dist/ 생성
npm run build:html # 파일 하나짜리 HTML → dist-html/gachi-galae-prototype.html (단톡 첨부·서버 없이 열기)
```

개발 서버는 `/api/...` 요청을 Render 백엔드로 넘긴다(`vite.config.ts`). 그래서 백엔드의 CORS 설정을 바꾸지 않아도 된다.

## 배포 (Vercel, 처음 한 번)

1. Vercel → Add New → Project → 이 저장소 선택
2. **Root Directory = `web`**, Framework는 Vite로 자동 인식
3. Deploy. `vercel.json`이 `/api/...`를 Render로 넘겨 준다
4. 받은 주소를 `frontend/plan.html`의 ④ 링크에 넣는다

## 실제 AI로 바꿀 곳

| 지금 (`src/ai.ts`) | 바꿀 것 |
|---|---|
| `parseQuery` | FastAPI `POST /ai/parse` — LLM 구조화 출력으로 조건 JSON, Pydantic으로 검증 |
| `answerWithRag` | FastAPI `POST /ai/ask` — 행사 설명 임베딩 → Supabase pgvector 검색 → 찾은 자료로만 답변 |
| `draftMeetup` | FastAPI `POST /ai/draft` — 초안만 만들고, 저장은 사람이 확인한 뒤 `POST /meetups` |
