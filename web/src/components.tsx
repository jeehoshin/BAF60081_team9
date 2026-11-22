import { useEffect, useState } from "react";
import type { Activity, Pref } from "./types";
import { SOURCE_LABEL, fmtAge, fmtCost, fmtPeriod, fmtRuntime } from "./filters";
import { PREF_LABEL, evidenceFor } from "./prefs";

const TYPE_ICON: Record<string, string> = { 공연: "🎭", 축제: "🎪", 전시: "🖼️", 러닝: "🏃" };

export function ActivityCard({ a, onDraft, refNo, prefs }: { a: Activity; onDraft?: (a: Activity) => void; refNo?: number; prefs?: Pref[] }) {
  const [imgOk, setImgOk] = useState(Boolean(a.image_url));
  const age = fmtAge(a);
  const runtime = fmtRuntime(a);
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
          {age && <span className="tag">{age}</span>}
          {runtime && <span className="tag">⏱️ {runtime}</span>}
        </div>
        <h3>{a.title}</h3>
        <p className="meta">📅 {fmtPeriod(a)}</p>
        <p className="meta">📍 {a.place ?? "장소 정보 없음"}</p>
        <p className="meta">💳 {fmtCost(a)}</p>
        {prefs && prefs.length > 0 && <EvidenceList a={a} prefs={prefs} />}
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

// 선호(아이랑·실내…)마다 이 행사에서 찾은 근거. ✅ 데이터 · 🔎 추정(문구 그대로) · ❔ 정보 없음
function EvidenceList({ a, prefs }: { a: Activity; prefs: Pref[] }) {
  const [reported, setReported] = useState<Pref[]>([]);
  return (
    <ul className="evid" aria-label="선호 조건 근거">
      {prefs.map((p) => {
        const e = evidenceFor(a, p);
        const label = PREF_LABEL[p];
        if (e.level === "data") {
          return (
            <li key={p} className={e.ok ? "ev-data" : "ev-against"}>
              <b>{e.ok ? "✅" : "⛔"} {label}</b> {e.text}
            </li>
          );
        }
        if (e.level === "none") {
          return (
            <li key={p} className="ev-none">
              <b>❔ {label}</b> 정보 없음 · 원문에서 확인해 주세요
            </li>
          );
        }
        return (
          <li key={p} className="ev-guess">
            <b>🔎 {label}</b> {e.text} <span className="ev-from">({e.from} · AI 추정)</span>
            {e.quote && (
              <q>
                {e.quote[0]}
                <mark>{e.quote[1]}</mark>
                {e.quote[2]}
              </q>
            )}
            {reported.includes(p) ? (
              <span className="ev-thanks">알려 줘서 고마워요. 태그 개선 기록에 남겨요.</span>
            ) : (
              <button className="ev-report" onClick={() => setReported((r) => [...r, p])}>
                근거가 틀렸어요
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// 단계가 보이는 로딩 + 실제 카드 골격을 닮은 Skeleton Screen (ux-loading.js)
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
          ⏳ 평소보다 오래 걸리고 있어요. 무료 AI 서버가 깨어나는 중이거나 요청이 몰렸을 수 있어요.
          {onCancel && (
            <button className="btn-ghost sm" onClick={onCancel}>
              그만 기다리고 직접 고르기
            </button>
          )}
        </p>
      )}
      <div className="skeletons" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skel-card">
            <div className="skeleton skel-thumb" />
            <div className="skel-body">
              <div className="skeleton skel-tag" />
              <div className="skeleton skel-title" />
              <div className="skeleton skel-meta" />
            </div>
          </div>
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
          title: "지금 AI 요청 한도에 도달했어요 (HTTP 429 · Rate Limit)",
          body: "무료 등급 분당 요청 상한에 걸렸어요. 약 30~60초 뒤 다시 시도하거나, AI 없이 조건을 직접 골라 바로 찾을 수 있어요. 입력하신 질문은 지워지지 않고 그대로 남아 있어요.",
        }
      : {
          title: "AI 서버에 연결하지 못했어요 (Connection / Cold Start)",
          body: "무료 클라우드 서버(Render)가 잠들어 있으면 깨어나는 데 최대 1분쯤 걸려요. 기다리는 동안 AI 없이 조건 필터로 바로 찾아볼 수 있어요.",
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
