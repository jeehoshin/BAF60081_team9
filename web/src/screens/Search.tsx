import { useRef, useState } from "react";
import type { Activity, City, Conditions, DatePreset, DemoMode, Parsed, Pref } from "../types";
import { parseQuery, toSchemaJson, wait } from "../ai";
import { DATE_LABEL, applyConditions, fmtAgeCond, relaxOptions } from "../filters";
import { ActivityCard, ErrorBox, HeroArt, Proto, StepLoader, type ErrorKind } from "../components";
import { PREFS, PREF_LABEL, rankByPrefs, summarize } from "../prefs";

const EXAMPLES = ["이번 주말 서울 공연", "이번 주말 아이랑 갈 만한 곳", "아이랑 볼 90분 이하 공연", "주차 편한 실내 데이트"];
const STEPS = ["문장 이해하기", "조건에 맞는 행사 찾기", "결과 정리하기"];
const PAGE = 12;

type Phase = "idle" | "loading" | "confirm" | "error" | "done";

function countRecognized(c: Conditions) {
  return [
    c.city,
    c.region,
    c.type,
    c.date,
    c.free ? "free" : undefined,
    c.maxCost !== undefined ? "cost" : undefined,
    c.ageMonths !== undefined ? "age" : undefined,
    c.maxRuntime !== undefined ? "run" : undefined,
    ...(c.prefs ?? []),
  ].filter(Boolean).length;
}

