import { useRef, useState } from "react";
import type { Activity, DemoMode } from "../types";
import { answerWithRag, wait, type RagAnswer } from "../ai";
import { ActivityCard, ErrorBox, Proto, StepLoader, type ErrorKind } from "../components";

const EXAMPLES = ["이번 주말 종로구 공연 추천해줘", "서울에서 볼 만한 전시 있어?", "대전 공연 알려줘", "주식 투자는 어떻게 시작해?"];
const STEPS = ["질문 이해하기", "행사 자료에서 근거 찾기", "근거로만 답변 쓰기", "답변과 출처 대조하기"];
const DOWN_REASONS = ["질문 조건과 다른 행사", "날짜·가격 정보 불일치", "설명·근거가 부족함"];

type Turn = { q: string; a: RagAnswer; vote?: "up" | "down"; reason?: string; traceOpen?: boolean; copied?: boolean };

export default function Ask({ items, demo, onDraft }: { items: Activity[]; demo: DemoMode; onDraft: (a: Activity) => void }) {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [err, setErr] = useState<{ kind: ErrorKind; q: string } | null>(null);
  const [hl, setHl] = useState<string | null>(null);
  const run = useRef(0);

  async function ask(text: string) {
    const question = text.trim();
    if (!question) return;
    const id = ++run.current;
    const delay = demo === "slow" ? 2000 : 400;
    setErr(null);
    setLoading(true);
    for (let i = 0; i < STEPS.length; i++) {
      setStep(i);
      await wait(delay);
      if (id !== run.current) return;
      if (i === 0 && (demo === "rate_limit" || demo === "server_down")) {
        setLoading(false);
        setErr({ kind: demo, q: question });
        return;
      }
    }
    let a = answerWithRag(question, items);
    if (demo === "empty") a = answerWithRag("", []);
    setTurns((t) => [...t, { q: question, a }]);
    setQ("");
    setLoading(false);
  }

  function jump(turn: number, ref: number) {
    const key = `t${turn}-ref-${ref}`;
    setHl(key);
    document.getElementById(key)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setHl(null), 1600);
  }

  function updateTurn(idx: number, patch: Partial<Turn>) {
    setTurns((all) => all.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  }

  function copyTurn(idx: number, t: Turn) {
    const plain = t.a.sentences.map((s) => s.text + (s.refs.length ? ` [${s.refs.join(",")}]` : "")).join(" ");
    navigator.clipboard?.writeText(plain);
    updateTurn(idx, { copied: true });
    setTimeout(() => updateTurn(idx, { copied: false }), 1500);
  }

  return (
    <section>
      <div className="hero">
        <h1>
          출처를 달아 답하는 <em>AI 동행 플래너</em>
        </h1>
        <p className="lead">모은 행사 자료에서 근거를 찾아 답하고, 문장마다 어느 자료에서 왔는지 번호로 보여 줘요. 근거가 없으면 지어내지 않아요.</p>
      </div>

      <div className="thread" role="log" aria-live="polite" aria-label="AI 동행 플래너 대화">
        {turns.length === 0 && !loading && !err && (
          <div className="state hint">
            <div className="state-ico">🧭</div>
            <div>
              <h3>이렇게 물어보세요 (클릭하면 바로 질문해요)</h3>
              <p className="small muted">행사 추천 질문과 함께, 근거가 없는 질문("주식 투자는 어떻게 시작해?")에서 환각을 어떻게 차단하는지도 확인해 보세요.</p>
              <div className="row">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="chip-ex" onClick={() => ask(ex)}>
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {turns.map((t, ti) => (
          <div key={ti} className="turn">
            <div className="bubble me">{t.q}</div>
            <div className={`bubble ai ${t.a.noEvidence ? "noev" : ""}`}>
              <div className="bubble-head">
                {t.a.noEvidence ? (
                  <span className="badge warn">⚠️ 근거 없음 · 답변 보류 (No-Evidence Abstain)</span>
                ) : (
                  <span className="badge ok">✓ 답변의 행사·날짜·가격이 모두 출처 카드에 있어요</span>
                )}
                <button className="trace-btn" onClick={() => updateTurn(ti, { traceOpen: !t.traceOpen })}>
                  {t.traceOpen ? "실행 단계(Trace) 접기 ▴" : "🔍 실행 단계(Trace) 보기 ▾"}
                </button>
              </div>

              {t.traceOpen && (
                <ol className="trace-box">
                  <li>
                    <b>① 질문 조건 추출</b>: {Object.keys(t.a.parsed.conditions).length > 0 ? JSON.stringify(t.a.parsed.conditions) : "명시된 지역·유형 조건 없음"}
                  </li>
                  <li>
                    <b>② 후보 문서 검색 (RAG Retrieval)</b>: 공공 데이터 {items.length}건 중 조건·키워드 매칭 상위 <b>{t.a.sources.length}건</b> 추출
                  </li>
                  <li>
                    <b>③ 근거 기반 생성 (Grounded Generation)</b>: {t.a.noEvidence ? "근거 0건 → 할루시네이션 방지를 위해 생성 중단 및 보류 안내" : `검색된 ${t.a.sources.length}건만 프롬프트 [자료] 구획에 주입해 문장별 출처 번호 부착`}
                  </li>
                  {!t.a.noEvidence && (
                    <li>
                      <b>④ 사후 출처 대조 (Fact Verification)</b>: 생성 문장 내 행사명·기간·가격이 원본 카드와 100% 일치함
                    </li>
                  )}
                </ol>
              )}

              <p>
                {t.a.sentences.map((s, si) => (
                  <span key={si}>
                    {s.text}
                    {s.refs.map((r) => (
                      <button key={r} className="fn" onClick={() => jump(ti, r)} aria-label={`출처 ${r}번 보기`}>
                        [{r}]
                      </button>
                    ))}{" "}
                  </span>
                ))}
              </p>

              <div className="vote">
                <button className="btn-ghost sm" onClick={() => copyTurn(ti, t)}>
                  {t.copied ? "✓ 복사됨" : "📋 복사"}
                </button>
                <button className="btn-ghost sm" onClick={() => ask(t.q)} disabled={loading}>
                  🔄 다시 생성
                </button>
                <span className="vote-sep">|</span>
                {t.vote === "up" ? (
                  <span className="small muted">👍 도움이 됐다니 다행이에요! 답변 품질 기록에 반영할게요.</span>
                ) : t.vote === "down" ? (
                  <div className="down-reasons">
                    {t.reason ? (
                      <span className="small muted">✓ ‘{t.reason}’ 의견을 기록했어요. 프롬프트·검색 개선에 반영할게요.</span>
                    ) : (
                      <>
                        <span className="small muted">어떤 점이 아쉬웠나요?</span>
                        {DOWN_REASONS.map((r) => (
                          <button key={r} className="chip-reason" onClick={() => updateTurn(ti, { reason: r })}>
                            {r}
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                ) : (
                  <>
                    <span className="small muted">도움이 됐나요?</span>
                    {(["up", "down"] as const).map((v) => (
                      <button key={v} className="btn-ghost sm" onClick={() => updateTurn(ti, { vote: v })}>
                        {v === "up" ? "👍" : "👎"}
                      </button>
                    ))}
                  </>
                )}
              </div>
            </div>
            {t.a.sources.length > 0 && (
              <div className="sources">
                <p className="small muted">검색된 근거 {t.a.sources.length}건 · 숫자는 질문과의 유사도(시연값) · 위 답변의 [1][2]를 누르면 해당 카드가 강조돼요</p>
                <div className="grid">
                  {t.a.sources.map(({ item, score }, i) => (
                    <div key={item.activity_id} id={`t${ti}-ref-${i + 1}`} className={`src-wrap ${hl === `t${ti}-ref-${i + 1}` ? "hl" : ""}`}>
                      <span className="score">유사도 {score.toFixed(2)}</span>
                      <ActivityCard a={item} refNo={i + 1} onDraft={onDraft} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && <StepLoader steps={STEPS} current={step} slow={demo === "slow"} />}
        {err && <ErrorBox kind={err.kind} onRetry={() => ask(err.q)} onFallback={() => (location.hash = "#search")} fallbackLabel="일반 검색으로 찾기" />}
      </div>

      <form
        className="searchbar sticky"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="행사에 대해 물어보세요 (예: 이번 주말 종로구 공연 추천해줘)" aria-label="질문" maxLength={200} />
        {q && !loading && (
          <button type="button" className="clear-btn" onClick={() => setQ("")} aria-label="입력 지우기">
            ✕
          </button>
        )}
        <button className="btn" disabled={!q.trim() || loading}>
          {loading ? "답변 생성 중…" : "물어보기"}
        </button>
      </form>
      <p className="disclosure">
        🔒 <b>AI 고지 · 환각 방지</b>: AI 동행 플래너는 수집된 공공 데이터 근거로만 답하며, 실명·연락처 등 개인정보는 입력하지 마세요.
      </p>

      <Proto>프로토타입: 실제 서비스는 행사 설명을 임베딩해 Supabase pgvector에서 찾고, LLM이 찾은 자료만으로 답해요. 지금은 키워드 점수로 흉내 냈어요.</Proto>
    </section>
  );
}
