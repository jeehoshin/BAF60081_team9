import { useEffect, useState } from "react";
import type { Activity } from "./types";
import { SOURCE_LABEL, fmtCost, fmtPeriod } from "./filters";

const TYPE_ICON: Record<string, string> = { 공연: "🎭", 축제: "🎪", 전시: "🖼️", 러닝: "🏃" };

export function ActivityCard({ a, onDraft, refNo }: { a: Activity; onDraft?: (a: Activity) => void; refNo?: number }) {
  const [imgOk, setImgOk] = useState(Boolean(a.image_url));
  return (
    <article className="card">
      <div className="thumb">
        {imgOk && a.image_url ? (
          <img src={a.image_url} alt="" loading="lazy" onError={() => setImgOk(false)} />
        ) : (
          <span className="thumb-ph">{TYPE_ICON[a.activity_type] ?? "📍"}</span>
        )}
        {refNo && <span className="ref-no">[{refNo}]</span>}
      </div>
      <div className="card-body">
        <div className="card-tags">
          <span className={`tag t-${a.activity_type}`}>{a.activity_type}</span>
          {a.region && <span className="tag">{a.region}</span>}
        </div>
        <h3>{a.title}</h3>
        <p className="meta">📅 {fmtPeriod(a)}</p>
        <p className="meta">📍 {a.place ?? "장소 정보 없음"}</p>
        <p className="meta">💳 {fmtCost(a)}</p>
        <div className="card-foot">
          <span className="src" title="데이터 출처">
            출처 · {SOURCE_LABEL[a.source] ?? a.source}
          </span>
          <div className="card-actions">
            {a.source_url && (
              <a className="btn-ghost sm" href={a.source_url} target="_blank" rel="noreferrer">
                원문 ↗
              </a>
            )}
            {onDraft && (
              <button className="btn sm" onClick={() => onDraft(a)}>
                이 행사로 모임 만들기
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

// 단계가 보이는 로딩. 기다리는 이유를 알려 주면 같은 시간도 덜 답답하다.
export function StepLoader({ steps, current, slow, onCancel }: { steps: string[]; current: number; slow: boolean; onCancel?: () => void }) {
  const [late, setLate] = useState(false);
  useEffect(() => {
    setLate(false);
    const t = setTimeout(() => setLate(true), 4000);
    return () => clearTimeout(t);
  }, [slow]);
  return (
    <div className="loader" role="status" aria-live="polite">
      <ol className="steps">
        {steps.map((s, i) => (
          <li key={s} className={i < current ? "done" : i === current ? "now" : ""}>
            <span className="dot">{i < current ? "✓" : i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      {slow && late && (
        <p className="late">
          평소보다 오래 걸리고 있어요. AI 서버가 바쁜 것 같아요.
          {onCancel && (
            <button className="btn-ghost sm" onClick={onCancel}>
              그만 기다리고 직접 고르기
            </button>
          )}
        </p>
      )}
      <div className="skeletons">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton" />
        ))}
      </div>
    </div>
  );
}

export type ErrorKind = "rate_limit" | "server_down";

export function ErrorBox({ kind, onRetry, onFallback, fallbackLabel }: { kind: ErrorKind; onRetry: () => void; onFallback: () => void; fallbackLabel: string }) {
  const msg =
    kind === "rate_limit"
      ? {
          title: "지금 AI 요청이 몰렸어요 (429)",
          body: "잠시 쉬었다가 다시 시도하거나, AI 없이 조건을 직접 골라 바로 찾을 수 있어요. 입력한 문장은 그대로 남아 있어요.",
        }
      : {
          title: "AI 서버에 연결하지 못했어요",
          body: "무료 서버가 잠들어 있으면 깨어나는 데 1분쯤 걸려요. 기다리는 동안 AI 없이 찾아볼 수 있어요.",
        };
  return (
    <div className="state error" role="alert">
      <div className="state-ico">{kind === "rate_limit" ? "⏳" : "🔌"}</div>
      <div>
        <h3>{msg.title}</h3>
        <p>{msg.body}</p>
        <div className="row">
          <button className="btn" onClick={onRetry}>
            다시 시도
          </button>
          <button className="btn-ghost" onClick={onFallback}>
            {fallbackLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Proto({ children }: { children: React.ReactNode }) {
  return <p className="proto-note">🧪 {children}</p>;
}
