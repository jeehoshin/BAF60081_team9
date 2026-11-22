// 백엔드 GET /activities 응답 한 건 (backend/app/schemas.py ActivityOut 중 화면에 쓰는 칸)
export type Activity = {
  activity_id: number;
  activity_type: string; // 공연 · 축제 · 전시 · 러닝
  title: string;
  place: string | null;
  region: string | null; // 'OO구'
  starts_at: string | null;
  ends_at: string | null;
  cost: string | null;
  description: string | null;
  source: string; // KOPIS · 한국관광공사 · 한국문화정보원 · user
  source_url: string | null;
  image_url: string | null;
  lat?: number | null;
  min_age_months?: number | null; // 관람 가능 최소 나이(개월). 전체 관람가 0, 모르면 null
  runtime_min?: number | null; // 러닝타임(분)
};

export type City = "서울" | "대전";
// 걸러내지 않고 순서에만 반영하는 선호 (prefs.ts)
export type Pref = "family" | "indoor" | "outdoor" | "date" | "handson";
export type DatePreset = "today" | "tomorrow" | "weekend" | "thisweek" | "nextweek" | "month";

// AI가 문장에서 뽑아내는 검색 조건. 실제 서비스에서는 LLM 구조화 출력의 스키마가 된다.
export type Conditions = {
  city?: City;
  region?: string;
  type?: string;
  date?: DatePreset;
  maxCost?: number;
  free?: boolean;
  ageMonths?: number; // 이 나이(개월)인 사람도 볼 수 있는 행사만 (min_age_months <= ageMonths)
  maxRuntime?: number; // 러닝타임이 이 분 이하인 행사만 (runtime_min <= maxRuntime)
  prefs?: Pref[]; // 선호: 걸러내지 않고 근거 있는 행사를 위로 올린다
};

export type Parsed = {
  conditions: Conditions;
  ignored: string[]; // 알아들었지만 데이터에 없어 반영하지 못한 말
  confidence: number; // 0~1
};

// 발표 때 원하는 상태를 바로 보여 주기 위한 시연 모드
export type DemoMode = "normal" | "slow" | "rate_limit" | "server_down" | "empty" | "unsure";
