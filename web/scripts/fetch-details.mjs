// 아직 끝나지 않은 행사의 상세 설명(detail_text)을 배포된 백엔드에서 받아 src/data/details.json 에 저장한다.
// 목록 API(GET /activities)에는 설명 원문이 없어서, 행사마다 GET /activities/{id} 를 부른다.
// 화면의 "🔎 설명에서 찾음" 근거는 이 파일에 있는 실제 설명에서만 나온다. 설명이 없는 행사는 "정보 없음"으로 보인다.
//
// 실행: cd web && npm run data:details   (Render 서버가 잠들어 있으면 처음 1분쯤 걸린다)
import { readFileSync, writeFileSync } from "node:fs";

const API = process.env.API_BASE_URL ?? "https://baf60081-team9.onrender.com";
const CONCURRENCY = 4;

async function getJson(url, tries = 3) {
  for (let i = 1; ; i++) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(60000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      if (i >= tries) throw err;
      await new Promise((r) => setTimeout(r, 3000 * i));
    }
  }
}

let list;
try {
  list = await getJson(`${API}/activities?limit=2000`);
} catch {
  // 서버를 못 부르면 저장본 목록으로 대신한다
  list = JSON.parse(readFileSync("src/data/snapshot.json", "utf8")).items;
}

const today = new Date();
today.setHours(0, 0, 0, 0);
const open = list.filter((a) => {
  const last = a.ends_at ?? a.starts_at;
  return a.source !== "user" && (!last || new Date(last) >= today);
});

const items = {};
let failed = 0;
let next = 0;
async function worker() {
  while (next < open.length) {
    const a = open[next++];
    try {
      const d = await getJson(`${API}/activities/${a.activity_id}`);
      const text = d.detail?.detail_text;
      if (text) items[a.activity_id] = text;
    } catch {
      failed++;
    }
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

const savedAt = new Date().toISOString().slice(0, 10);
writeFileSync("src/data/details.json", JSON.stringify({ saved_at: savedAt, items }));
console.log(`진행 중 행사 ${open.length}건 중 설명 있음 ${Object.keys(items).length}건, 실패 ${failed}건 → src/data/details.json`);
