// ─────────────────────────────────────────────────────────────
// 시연용 "가짜 AI". 화면 흐름을 보여 주려고 규칙으로 흉내 낸다.
// 실제 서비스에서는 FastAPI가 LLM을 부른다 (4주차 구조화 출력, 5주차 RAG).
//   parseQuery    → POST /ai/parse   : 문장 → 검색 조건 JSON (response_format = json_schema)
//   answerWithRag → POST /ai/ask     : pgvector로 행사 설명 검색 → 근거만으로 답변 + 출처 번호
//   draftMeetup   → POST /ai/draft   : 행사 정보 → 모임 이름·소개 초안 (사람이 고친 뒤 POST /meetups)
// 행사 자체는 지어내지 않고 항상 공공 API에서 받은 실제 데이터에서만 고른다.
// ─────────────────────────────────────────────────────────────
import type { Activity, Conditions, DatePreset, Parsed } from "./types";
import { DAEJEON_GU, SEOUL_GU, applyConditions, cityOf, fmtCost, fmtPeriod } from "./filters";

const ALL_GU = Array.from(new Set([...SEOUL_GU, ...DAEJEON_GU])).sort((a, b) => b.length - a.length);

const TYPE_RULES: [string, RegExp][] = [
  ["공연", /(공연|뮤지컬|연극|콘서트|클래식|국악|오페라|무용|발레|음악회)/],
  ["축제", /(축제|페스티벌|페스타)/],
  ["전시", /(전시|미술|갤러리|사진전|박물관)/],
  ["러닝", /(러닝|달리기|조깅|마라톤)/],
];

// 알아들었지만 지금 데이터에 칸이 없어 반영할 수 없는 말. 숨기지 않고 화면에 알린다.
const UNSUPPORTED = /(아이랑|아이와|아이들|가족|데이트|커플|혼자|조용한|야외|실내|반려견|강아지|부모님|친구랑|친구와|주차)/g;

export function parseQuery(text: string): Parsed {
  const t = text.trim();
  const c: Conditions = {};

  if (/서울/.test(t)) c.city = "서울";
  else if (/대전/.test(t)) c.city = "대전";

  const gu = ALL_GU.find((g) => t.includes(g));
  if (gu) {
    c.region = gu;
    c.city ??= cityOf(gu);
  }

  for (const [type, re] of TYPE_RULES) {
    if (re.test(t)) {
      c.type = type;
      break;
    }
  }

  let date: DatePreset | undefined;
  if (/오늘/.test(t)) date = "today";
  else if (/내일/.test(t)) date = "tomorrow";
  else if (/다음\s*주/.test(t)) date = "nextweek";
  else if (/(주말|토요일|일요일)/.test(t)) date = "weekend";
  else if (/이번\s*주/.test(t)) date = "thisweek";
  else if (/(이번\s*달|이달|한\s*달)/.test(t)) date = "month";
  if (date) c.date = date;

  if (/(무료|공짜)/.test(t)) c.free = true;
  const man = t.match(/(\d+(?:\.\d+)?)\s*만\s*원?/);
  const won = t.match(/(\d{1,3}(?:,\d{3})+|\d{4,})\s*원/);
  if (man) c.maxCost = Math.round(parseFloat(man[1]) * 10000);
  else if (won) c.maxCost = parseInt(won[1].replace(/,/g, ""), 10);

  const ignored = Array.from(new Set(t.match(UNSUPPORTED) ?? []));
  const known = [c.city || c.region, c.type, c.date, c.free || c.maxCost !== undefined].filter(Boolean).length;
  let confidence = known === 0 ? 0.35 : known === 1 ? 0.7 : 0.92;
  if (ignored.length) confidence -= 0.1;

  return { conditions: c, ignored, confidence: Math.max(0.1, Math.round(confidence * 100) / 100) };
}

// LLM이 돌려줄 JSON 모양. 발표에서 "AI가 실제로 무엇을 만들었는지" 보여 줄 때 쓴다.
export function toSchemaJson(p: Parsed) {
  const c = p.conditions;
  return {
    city: c.city ?? null,
    region: c.region ?? null,
    activity_type: c.type ?? null,
    date_preset: c.date ?? null,
    max_cost: c.maxCost ?? null,
    free_only: c.free ?? false,
    unsupported_preferences: p.ignored,
    confidence: p.confidence,
  };
}

// ── RAG 흉내: 검색 → 근거 문장 + 출처 번호 ───────────────────

export type Sentence = { text: string; refs: number[] };
export type RagAnswer = {
  sentences: Sentence[];
  sources: { item: Activity; score: number }[];
  noEvidence: boolean;
  parsed: Parsed;
};

const PARTICLE = /(에서|으로|하고|이랑|랑|에|을|를|이|가|은|는|도|의|와|과)$/;
const STOP = new Set(["추천", "추천해줘", "알려줘", "있어", "있나요", "어디", "뭐", "갈만한", "갈", "만한", "곳", "행사", "같이", "보고", "싶어", "이번", "다음", "주말", "오늘", "내일"]);

