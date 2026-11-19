import { useRef, useState } from "react";
import type { Activity, DemoMode } from "../types";
import { answerWithRag, wait, type RagAnswer } from "../ai";
import { ActivityCard, ErrorBox, Proto, StepLoader, type ErrorKind } from "../components";

const EXAMPLES = ["이번 주말 종로구 공연 추천해줘", "서울에서 볼 만한 전시 있어?", "대전 공연 알려줘", "주식 투자는 어떻게 시작해?"];
const STEPS = ["질문 이해하기", "행사 자료에서 근거 찾기", "근거로만 답변 쓰기", "답변과 출처 대조하기"];

type Turn = { q: string; a: RagAnswer; vote?: "up" | "down" };

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

  return (
    <section>
      <div className="hero">
        <h1>
          출처를 달아 답하는 <em>AI 동행 플래너</em>
        </h1>
        <p className="lead">모은 행사 자료에서 근거를 찾아 답하고, 문장마다 어느 자료에서 왔는지 번호로 보여 줘요. 근거가 없으면 지어내지 않아요.</p>
      </div>

      <div className="thread">
        {turns.length === 0 && !loading && !err && (
          <div className="state hint">
            <div className="state-ico">🧭</div>
            <div>
              <h3>이렇게 물어보세요</h3>
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
              {t.a.noEvidence && <span className="badge warn">근거 없음 · 답변 보류</span>}
              {!t.a.noEvidence && <span className="badge ok">✓ 답변의 행사·날짜·가격이 모두 출처 카드에 있어요</span>}
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
                {t.vote ? (
                  <span className="small muted">의견 고마워요. 답변 품질 기록에 남겨 프롬프트 개선에 써요.</span>
                ) : (
                  <>
                    <span className="small muted">도움이 됐나요?</span>
                    {(["up", "down"] as const).map((v) => (
                      <button key={v} className="btn-ghost sm" onClick={() => setTurns((all) => all.map((x, i) => (i === ti ? { ...x, vote: v } : x)))}>
                        {v === "up" ? "👍" : "👎"}
                      </button>
                    ))}
                  </>
                )}
              </div>
            </div>
            {t.a.sources.length > 0 && (
              <div className="sources">
                <p className="small muted">검색된 근거 {t.a.sources.length}건 · 숫자는 질문과의 유사도(시연값)</p>
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
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="행사에 대해 물어보세요" aria-label="질문" maxLength={200} />
        <button className="btn" disabled={!q.trim() || loading}>
          물어보기
        </button>
      </form>

      <Proto>프로토타입: 실제 서비스는 행사 설명을 임베딩해 Supabase pgvector에서 찾고, LLM이 찾은 자료만으로 답해요. 지금은 키워드 점수로 흉내 냈어요.</Proto>
    </section>
  );
}
