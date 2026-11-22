import { useEffect, useState } from "react";
import type { Activity, DemoMode } from "./types";
import { loadActivities, type LoadResult } from "./data";
import Search from "./screens/Search";
import Ask from "./screens/Ask";
import Draft from "./screens/Draft";
import mascot from "./mascot.svg";

const TABS: [string, string][] = [
  ["search", "🔎 AI 검색"],
  ["ask", "🧭 AI 동행 플래너"],
  ["draft", "✍️ 모임 초안"],
];

const EXT_LINKS: [string, string, string][] = [
  ["https://baf60081team9-frontend.vercel.app/plan.html", "📋 5주차 발표 페이지", "팀 아이디어·설계 요약 페이지 (plan.html)"],
  ["https://baf60081team9-frontend.vercel.app/stats.html", "📊 데이터 분석", "공공 데이터·KOPIS 통계·품질 분석 페이지"],
  ["https://baf60081-team9.onrender.com/docs", "⚡ Swagger API", "FastAPI 백엔드 Swagger UI (/docs)"],
  ["https://baf60081team9-frontend.vercel.app/", "🏠 기존 서비스", "선행 과목 전체 서비스 홈"],
];

const DEMO_OPTS: [DemoMode, string][] = [
  ["normal", "정상"],
  ["slow", "느린 응답"],
  ["rate_limit", "요청 한도 초과 (429)"],
  ["server_down", "서버 연결 실패"],
  ["empty", "결과 없음"],
  ["unsure", "AI 확신 낮음"],
];

// 공유 페이지(Artifact)는 '#이름' 모양의 주소만 넘겨 주므로 '#draft-172'처럼 쓴다. 예전 모양 '#/draft?id=172'도 읽는다
function readHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const m = h.match(/^draft(?:-(\d+)|\?id=(\d+))?$/);
  if (m) return { tab: "draft", id: m[1] || m[2] ? Number(m[1] ?? m[2]) : null };
  const tab = h.split("?")[0];
  return { tab: TABS.some(([k]) => k === tab) ? tab : "search", id: null };
}

export default function App() {
  const [route, setRoute] = useState(readHash);
  const [data, setData] = useState<LoadResult | null>(null);
  const [demo, setDemo] = useState<DemoMode>("normal");
  const [panelOpen, setPanelOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      setRoute(readHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const reload = () => {
    setData(null);
    loadActivities().then(setData);
  };
  useEffect(reload, []);

  const toDraft = (a: Activity) => (location.hash = `#draft-${a.activity_id}`);

  return (
    <>
      <header className="top">
        <div className="top-in">
          <div className="brand-wrap">
            <a className="brand" href="#search">
              <img src={mascot} alt="" />
              같이 <span>갈래?</span>
              <small>AI 프로토타입</small>
            </a>
          </div>
          <nav className="tabs" aria-label="AI 주요 기능 화면">
            {TABS.map(([k, label]) => (
              <a key={k} href={`#${k}`} className={route.tab === k ? "on" : ""}>
                {label}
              </a>
            ))}
          </nav>
          <nav className="quick-links" aria-label="프로젝트 바로가기">
            {EXT_LINKS.map(([href, label, title]) => (
              <a key={href} href={href} target="_blank" rel="noreferrer" title={title} className="ext-pill">
                {label} ↗
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main className="wrap">
        {data && !data.live && (
          <div className="banner">
            실시간 서버에 연결하지 못해 저장본({data.savedAt})으로 보여 주고 있어요.
            <button className="link" onClick={reload}>
              다시 연결
            </button>
          </div>
        )}
        {!data ? (
          <div className="boot" role="status">
            <div className="spinner" />
            <p>공공 데이터 불러오는 중… 서버가 잠들어 있으면 최대 15초 걸려요.</p>
          </div>
        ) : route.tab === "ask" ? (
          <Ask items={data.items} demo={demo} onDraft={toDraft} />
        ) : route.tab === "draft" ? (
          <Draft key={route.id ?? "pick"} items={data.items} demo={demo} activityId={route.id} />
        ) : (
          <Search items={data.items} demo={demo} onDraft={toDraft} />
        )}
      </main>

      <footer className="foot">
        <div className="foot-links">
          {EXT_LINKS.map(([href, label]) => (
            <a key={href} href={href} target="_blank" rel="noreferrer">
              {label} ↗
            </a>
          ))}
          <a href="https://github.com/jeehoshin/BAF60081_team9" target="_blank" rel="noreferrer">
            💻 GitHub 저장소 ↗
          </a>
        </div>
        <div>
          데이터 출처: KOPIS 공연예술통합전산망((재)예술경영지원센터) · 한국관광공사 TourAPI · 한국문화정보원 한눈에보는문화정보 · BAF60086 1조 같이 갈래?
        </div>
      </footer>

      <div className={`demo ${panelOpen ? "open" : ""} ${demo !== "normal" ? "active" : ""}`}>
        <button className="demo-toggle" onClick={() => setPanelOpen((v) => !v)} aria-expanded={panelOpen}>
          🎬 시연 상태{demo !== "normal" ? ` · ${DEMO_OPTS.find(([k]) => k === demo)?.[1]}` : ""}
        </button>
        {panelOpen && (
          <div className="demo-body">
            <p className="small muted">발표용: 다음 AI 요청에 이 상태를 강제로 보여 줘요.</p>
            {DEMO_OPTS.map(([k, label]) => (
              <label key={k}>
                <input type="radio" name="demo" checked={demo === k} onChange={() => setDemo(k)} /> {label}
              </label>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
