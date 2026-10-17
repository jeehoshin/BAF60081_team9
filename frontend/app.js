// 페이지 스크립트가 `const { api } = window.Gachi`로 꺼내 쓰므로 전역에 이름을 남기지 않는다
(function () {
const API = () => (window.APP_CONFIG?.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const UserStore = {
  key: "gachi-galae-user",
  get() {
    try {
      return JSON.parse(localStorage.getItem(this.key) || "null");
    } catch {
      return null;
    }
  },
  set(user) {
    localStorage.setItem(this.key, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(this.key);
  },
};

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };
  // GET에 Content-Type을 붙이면 CORS preflight가 발생해 로컬에서 멈출 수 있음
  if (method !== "GET" && method !== "HEAD" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API()}${path}`, {
    ...options,
    method,
    headers,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = data?.detail || data || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setStatus(el, message, ok = true) {
  if (!el) return;
  el.textContent = message;
  el.className = `status ${ok ? "ok" : "err"}`;
}

function requireUser(redirect = "register.html") {
  const user = UserStore.get();
  if (!user) {
    location.href = redirect;
    return null;
  }
  return user;
}

function renderUserBox(selector = "#userBox") {
  const el = document.querySelector(selector);
  if (!el) return;
  const user = UserStore.get();
  if (!user) {
    el.innerHTML = `아직 합류하지 않았어요. <a href="register.html">닉네임으로 합류</a> · <a href="qr.html">QR</a>`;
    return;
  }
  // 참여자 목록과 같은 "30대(여)" 형식으로 내 정보를 보여준다
  const me = fmtPerson(user).replace(`${user.nickname} · `, "");
  el.innerHTML = `
    <span>접속 중: <strong>${escapeHtml(user.nickname)}</strong>
    <span class="muted">(id ${user.user_id} · ${escapeHtml(me)})</span></span>
    <a href="register.html" class="muted">내 정보 수정</a>
    <button type="button" class="secondary" id="logoutBtn">로그아웃</button>
  `;
  el.querySelector("#logoutBtn")?.addEventListener("click", () => {
    UserStore.clear();
    location.reload();
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtDate(iso) {
  if (!iso) return "일정 미정";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDay(d) {
  return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric", weekday: "short" });
}

// 공공 API 행사는 날짜만 있고(00:00 시작), 기간이 있다. 예: "10월 14일 (수) ~ 10월 17일 (토)"
function fmtPeriod(startIso, endIso) {
  if (!startIso) return "일정 미정";
  const s = new Date(startIso);
  if (Number.isNaN(s.getTime())) return startIso;
  const e = endIso ? new Date(endIso) : null;
  const allDay = s.getHours() === 0 && s.getMinutes() === 0;
  if (!e || Number.isNaN(e.getTime()) || e.toDateString() === s.toDateString()) {
    return allDay ? fmtDay(s) : fmtDate(startIso);
  }
  return `${fmtDay(s)} ~ ${fmtDay(e)}`;
}

// http(s) 주소만 링크·이미지로 쓴다
function safeUrl(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : "";
}

const NAV_ITEMS = [
  ["home", "index.html", "활동"],
  ["map", "map.html", "지도"],
  ["talk", "talk.html", "모임톡"],
  ["create", "create.html", "활동 올리기"],
  ["stats", "stats.html", "분석"],
  ["live", "live.html", "라이브"],
  ["qr", "qr.html", "QR"],
  ["register", "register.html", "합류"],
];

function renderNav() {
  document.querySelectorAll("nav.topnav[data-active]").forEach((nav) => {
    const active = nav.dataset.active;
    nav.innerHTML =
      `<a class="brand" href="index.html"><img class="brand-mascot" data-mascot src="mascot.svg" alt="">같이 <span>갈래?</span></a>` +
      NAV_ITEMS.map(
        ([key, href, label]) => `<a href="${href}"${key === active ? ' class="active"' : ""}>${label}</a>`
      ).join("");
  });
}

// assets/nubzuki.png(공식 이미지)를 넣으면 SVG 대신 자동으로 사용
function applyMascot() {
  const probe = new Image();
  probe.onload = () => {
    document.querySelectorAll("img[data-mascot]").forEach((img) => {
      img.src = "assets/nubzuki.png";
    });
  };
  probe.src = "assets/nubzuki.png";
}

const TYPE_STYLE = {
  러닝: { color: "#16a36a", emoji: "🏃" },
  공연: { color: "#7b4fe0", emoji: "🎵" },
  축제: { color: "#e5832f", emoji: "🎉" },
  전시: { color: "#1f5fd6", emoji: "🖼️" },
};

function typeStyle(type) {
  return TYPE_STYLE[type] || { color: "#5d6b86", emoji: "📍" };
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function fmtPerson(p) {
  const name = p?.nickname || (p?.user_id ? `user${p.user_id}` : "?");
  const age = p?.age_group && p.age_group !== "선택 안 함" ? p.age_group : "";
  const gen = p?.gender && p.gender !== "선택 안 함" ? p.gender : "";
  if (age && gen) return `${name} · ${age}(${gen})`;
  if (age) return `${name} · ${age}`;
  if (gen) return `${name} · (${gen})`;
  return `${name} · 정보 비공개`;
}

// "선택 안 함"·"무관"·빈 값은 입력 안 한 것으로 본다
function cleanChoice(v) {
  return v && v !== "선택 안 함" && v !== "무관" ? v : "";
}

function genderLabel(g) {
  return g === "여" ? "여성" : g === "남" ? "남성" : g;
}

// 모임 참여 가능 여부. 서버(POST /meetups/{id}/participants)와 같은 규칙으로 미리 판정해
// 화면에서 회색 카드·사유를 보여준다. m은 /activities의 모임(MeetupOut)과 /map의 카드 둘 다 받는다.
function meetupState(m, user, joined = false) {
  const count = m.participant_count ?? m.who?.count ?? 0;
  const capacity = m.capacity ?? m.who?.capacity ?? 0;
  if (joined) return { state: "joined", disabled: false, reason: "" };
  if (capacity && count >= capacity) return { state: "full", disabled: true, reason: "정원이 마감되었어요" };
  const g = cleanChoice(m.gender_filter);
  const a = cleanChoice(m.age_filter);
  if (!g && !a) return { state: "ok", disabled: false, reason: "" };
  if (!user) {
    return { state: "need_login", disabled: false, reason: "참여 조건이 있는 모임이에요. 합류할 때 연령대·성별을 입력하면 참여할 수 있어요" };
  }
  const userGender = cleanChoice(user.gender);
  const userAge = cleanChoice(user.age_group);
  if ((g && !userGender) || (a && !userAge)) {
    return { state: "missing_info", disabled: true, reason: "참여 조건이 있는 모임이에요. 연령대·성별을 입력해 주세요" };
  }
  if (g && userGender !== g) {
    return { state: "gender_mismatch", disabled: true, reason: `이 모임은 ${genderLabel(g)}만 참여할 수 있어요` };
  }
  if (a && userAge !== a) {
    return { state: "age_mismatch", disabled: true, reason: `이 모임은 ${a}만 참여할 수 있어요` };
  }
  return { state: "ok", disabled: false, reason: "" };
}

// 모임을 열 때 호스트도 자기 조건을 충족해야 한다(서버도 같은 규칙으로 거절). 문제 없으면 "".
function hostFilterProblem(user, genderFilter, ageFilter) {
  const g = cleanChoice(genderFilter);
  const a = cleanChoice(ageFilter);
  if (g && cleanChoice(user?.gender) !== g) {
    return `호스트도 조건을 충족해야 해요. '${genderLabel(g)}만' 모임을 열려면 내 성별이 '${g}'로 등록되어 있어야 합니다.`;
  }
  if (a && cleanChoice(user?.age_group) !== a) {
    return `호스트도 조건을 충족해야 해요. '${a}만' 모임을 열려면 내 연령대가 '${a}'로 등록되어 있어야 합니다.`;
  }
  return "";
}

// 모임 조건 배지 HTML. 조건이 없으면 "조건 무관"(showNone=true일 때)
function condBadges(m, showNone = false) {
  const g = cleanChoice(m.gender_filter);
  const a = cleanChoice(m.age_filter);
  const out = [];
  if (g) out.push(`<span class="pill warn">${escapeHtml(genderLabel(g))}만</span>`);
  if (a) out.push(`<span class="pill warn">${escapeHtml(a)}만</span>`);
  if (!out.length && showNone) out.push(`<span class="pill">조건 무관</span>`);
  return out.join("");
}

// 참여 불가 사유 HTML. 정보 미입력이면 바로 고칠 수 있는 링크를 붙인다.
function reasonNote(ev) {
  if (!ev?.reason) return "";
  const fix = ev.state === "missing_info" ? ` <a href="register.html">내 정보 입력하기</a>` : "";
  return `<p class="reason-note">🔒 ${escapeHtml(ev.reason)}${fix}</p>`;
}

document.addEventListener("DOMContentLoaded", () => {
  renderNav();
  applyMascot();
});

window.Gachi = {
  api, API, UserStore, setStatus, requireUser, renderUserBox, escapeHtml, fmtDate, fmtTime,
  fmtPeriod, fmtPerson, safeUrl, typeStyle, renderNav, applyMascot,
  cleanChoice, genderLabel, meetupState, hostFilterProblem, condBadges, reasonNote,
};
})();
