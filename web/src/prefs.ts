// ─────────────────────────────────────────────────────────────
// "선호" 조건: 데이터에 딱 맞는 칸이 없는 말(아이랑·실내·야외·데이트·체험).
// 걸러내지 않고, 행사마다 근거를 찾아 순서만 바꾼다. 근거는 세 단계로 보여 준다.
//   ✅ 데이터로 확인 : 공공 API의 칸 (예: KOPIS 관람연령 min_age_months)
//   🔎 근거로 추정   : 실제 상세 설명·장소 이름에서 찾은 문구. 화면에 문구를 그대로 보여 준다
//   ❔ 정보 없음     : 빼지 않고 표시만 한다
// 시연에서는 낱말 규칙으로 찾는다. 실제 서비스는 수집할 때 LLM이 설명을 읽고
// {값, 근거 문장} 구조화 출력으로 태그를 달고(4주차), 의미가 비슷한 행사는 임베딩으로 올린다(5주차).
// 낱말 규칙은 틀릴 수 있어서 근거 문구를 꼭 같이 보여 주고, "근거가 틀렸어요"로 알릴 수 있게 한다.
// ─────────────────────────────────────────────────────────────
import type { Activity, Pref } from "./types";
import details from "./data/details.json";
import { fmtAge } from "./filters";

const DETAILS = details.items as Record<string, string>;
export const DETAILS_SAVED_AT = details.saved_at;

export const PREFS: Pref[] = ["family", "indoor", "outdoor", "date", "handson"];
export const PREF_LABEL: Record<Pref, string> = {
  family: "아이랑",
  indoor: "실내",
  outdoor: "야외",
  date: "데이트",
  handson: "체험",
};

// 상세 설명에서 찾는 문구. '아이들을 위해'(기부 행사)처럼 뜻이 다른 말에 걸리지 않게 좁게 잡았다
const TEXT_RULES: Record<Pref, RegExp> = {
  family: /(온\s*가족|가족|어린이|아동극|키즈|유아|아이와\s*함께|아이들과)/,
  indoor: /(실내|전시실|미술관|갤러리|박물관)/,
  outdoor: /(야외|광장|공원|한강|거리\s*공연)/,
  date: /(연인|커플|데이트|야경|로맨틱)/,
  handson: /(체험|만들기|워크숍|참여형)/,
};

// 장소 이름에서 찾는 문구
const PLACE_RULES: Partial<Record<Pref, RegExp>> = {
  indoor: /(미술관|갤러리|박물관|극장|아트센터|아트홀|소극장|공연장|문화센터|홀)/,
  outdoor: /(광장|공원|한강|운동장)/,
};

export type Evidence =
  | { level: "data"; ok: boolean; text: string }
  | { level: "guess"; from: "설명" | "장소 이름" | "행사 유형"; text: string; quote?: [string, string, string] }
  | { level: "none" };

export function detailOf(a: Activity): string | undefined {
  return DETAILS[String(a.activity_id)];
}

// 찾은 문구 앞뒤를 조금 잘라 [앞, 문구, 뒤]로 돌려준다
function snippet(text: string, re: RegExp): [string, string, string] | undefined {
  const m = re.exec(text);
  if (!m) return undefined;
  const start = Math.max(0, m.index - 30);
  const end = Math.min(text.length, m.index + m[0].length + 30);
  return [(start > 0 ? "…" : "") + text.slice(start, m.index), m[0], text.slice(m.index + m[0].length, end) + (end < text.length ? "…" : "")];
}

export function evidenceFor(a: Activity, pref: Pref): Evidence {
  if (pref === "family" && a.min_age_months !== null && a.min_age_months !== undefined) {
    const age = fmtAge(a) ?? "";
    return a.min_age_months <= 84
      ? { level: "data", ok: true, text: `${age} · KOPIS 관람연령` }
      : { level: "data", ok: false, text: `${age}이라 아이와 보기 어려워요 · KOPIS 관람연령` };
  }
  const detail = detailOf(a);
  const quote = detail ? snippet(detail, TEXT_RULES[pref]) : undefined;
  if (quote) return { level: "guess", from: "설명", text: "상세 설명에 이런 문구가 있어요", quote };
  const placeRule = PLACE_RULES[pref];
  const place = placeRule && a.place ? snippet(a.place, placeRule) : undefined;
  if (place) return { level: "guess", from: "장소 이름", text: `장소 이름 ‘${a.place}’로 추정`, quote: undefined };
  if (pref === "indoor" && a.source === "KOPIS" && a.activity_type === "공연") {
    return { level: "guess", from: "행사 유형", text: "공연장 공연이라 실내로 추정" };
  }
  return { level: "none" };
}

function score(e: Evidence) {
  if (e.level === "data") return e.ok ? 3 : -3;
  if (e.level === "guess") return 2;
  return 0;
}

export function prefScore(a: Activity, prefs: Pref[] = []) {
  return prefs.reduce((s, p) => s + score(evidenceFor(a, p)), 0);
}

// 근거가 있는 행사를 위로. 점수가 같으면 원래 순서(진행 중·곧 시작 순)를 지킨다
export function rankByPrefs(items: Activity[], prefs: Pref[] = []): Activity[] {
  if (!prefs.length) return items;
  return items
    .map((a, i) => ({ a, i, s: prefScore(a, prefs) }))
    .sort((x, y) => y.s - x.s || x.i - y.i)
    .map((x) => x.a);
}

export type PrefSummary = { data: number; guess: number; none: number; against: number };

export function summarize(items: Activity[], pref: Pref): PrefSummary {
  const out: PrefSummary = { data: 0, guess: 0, none: 0, against: 0 };
  for (const a of items) {
    const e = evidenceFor(a, pref);
    if (e.level === "data") out[e.ok ? "data" : "against"]++;
    else out[e.level]++;
  }
  return out;
}
