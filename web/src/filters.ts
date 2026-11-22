import type { Activity, City, Conditions, DatePreset } from "./types";

export const SEOUL_GU = [
  "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
  "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
  "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
];
export const DAEJEON_GU = ["동구", "중구", "서구", "유성구", "대덕구"];

export const DATE_LABEL: Record<DatePreset, string> = {
  today: "오늘",
  tomorrow: "내일",
  weekend: "이번 주말",
  thisweek: "이번 주",
  nextweek: "다음 주",
  month: "이번 달",
};

const DAY = 24 * 60 * 60 * 1000;

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function dateRange(p: DatePreset, now = new Date()): [Date, Date] {
  const today = startOfDay(now);
  const dow = today.getDay(); // 0 일 ~ 6 토
  const end = (d: Date) => new Date(d.getTime() + DAY - 1);
  switch (p) {
    case "today":
      return [today, end(today)];
    case "tomorrow": {
      const t = new Date(today.getTime() + DAY);
      return [t, end(t)];
    }
    case "weekend": {
      // 토·일에 물으면 오늘부터 일요일까지, 평일이면 다가오는 토·일
      const sat = dow === 0 ? today : new Date(today.getTime() + ((6 - dow) % 7) * DAY);
      const from = dow === 0 || dow === 6 ? today : sat;
      const sun = dow === 0 ? today : new Date(sat.getTime() + DAY);
      return [from, end(sun)];
    }
    case "thisweek": {
      const sun = new Date(today.getTime() + ((7 - dow) % 7) * DAY);
      return [today, end(sun)];
    }
    case "nextweek": {
      const mon = new Date(today.getTime() + (((8 - dow) % 7) || 7) * DAY);
      return [mon, end(new Date(mon.getTime() + 6 * DAY))];
    }
    case "month": {
      const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      return [today, end(last)];
    }
  }
}

function lastDay(a: Activity): Date | null {
  const s = a.ends_at ?? a.starts_at;
  return s ? new Date(s) : null;
}

export function isOver(a: Activity, now = new Date()) {
  const l = lastDay(a);
  return l !== null && l < startOfDay(now);
}

function overlaps(a: Activity, [from, to]: [Date, Date]) {
  if (!a.starts_at) return true; // 기간 정보가 없으면 늘 열려 있는 것으로 본다
  const s = new Date(a.starts_at);
  const e = lastDay(a) ?? s;
  return s <= to && e >= from;
}

// "전석 20,000원" → 20000, "무료" → 0, 정보 없음 → null. 좌석이 여럿이면 가장 싼 값
export function minCost(a: Activity): number | null {
  const c = a.cost?.trim();
  if (!c || c === "None") return null;
  if (/무료/.test(c)) return 0;
  const nums = [...c.matchAll(/(\d{1,3}(?:,\d{3})+|\d{3,})\s*원/g)].map((m) => parseInt(m[1].replace(/,/g, ""), 10));
  return nums.length ? Math.min(...nums) : null;
}

export function cityOf(region: string | null): City | undefined {
  if (!region) return undefined;
  if (region === "중구") return undefined; // 두 도시에 다 있다
  if (SEOUL_GU.includes(region)) return "서울";
  if (DAEJEON_GU.includes(region)) return "대전";
  return undefined;
}

function inCity(a: Activity, city: City) {
  if (!a.region) return false;
  if (a.region === "중구") {
    // '중구'는 두 도시에 다 있어서 좌표(서울 북위 37.4 이상, 대전 36.5 이하)로 가르고, 없으면 주소·제목 글자로 가른다
    if (typeof a.lat === "number") return city === (a.lat >= 37 ? "서울" : "대전");
    const text = `${a.place ?? ""} ${a.title}`;
    if (/대전/.test(text)) return city === "대전";
    if (/서울/.test(text)) return city === "서울";
    return true;
  }
  return (city === "서울" ? SEOUL_GU : DAEJEON_GU).includes(a.region);
}

