import { useRef, useState } from "react";
import type { Activity, City, Conditions, DatePreset, DemoMode, Parsed } from "../types";
import { parseQuery, toSchemaJson, wait } from "../ai";
import { DATE_LABEL, applyConditions, relaxOptions } from "../filters";
import { ActivityCard, ErrorBox, Proto, StepLoader, type ErrorKind } from "../components";

const EXAMPLES = ["이번 주말 서울 공연", "서울 3만원 이하 공연", "이번 주말 서울 무료 축제", "아이랑 갈 만한 곳"];
const STEPS = ["문장 이해하기", "조건에 맞는 행사 찾기", "결과 정리하기"];
const PAGE = 12;

type Phase = "idle" | "loading" | "confirm" | "error" | "done";

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

  const results = phase === "done" && !forceEmpty ? applyConditions(items, cond) : [];
  const relax = phase === "done" && results.length === 0 ? relaxOptions(items, cond) : [];

  return (
    <section>
      <div className="hero">
        <h1>
          말로 찾는 <em>이번 주 활동</em>
        </h1>
        <p className="lead">평소 말하듯 적으면 AI가 날짜·지역·유형·가격 조건으로 바꿔서 공공 데이터에서 찾아 줘요.</p>
        <form
          className="searchbar"
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: 이번 주말 서울에서 무료로 갈 만한 축제" aria-label="찾고 싶은 활동" maxLength={120} />
          <button className="btn" type="submit" disabled={!q.trim() || phase === "loading"}>
            {phase === "loading" ? "찾는 중…" : "AI로 찾기"}
          </button>
        </form>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip-ex" onClick={() => submit(ex)} disabled={phase === "loading"}>
              {ex}
            </button>
          ))}
        </div>
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
              확신이 낮아서({Math.round(parsed.confidence * 100)}%) 바로 찾지 않고 먼저 물어볼게요.
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
              <span className="label">{edited ? "✏️ 직접 고친 조건" : "🤖 AI가 이렇게 이해했어요"}</span>
              {!edited && <span className={`conf ${parsed.confidence >= 0.8 ? "hi" : "mid"}`}>확신 {Math.round(parsed.confidence * 100)}%</span>}
              <button className="link" onClick={() => setShowJson((v) => !v)}>
                {showJson ? "JSON 닫기" : "AI 응답 JSON 보기"}
              </button>
            </div>
            <ConditionBar cond={cond} onChange={update} />
            <Ignored words={parsed.ignored} />
            {showJson && <pre className="json">{JSON.stringify(toSchemaJson({ ...parsed, conditions: cond }), null, 2)}</pre>}
            <p className="small muted">틀렸다면 칩의 ✕를 누르거나 조건을 추가해 바로 고칠 수 있어요. AI를 다시 부르지 않아요.</p>
          </div>

          {results.length > 0 ? (
            <>
              <p className="count">
                <b>{results.length}건</b> 찾았어요 · 끝난 행사는 뺐어요
              </p>
              <div className="grid">
                {results.slice(0, shown).map((a) => (
                  <ActivityCard key={a.activity_id} a={a} onDraft={onDraft} />
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
                <h3>이 조건에 맞는 행사가 없어요</h3>
                {relax.length > 0 ? (
                  <>
                    <p>조건을 조금 바꾸면 이만큼 있어요.</p>
                    <div className="row">
                      {relax.map((r) => (
                        <button key={r.label} className="chip-ex" onClick={() => update(r.next)}>
                          {r.label} <b>{r.count}건</b>
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
      ⚠️ <b>{words.map((w) => `‘${w}’`).join(", ")}</b>은(는) 아직 데이터에 없는 조건이라 반영하지 못했어요. 결과에서 직접 확인해 주세요.
    </p>
  );
}

const PRICE_OPTS: [string, Conditions][] = [
  ["무료", { free: true }],
  ["1만원 이하", { maxCost: 10000 }],
  ["3만원 이하", { maxCost: 30000 }],
  ["5만원 이하", { maxCost: 50000 }],
];

function ConditionBar({ cond, onChange }: { cond: Conditions; onChange: (c: Conditions) => void }) {
  const chips: { label: string; clear: Conditions }[] = [];
  if (cond.city) chips.push({ label: cond.city, clear: { ...cond, city: undefined, region: undefined } });
  if (cond.region) chips.push({ label: cond.region, clear: { ...cond, region: undefined } });
  if (cond.type) chips.push({ label: cond.type, clear: { ...cond, type: undefined } });
  if (cond.date) chips.push({ label: DATE_LABEL[cond.date], clear: { ...cond, date: undefined } });
  if (cond.free) chips.push({ label: "무료", clear: { ...cond, free: undefined } });
  if (cond.maxCost !== undefined) chips.push({ label: `${(cond.maxCost / 10000).toLocaleString("ko-KR")}만원 이하`, clear: { ...cond, maxCost: undefined } });

  return (
    <div className="chips">
      {chips.length === 0 && <span className="muted small">조건 없음 · 전체에서 찾아요</span>}
      {chips.map((c) => (
        <span key={c.label} className="chip">
          {c.label}
          <button aria-label={`${c.label} 조건 빼기`} onClick={() => onChange(c.clear)}>
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
    </div>
  );
}
