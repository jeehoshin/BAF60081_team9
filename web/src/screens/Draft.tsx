import { useEffect, useMemo, useRef, useState } from "react";
import type { Activity, DemoMode } from "../types";
import { draftMeetup, wait, type MeetupDraft, type Tone } from "../ai";
import { applyConditions, fmtCost, fmtPeriod } from "../filters";
import { ErrorBox, Proto, StepLoader, type ErrorKind } from "../components";

const STEPS = ["행사 정보 읽기", "모임 초안 쓰기"];
const TONES: [Tone, string][] = [
  ["friendly", "친근하게"],
  ["short", "짧게"],
  ["polite", "정중하게"],
];
type Field = keyof MeetupDraft;
const EMPTY: MeetupDraft = { name: "", meetAt: "", place: "", capacity: 4, intro: "" };

export default function Draft({ items, demo, activityId }: { items: Activity[]; demo: DemoMode; activityId: number | null }) {
  const activity = items.find((a) => a.activity_id === activityId) ?? null;
  const [tone, setTone] = useState<Tone>("friendly");
  const [form, setForm] = useState<MeetupDraft>(EMPTY);
  const [aiFields, setAiFields] = useState<Set<Field>>(new Set());
  const [phase, setPhase] = useState<"loading" | "error" | "edit" | "confirm" | "created">("loading");
  const [step, setStep] = useState(0);
  const [err, setErr] = useState<ErrorKind>("rate_limit");
  const run = useRef(0);

  async function generate(t: Tone) {
    if (!activity) return;
    const id = ++run.current;
    const delay = demo === "slow" ? 2000 : 450;
    setPhase("loading");
    setStep(0);
    await wait(delay);
    if (id !== run.current) return;
    if (demo === "rate_limit" || demo === "server_down") {
      setErr(demo);
      setPhase("error");
      return;
    }
    setStep(1);
    await wait(delay);
    if (id !== run.current) return;
    setForm(draftMeetup(activity, t));
    setAiFields(new Set<Field>(["name", "meetAt", "place", "capacity", "intro"]));
    setPhase("edit");
  }

  useEffect(() => {
    if (activity) generate(tone);
  }, [activityId]);

  if (!activity) return <Picker items={items} />;

  function set<K extends Field>(k: K, v: MeetupDraft[K]) {
    setForm((f) => ({ ...f, [k]: v }));
    setAiFields((s) => {
      const n = new Set(s);
      n.delete(k);
      return n;
    });
  }

  function writeMyself() {
    run.current++;
    setForm({ ...EMPTY, place: activity!.place ?? "" });
    setAiFields(new Set());
    setPhase("edit");
  }

  const problems: string[] = [];
  if (!form.name.trim()) problems.push("모임 이름을 적어 주세요.");
  if (form.name.length > 40) problems.push("모임 이름은 40자까지예요.");
  if (form.capacity < 4 || form.capacity > 20) problems.push("정원은 4~20명이에요.");
  if (!form.meetAt) problems.push("만날 시간을 골라 주세요.");
  const outside =
    form.meetAt && activity.ends_at && new Date(form.meetAt) > new Date(activity.ends_at) ? "만날 시간이 행사가 끝난 뒤예요. 날짜를 확인해 주세요." : null;

  const Badge = ({ k }: { k: Field }) => (aiFields.has(k) ? <span className="badge ai">AI 초안</span> : <span className="badge me">직접 수정</span>);

  return (
    <section>
      <div className="hero">
        <div className="hero-card">
          <p className="eyebrow">모임 초안 · 03</p>
          <div className="band" />
          <h1>
            AI가 쓰고, <em>내가 정하는</em> 모임
          </h1>
          <p className="strip">Draft by AI, decided by you</p>
          <p className="lead">행사 정보로 모임 이름·시간·소개 초안을 써 줘요. 고칠 곳은 고치고, 마지막 확인은 사람이 해요.</p>
        </div>
      </div>

      <div className="draft-layout">
        <aside className="panel">
          <p className="small muted">고른 행사</p>
          <h3>{activity.title}</h3>
          <p className="meta">📅 {fmtPeriod(activity)}</p>
          <p className="meta">📍 {activity.place ?? "장소 정보 없음"}</p>
          <p className="meta">💳 {fmtCost(activity)}</p>
          <a className="link" href="#draft">
            다른 행사 고르기
          </a>
        </aside>

        <div className="panel">
          {phase === "loading" && <StepLoader steps={STEPS} current={step} slow={demo === "slow"} onCancel={writeMyself} />}
          {phase === "error" && <ErrorBox kind={err} onRetry={() => generate(tone)} onFallback={writeMyself} fallbackLabel="빈 양식에 직접 쓰기" />}

          {(phase === "edit" || phase === "confirm") && (
            <>
              <div className="row tone">
                <span className="small muted">말투 바꿔 다시 쓰기</span>
                {TONES.map(([t, label]) => (
                  <button
                    key={t}
                    className={t === tone ? "chip-ex on" : "chip-ex"}
                    onClick={() => {
                      setTone(t);
                      generate(t);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="field">
                <span>
                  모임 이름 <Badge k="name" />
                </span>
                <input value={form.name} maxLength={60} onChange={(e) => set("name", e.target.value)} />
              </label>
              <div className="two">
                <label className="field">
                  <span>
                    만날 시간 <Badge k="meetAt" />
                  </span>
                  <input type="datetime-local" value={form.meetAt} onChange={(e) => set("meetAt", e.target.value)} />
                </label>
                <label className="field">
                  <span>
                    정원 <Badge k="capacity" />
                  </span>
                  <input type="number" min={4} max={20} value={form.capacity} onChange={(e) => set("capacity", Number(e.target.value))} />
                </label>
              </div>
              <label className="field">
                <span>
                  모이는 곳 <Badge k="place" />
                </span>
                <input value={form.place} maxLength={120} onChange={(e) => set("place", e.target.value)} />
              </label>
              <label className="field">
                <span>
                  소개 <Badge k="intro" />
                </span>
                <textarea rows={5} value={form.intro} maxLength={500} onChange={(e) => set("intro", e.target.value)} />
              </label>
              {(problems.length > 0 || outside) && (
                <ul className="problems">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                  {outside && <li>{outside}</li>}
                </ul>
              )}
              <p className="small muted">AI는 행사 이름·장소·가격처럼 받은 자료에 있는 사실만 써요. 소개 글의 약속(뒤풀이 등)은 꼭 직접 확인해 주세요.</p>
              <button className="btn" disabled={problems.length > 0} onClick={() => setPhase("confirm")}>
                확인하고 모임 만들기
              </button>
            </>
          )}

          {phase === "created" && (
            <div className="state ok-state">
              <div className="state-ico">🎉</div>
              <div>
                <h3>모임을 만들었어요 (시연)</h3>
                <p>프로토타입이라 실제로 저장하지는 않았어요. 실제 서비스에서는 여기서 POST /meetups 를 불러 모임을 만들고 내가 모임장으로 자동 참여해요.</p>
                <button className="btn-ghost" onClick={() => setPhase("edit")}>
                  다시 고치기
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {phase === "confirm" && (
        <div className="modal-bg" role="dialog" aria-modal="true" aria-label="모임 만들기 확인">
          <div className="modal">
            <h3>이대로 만들까요?</h3>
            <dl>
              <dt>이름</dt>
              <dd>{form.name}</dd>
              <dt>시간</dt>
              <dd>{form.meetAt.replace("T", " ")}</dd>
              <dt>장소</dt>
              <dd>{form.place}</dd>
              <dt>정원</dt>
              <dd>{form.capacity}명</dd>
            </dl>
            {aiFields.size > 0 && <p className="ignored">AI가 쓴 내용을 그대로 둔 칸이 {aiFields.size}개 있어요. 한 번 더 읽어 봐 주세요.</p>}
            <div className="row">
              <button className="btn" onClick={() => setPhase("created")}>
                네, 만들기
              </button>
              <button className="btn-ghost" onClick={() => setPhase("edit")}>
                더 고칠래요
              </button>
            </div>
          </div>
        </div>
      )}

      <Proto>프로토타입: 초안은 규칙으로 만든 시연용 문장이에요. 실제 서비스는 LLM이 초안을 쓰고, 사람이 확인해야만 저장해요.</Proto>
    </section>
  );
}

function Picker({ items }: { items: Activity[] }) {
  const [text, setText] = useState("");
  const list = useMemo(() => {
    const open = applyConditions(items, {});
    const t = text.trim();
    return (t ? open.filter((a) => a.title.includes(t) || a.place?.includes(t) || a.region?.includes(t)) : open).slice(0, 20);
  }, [items, text]);
  return (
    <section>
      <div className="hero">
        <div className="hero-card">
          <p className="eyebrow">모임 초안 · 03</p>
          <div className="band" />
          <h1>
            어떤 행사로 <em>모일까요?</em>
          </h1>
          <p className="lead">검색 결과에서 "모임 만들기"를 눌러도 되고, 여기서 골라도 돼요.</p>
          <div className="searchbar">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="행사 이름이나 지역으로 찾기" aria-label="행사 찾기" />
          </div>
        </div>
      </div>
      {list.length === 0 ? (
        <div className="state empty">
          <div className="state-ico">🔍</div>
          <div>
            <h3>‘{text}’와 맞는 행사가 없어요</h3>
            <p>다른 이름이나 구 이름으로 찾아보세요.</p>
          </div>
        </div>
      ) : (
        <ul className="pick">
          {list.map((a) => (
            <li key={a.activity_id}>
              <a href={`#draft-${a.activity_id}`}>
                <span className={`tag t-${a.activity_type}`}>{a.activity_type}</span>
                <b>{a.title}</b>
                <span className="muted small">
                  {a.region} · {fmtPeriod(a)}
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
