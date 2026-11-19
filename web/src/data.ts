import type { Activity } from "./types";
import snapshot from "./data/snapshot.json";

export type LoadResult = {
  items: Activity[];
  live: boolean; // true: Render 서버에서 방금 받음, false: 저장본
  savedAt?: string;
};

// Render 무료 서버는 잠들어 있으면 깨어나는 데 50초쯤 걸린다.
// 발표 중에 마냥 기다릴 수 없으니 15초가 지나면 저장본(11/19에 받은 공공 API 자료)으로 먼저 보여 준다.
const TIMEOUT_MS = 15000;

export async function loadActivities(): Promise<LoadResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch("/api/activities?limit=2000", { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = (await res.json()) as Activity[];
    if (!Array.isArray(items) || items.length === 0) throw new Error("빈 응답");
    return { items, live: true };
  } catch {
    return { items: snapshot.items as Activity[], live: false, savedAt: snapshot.saved_at };
  } finally {
    clearTimeout(timer);
  }
}

export function snapshotResult(): LoadResult {
  return { items: snapshot.items as Activity[], live: false, savedAt: snapshot.saved_at };
}