function keywords(q: string) {
  return q
    .split(/[\s,.?!~]+/)
    .map((w) => w.replace(PARTICLE, ""))
    .filter((w) => w.length >= 2 && !STOP.has(w) && !/^\d/.test(w));
}

export function answerWithRag(question: string, items: Activity[]): RagAnswer {
  const parsed = parseQuery(question);
  const pool = applyConditions(items, parsed.conditions);
  const words = keywords(question).filter(
    (w) => !TYPE_RULES.some(([, re]) => re.test(w)) && !ALL_GU.includes(w) && !/^(서울|대전)/.test(w),
  );
  const known = Object.keys(parsed.conditions).length > 0;

  const scored = pool
    .map((item) => {
      let score = 0;
      for (const w of words) {
        if (item.title.includes(w)) score += 3;
        if (item.description?.includes(w)) score += 1;
        if (item.place?.includes(w)) score += 1;
      }
      return { item, score };
    })
    .filter((s) => s.score > 0 || (known && words.length === 0))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  if (scored.length === 0) {
    return {
      sentences: [
        { text: "가지고 있는 공연·축제·전시 자료에서 이 질문의 근거를 찾지 못했어요.", refs: [] },
        { text: "근거 없이 지어내 답하지 않도록 여기서 멈출게요. 지역이나 날짜, 유형을 넣어 다시 물어봐 주세요.", refs: [] },
      ],
      sources: [],
      noEvidence: true,
      parsed,
    };
  }

  const max = Math.max(...scored.map((s) => s.score), 1);
  const sources = scored.map((s, i) => ({ item: s.item, score: Math.round((0.62 + 0.33 * (s.score / max) - i * 0.03) * 100) / 100 }));
  const sentences: Sentence[] = [
    { text: `조건에 맞는 행사 중 근거를 확인한 ${sources.length}곳을 골랐어요.`, refs: [] },
    ...sources.map(({ item }, i) => ({
      text: `「${item.title}」은(는) ${item.place ?? item.region ?? "장소 미정"}에서 ${fmtPeriod(item)}에 열리고, 가격은 ${fmtCost(item)}이에요.`,
      refs: [i + 1],
    })),
    { text: "시간과 가격은 바뀔 수 있으니 가기 전에 원문에서 한 번 더 확인해 주세요.", refs: [] },
  ];
  return { sentences, sources, noEvidence: false, parsed };
}

// ── 모임 초안 ───────────────────────────────────────────────

export type Tone = "friendly" | "short" | "polite";
export type MeetupDraft = { name: string; meetAt: string; place: string; capacity: number; intro: string };

function toLocalInput(d: Date) {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// 행사 기간 안에서 가장 가까운 토요일 오후 2시. 없으면 기간 첫날 오후 2시
function suggestTime(a: Activity, now = new Date()) {
  const start = a.starts_at ? new Date(a.starts_at) : now;
  const end = a.ends_at ? new Date(a.ends_at) : null;
  const from = start > now ? start : now;
  const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 1, 14, 0);
  for (let i = 0; i < 14; i++) {
    if (d.getDay() === 6 && (!end || d <= end)) return d;
    d.setDate(d.getDate() + 1);
  }
  return new Date(from.getFullYear(), from.getMonth(), from.getDate() + 1, 14, 0);
}

function shortTitle(title: string) {
  const t = title.replace(/\s*[[(（［].*?[\])）］]\s*/g, " ").trim();
  return t.length > 18 ? `${t.slice(0, 18)}…` : t;
}

export function draftMeetup(a: Activity, tone: Tone): MeetupDraft {
  const st = shortTitle(a.title);
  const where = a.place ?? a.region ?? "행사장";
  const cost = fmtCost(a);
  const names: Record<Tone, string> = {
    friendly: `${st} 같이 가요!`,
    short: `${st} 동행`,
    polite: `${st} 함께 관람하실 분`,
  };
  const intros: Record<Tone, string> = {
    friendly: `혼자 가기 아쉬워서 같이 갈 분을 찾아요 🙌\n${where}에서 만나서 같이 보고, 끝나고 시간 되면 짧게 이야기 나눠요.\n가격: ${cost} (각자 예매)`,
    short: `${where} · ${cost}\n입구에서 만나 같이 관람해요. 예매는 각자.`,
    polite: `「${a.title}」을(를) 함께 관람하실 분을 모십니다.\n장소: ${where}\n가격: ${cost}이며, 예매는 각자 부탁드립니다.\n처음 뵙는 분들도 편하게 참여해 주세요.`,
  };
  return { name: names[tone], meetAt: toLocalInput(suggestTime(a)), place: `${where} 입구`, capacity: 4, intro: intros[tone] };
}

export function wait(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