export default function Search({ items, demo, onDraft }: { items: Activity[]; demo: DemoMode; onDraft: (a: Activity) => void }) {
  const [q, setQ] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState(0);
  const [slow, setSlow] = useState(false);
  const [err, setErr] = useState<ErrorKind>("rate_limit");
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const [cond, setCond] = useState<Conditions>({});
  const [edited, setEdited] = useState(false);
  const [forceEmpty, setForceEmpty] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [shown, setShown] = useState(PAGE);
  const run = useRef(0);

  async function submit(text: string) {
    const query = text.trim();
    if (!query) return;
    const id = ++run.current;
    const delay = demo === "slow" ? 2200 : 450;
    setQ(query);
    setSlow(demo === "slow");
    setPhase("loading");
    setStep(0);
    setShown(PAGE);
    setShowJson(false);

    await wait(delay);
    if (id !== run.current) return;
    if (demo === "rate_limit" || demo === "server_down") {
      setErr(demo);
      setPhase("error");
      return;
    }
    const p = parseQuery(query);
    if (demo === "unsure") p.confidence = 0.42;
    let forced = false;
    if (demo === "empty") {
      // 실제 데이터로 0건이 되는 조건을 덧붙여서, 아래 "조건 바꾸기" 제안의 건수가 진짜 숫자로 나오게 한다
      const tries: Conditions[] = [{ free: true }, { free: true, date: "today" }, { free: true, date: "today", region: "대덕구" }];
      const hit = tries.find((t) => applyConditions(items, { ...p.conditions, ...t }).length === 0);
      if (hit) p.conditions = { ...p.conditions, ...hit };
      else forced = true;
    }
    setParsed(p);
    setCond(p.conditions);
    setEdited(false);
    setForceEmpty(forced);
    setStep(1);
    await wait(delay);
    if (id !== run.current) return;
    if (p.confidence < 0.6) {
      setPhase("confirm");
      return;
    }
    setStep(2);
    await wait(delay / 2);
    if (id !== run.current) return;
    setPhase("done");
  }

  // AI 없이 조건을 직접 고르는 길. 오류·지연·낮은 확신 어디서든 이리로 빠질 수 있다.
  function manual() {
    run.current++;
    setParsed({ conditions: {}, ignored: [], confidence: 1 });
    setCond({});
    setEdited(true);
    setForceEmpty(false);
    setPhase("done");
  }

  function update(next: Conditions) {
    setCond(next);
    setEdited(true);
    setForceEmpty(false);
    setShown(PAGE);
  }

  // 조건으로 걸러낸 뒤, 선호(아이랑·실내…)는 근거 있는 행사를 위로 올린다
  const results = phase === "done" && !forceEmpty ? rankByPrefs(applyConditions(items, cond), cond.prefs) : [];
  // 나이를 숫자로 걸러내면 관람연령 칸이 없는 행사(전시·축제 등)는 빠진다. 몇 건이 빠졌는지 알려 준다
  const ageUnknown =
    phase === "done" && cond.ageMonths !== undefined
      ? applyConditions(items, { ...cond, ageMonths: undefined }).filter((a) => a.min_age_months === null || a.min_age_months === undefined).length
      : 0;
  const relax = phase === "done" && results.length === 0 ? relaxOptions(items, cond) : [];
  const recCount = countRecognized(cond);

  return (
    <section>
      <div className="hero">
        <div className="hero-card">
        <p className="eyebrow">공연 · 축제 · 전시 동행</p>
        <div className="band" />
        <h1>이번 주말, 어디 갈래?</h1>
        <p className="strip">Ask in one sentence</p>
        <p className="lead">평소 말하듯 적으면 AI가 날짜·지역·유형·가격 같은 조건으로 걸러 주고, ‘아이랑·실내’처럼 딱 맞는 칸이 없는 말은 근거를 찾아 순서로 반영해요.</p>
        <form
          className="searchbar"
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: 이번 주말 서울에서 무료로 갈 만한 축제" aria-label="찾고 싶은 활동" maxLength={120} />
          {q && phase !== "loading" && (
            <button type="button" className="clear-btn" onClick={() => setQ("")} aria-label="입력 지우기">
              ✕
            </button>
          )}
          <button className="btn" type="submit" disabled={!q.trim() || phase === "loading"}>
            {phase === "loading" ? "찾는 중…" : "찾아 줘"}
          </button>
        </form>
        <div className="examples" aria-label="추천 예시 질문">
          <span className="ex-label">예시</span>
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip-ex" onClick={() => submit(ex)} disabled={phase === "loading"}>
              {ex}
            </button>
          ))}
        </div>
        <p className="disclosure">질문은 외부 AI 모델로 보내지고, AI는 틀릴 수 있어요. 이름·연락처 같은 개인정보는 적지 마세요. (지금 프로토타입은 규칙으로 흉내 내서 어디에도 보내지 않아요)</p>
        </div>
        <HeroArt />
      </div>

      {phase === "idle" && (
        <div className="state hint">
          <div className="state-ico">💬</div>
          <div>
            <h3>무엇을 하고 싶은지 한 줄로 적어 보세요</h3>
            <p>
              지금 볼 수 있는 활동 <b>{applyConditions(items, {}).length}건</b> (모은 자료 {items.length}건 중 끝나지 않은 것 · KOPIS · 한국관광공사 · 한국문화정보원). 조건을 직접 고르고 싶다면{" "}
              <button className="link" onClick={manual}>
                AI 없이 찾기
              </button>
            </p>
          </div>
        </div>
      )}

      {phase === "loading" && <StepLoader steps={STEPS} current={step} slow={slow} onCancel={manual} />}

      {phase === "error" && <ErrorBox kind={err} onRetry={() => submit(q)} onFallback={manual} fallbackLabel="AI 없이 조건 직접 고르기" />}

      {phase === "confirm" && parsed && (
        <div className="state confirm">
          <div className="state-ico">🤔</div>
          <div>
            <h3>이렇게 이해했는데, 맞나요?</h3>
            <p>
              문장을 제대로 이해했는지 확실하지 않아서 바로 찾지 않고 먼저 물어볼게요. (알아들은 조건 {countRecognized(parsed.conditions)}개)
            </p>
            <ConditionBar cond={cond} onChange={update} />
            <Ignored words={parsed.ignored} />
            <div className="row">
              <button className="btn" onClick={() => setPhase("done")}>
                맞아요, 이대로 찾기
              </button>
              <button className="btn-ghost" onClick={manual}>
                조건 직접 고르기
              </button>
            </div>
          </div>
        </div>
      )}

      {phase === "done" && parsed && (
        <>
          <div className="understood">
            <div className="understood-head">
              <span className="label">{edited ? "직접 고친 조건" : "AI가 이해한 조건"}</span>
              <span className={`conf ${recCount >= 2 ? "hi" : "mid"}`} title="모델의 자체 확신도 숫자 대신 실제로 검증 가능한 조건 수와 검색 건수를 표시합니다 (AI-UX 원칙)">
                ✓ 인식 조건 {recCount}개 · 근거 행사 {results.length}건
              </span>
              {parsed.ignored.length > 0 && !edited && <span className="conf mid">⚠️ 미반영 {parsed.ignored.length}개</span>}
              <button className="link" onClick={() => setShowJson((v) => !v)}>
                {showJson ? "스키마 JSON 닫기" : "AI 응답 JSON · 검증 보기"}
              </button>
            </div>
            <ConditionBar cond={cond} onChange={update} />
            <p className="legend small muted">
              <span className="chip mini">조건</span> 맞지 않으면 걸러내요 · <span className="chip pref mini">✨ 선호</span> 걸러내지 않고 근거 있는 행사를 위로 올려요
            </p>
            <Ignored words={parsed.ignored} />
            {showJson && (
              <div className="json-wrap">
                <p className="json-note">
                  💡 <b>4주차 구조화 출력(Pydantic) &amp; AI-UX 신뢰도 원칙</b>: 모델이 자체 출력한 <code>confidence({parsed.confidence})</code>는 실제 정답 확률이 아니므로, 화면 상단에는 <b>검증 가능한 사실(인식한 조건 {recCount}개 · 매칭 행사 {results.length}건)</b>로 표현합니다.
                </p>
                <pre className="json">{JSON.stringify(toSchemaJson({ ...parsed, conditions: cond }), null, 2)}</pre>
              </div>
            )}
            <p className="small muted">틀렸다면 칩의 ✕를 누르거나 조건을 추가해 바로 고칠 수 있어요. AI를 다시 부르지 않아요.</p>
          </div>

          {ageUnknown > 0 && (
            <p className="ignored">
              관람연령 정보가 없는 행사 <b>{ageUnknown}건</b>(주로 전시·축제)은 나이 조건 때문에 빠졌어요.{" "}
              <button className="link" onClick={() => update({ ...cond, ageMonths: undefined, prefs: Array.from(new Set([...(cond.prefs ?? []), "family" as Pref])) })}>
                빼지 말고 ‘아이랑’ 선호로 바꾸기
              </button>
            </p>
          )}

          {results.length > 0 ? (
            <>
              <div className="res-head">
                <h2>찾은 행사 {results.length}건</h2>
                <p>공공 데이터에 있는 행사만 보여 줘요 · 끝난 행사는 뺐어요</p>
              </div>
              {(cond.prefs ?? []).map((pref) => {
                const s = summarize(results, pref);
                return (
                  <p key={pref} className="pref-sum">
                    <span className="chip pref mini">✨ {PREF_LABEL[pref]}</span>
                    근거: <span className="ev-pill ev-data">✅ 데이터로 확인 {s.data}</span>
                    <span className="ev-pill ev-guess">🔎 설명·장소로 추정 {s.guess}</span>
                    <span className="ev-pill ev-none">❔ 정보 없음 {s.none}</span>
                    {s.against > 0 && <span className="ev-pill ev-against">⛔ 맞지 않음 {s.against}</span>}
                  </p>
                );
              })}
              <div className="grid">
                {results.slice(0, shown).map((a) => (
                  <ActivityCard key={a.activity_id} a={a} onDraft={onDraft} prefs={cond.prefs} />
                ))}
              </div>
              {shown < results.length && (
                <button className="btn-ghost more" onClick={() => setShown((n) => n + PAGE)}>
                  {Math.min(PAGE, results.length - shown)}건 더 보기
                </button>
              )}
            </>
          ) : (
            <div className="state empty">
              <div className="state-ico">🔍</div>
              <div>
                <h3>이 조건에 맞는 행사가 없어요. 더 넓게 찾아볼까요?</h3>
                {relax.length > 0 ? (
                  <>
                    <p>조건 하나를 빼면 결과가 늘어나요. 숫자는 지금 데이터로 센 실제 건수예요.</p>
                    <div className="row">
                      {relax.map((r) => (
                        <button key={r.label} className="chip-ex" onClick={() => update(r.next)}>
                          {r.label} · {r.count}건
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <p>조건을 하나씩 빼 보거나 다른 말로 다시 물어봐 주세요.</p>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <Proto>프로토타입: 문장 해석은 규칙으로 흉내 낸 시연용 AI예요. 행사 목록은 공공 API에서 받은 실제 데이터예요.</Proto>
    </section>
  );
}

function Ignored({ words }: { words: string[] }) {
  if (!words.length) return null;
  return (
    <p className="ignored">
      ⚠️ <b>{words.map((w) => `‘${w}’`).join(", ")}</b>은(는) 공공 데이터에 근거를 찾을 정보가 없어서 반영하지 못했어요. 원문 링크나 장소에 직접 확인해 주세요.
    </p>
  );
}

const PRICE_OPTS: [string, Conditions][] = [
  ["무료", { free: true }],
  ["1만원 이하", { maxCost: 10000 }],
  ["3만원 이하", { maxCost: 30000 }],
  ["5만원 이하", { maxCost: 50000 }],
];

const AGE_OPTS: [string, number][] = [
  ["전체 관람가", 0],
  ["36개월 관람 가능", 36],
  ["만 7세(초등) 관람 가능", 84],
  ["만 12세 관람 가능", 144],
];

const RUNTIME_OPTS: [string, number][] = [
  ["60분 이하", 60],
  ["90분 이하", 90],
  ["120분 이하", 120],
];

function ConditionBar({ cond, onChange }: { cond: Conditions; onChange: (c: Conditions) => void }) {
  // kind는 칩 색: 장소 · 유형 · 날짜 · 가격 · 관람 조건
  const chips: { label: string; clear: Conditions; kind: string }[] = [];
  if (cond.city) chips.push({ label: cond.city, clear: { ...cond, city: undefined, region: undefined }, kind: "place" });
  if (cond.region) chips.push({ label: cond.region, clear: { ...cond, region: undefined }, kind: "place" });
  if (cond.type) chips.push({ label: cond.type, clear: { ...cond, type: undefined }, kind: "type" });
  if (cond.date) chips.push({ label: DATE_LABEL[cond.date], clear: { ...cond, date: undefined }, kind: "date" });
  if (cond.free) chips.push({ label: "무료", clear: { ...cond, free: undefined }, kind: "price" });
  if (cond.maxCost !== undefined) chips.push({ label: `${(cond.maxCost / 10000).toLocaleString("ko-KR")}만 원 이하`, clear: { ...cond, maxCost: undefined }, kind: "price" });
  if (cond.ageMonths !== undefined) chips.push({ label: fmtAgeCond(cond.ageMonths), clear: { ...cond, ageMonths: undefined }, kind: "meta" });
  if (cond.maxRuntime !== undefined) chips.push({ label: `${cond.maxRuntime}분 이하`, clear: { ...cond, maxRuntime: undefined }, kind: "meta" });
  const prefs = cond.prefs ?? [];
  const setPrefs = (next: Pref[]) => onChange({ ...cond, prefs: next.length ? next : undefined });

  return (
    <div className="chips">
      {chips.length === 0 && prefs.length === 0 && <span className="muted small">조건 없음 · 전체에서 찾아요</span>}
      {chips.map((c) => (
        <span key={c.label} className={`chip k-${c.kind}`}>
          {c.label}
          <button aria-label={`${c.label} 조건 빼기`} onClick={() => onChange(c.clear)}>
            ✕
          </button>
        </span>
      ))}
      {prefs.map((p) => (
        <span key={p} className="chip pref" title="걸러내지 않고, 근거 있는 행사를 위로 올려요">
          ✨ {PREF_LABEL[p]}
          <button aria-label={`${PREF_LABEL[p]} 선호 빼기`} onClick={() => setPrefs(prefs.filter((x) => x !== p))}>
            ✕
          </button>
        </span>
      ))}
      {!cond.city && (
        <select aria-label="도시 추가" value="" onChange={(e) => onChange({ ...cond, city: e.target.value as City })}>
          <option value="">+ 도시</option>
          <option>서울</option>
          <option>대전</option>
        </select>
      )}
      {!cond.type && (
        <select aria-label="유형 추가" value="" onChange={(e) => onChange({ ...cond, type: e.target.value })}>
          <option value="">+ 유형</option>
          <option>공연</option>
          <option>축제</option>
          <option>전시</option>
        </select>
      )}
      {!cond.date && (
        <select aria-label="날짜 추가" value="" onChange={(e) => onChange({ ...cond, date: e.target.value as DatePreset })}>
          <option value="">+ 날짜</option>
          {(Object.keys(DATE_LABEL) as DatePreset[]).map((k) => (
            <option key={k} value={k}>
              {DATE_LABEL[k]}
            </option>
          ))}
        </select>
      )}
      {!cond.free && cond.maxCost === undefined && (
        <select aria-label="가격 추가" value="" onChange={(e) => onChange({ ...cond, ...PRICE_OPTS[Number(e.target.value)][1] })}>
          <option value="">+ 가격</option>
          {PRICE_OPTS.map(([label], i) => (
            <option key={label} value={i}>
              {label}
            </option>
          ))}
        </select>
      )}
      {cond.ageMonths === undefined && (
        <select aria-label="관람연령 추가" value="" onChange={(e) => onChange({ ...cond, ageMonths: Number(e.target.value) })}>
          <option value="">+ 관람연령</option>
          {AGE_OPTS.map(([label, m]) => (
            <option key={m} value={m}>
              {label}
            </option>
          ))}
        </select>
      )}
      {cond.maxRuntime === undefined && (
        <select aria-label="러닝타임 추가" value="" onChange={(e) => onChange({ ...cond, maxRuntime: Number(e.target.value) })}>
          <option value="">+ 러닝타임</option>
          {RUNTIME_OPTS.map(([label, m]) => (
            <option key={m} value={m}>
              {label}
            </option>
          ))}
        </select>
      )}
      {prefs.length < PREFS.length && (
        <select aria-label="선호 추가" value="" onChange={(e) => setPrefs([...prefs, e.target.value as Pref])}>
          <option value="">+ 선호</option>
          {PREFS.filter((p) => !prefs.includes(p)).map((p) => (
            <option key={p} value={p}>
              {PREF_LABEL[p]}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