export function applyConditions(items: Activity[], c: Conditions, now = new Date()): Activity[] {
  const range = c.date ? dateRange(c.date, now) : null;
  return items.filter((a) => {
    if (isOver(a, now)) return false;
    if (c.city && !inCity(a, c.city)) return false;
    if (c.region && a.region !== c.region) return false;
    if (c.type && a.activity_type !== c.type) return false;
    if (range && !overlaps(a, range)) return false;
    if (c.free || c.maxCost !== undefined) {
      const m = minCost(a);
      if (m === null) return false;
      if (c.free && m !== 0) return false;
      if (c.maxCost !== undefined && m > c.maxCost) return false;
    }
    if (c.ageMonths !== undefined) {
      if (a.min_age_months === null || a.min_age_months === undefined || a.min_age_months > c.ageMonths) return false;
    }
    if (c.maxRuntime !== undefined) {
      if (a.runtime_min === null || a.runtime_min === undefined || a.runtime_min > c.maxRuntime) return false;
    }
    return true;
  });
}

export type Relax = { label: string; next: Conditions; count: number };

// 결과가 0건일 때 "이렇게 바꾸면 N건 있어요"를 실제 데이터로 계산해 제안한다
export function relaxOptions(items: Activity[], c: Conditions): Relax[] {
  const tries: { label: string; next: Conditions }[] = [];
  if (c.free) tries.push({ label: "무료 조건 빼기", next: { ...c, free: undefined } });
  if (c.maxCost !== undefined) tries.push({ label: "가격 조건 빼기", next: { ...c, maxCost: undefined } });
  if (c.ageMonths !== undefined) tries.push({ label: "관람연령 조건 빼기", next: { ...c, ageMonths: undefined } });
  if (c.maxRuntime !== undefined) tries.push({ label: "러닝타임 조건 빼기", next: { ...c, maxRuntime: undefined } });
  if (c.date && c.date !== "month") tries.push({ label: `${DATE_LABEL[c.date]} → 이번 달`, next: { ...c, date: "month" } });
  if (c.date) tries.push({ label: "날짜 조건 빼기", next: { ...c, date: undefined } });
  if (c.region) tries.push({ label: `${c.region} → ${c.city ?? cityOf(c.region) ?? "전체"} 전체`, next: { ...c, region: undefined } });
  if (c.type) tries.push({ label: `${c.type} 말고 다른 유형도`, next: { ...c, type: undefined } });
  if (c.city && !c.region) {
    const other: City = c.city === "서울" ? "대전" : "서울";
    tries.push({ label: `${other}에서 찾기`, next: { ...c, city: other } });
  }
  return tries
    .map((t) => ({ ...t, count: applyConditions(items, t.next).length }))
    .filter((t) => t.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 4);
}

export function fmtDate(s: string | null) {
  if (!s) return "";
  const d = new Date(s);
  return `${d.getMonth() + 1}.${d.getDate()}`;
}

export function fmtPeriod(a: Activity) {
  if (!a.starts_at) return "기간 정보 없음";
  const s = fmtDate(a.starts_at);
  const e = fmtDate(a.ends_at);
  if (!e || e === s) return s;
  const span = (new Date(a.ends_at!).getTime() - new Date(a.starts_at).getTime()) / DAY;
  return span > 120 ? `${s} ~ ${e} (장기)` : `${s} ~ ${e}`;
}

export function fmtCost(a: Activity) {
  const m = minCost(a);
  if (m === null) return "가격 정보 없음";
  if (m === 0) return "무료";
  return `${m.toLocaleString("ko-KR")}원부터`;
}

export function fmtAge(a: Activity): string | null {
  const m = a.min_age_months;
  if (m === null || m === undefined) return null;
  if (m === 0) return "전체 관람가";
  if (m < 48 || m % 12 !== 0) return `${m}개월 이상`;
  return `만 ${m / 12}세 이상`;
}

export function fmtAgeCond(months: number): string {
  if (months === 0) return "전체 관람가";
  if (months < 48 || months % 12 !== 0) return `${months}개월 관람 가능`;
  return `만 ${months / 12}세(초등) 관람 가능`;
}

export function fmtRuntime(a: Activity): string | null {
  const r = a.runtime_min;
  if (!r) return null;
  return `${r}분`;
}

export const SOURCE_LABEL: Record<string, string> = {
  KOPIS: "KOPIS 공연예술통합전산망",
  한국관광공사: "한국관광공사 TourAPI",
  한국문화정보원: "한국문화정보원",
  user: "이용자 등록",
};
