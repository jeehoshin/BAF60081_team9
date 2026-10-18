(function () {
  function boot() {
    const { api, renderUserBox, setStatus, escapeHtml, fmtPeriod } = window.Gachi;
    renderUserBox();
    let datePreset = "";

    function toIsoLocal(d, endOfDay = false) {
      const pad = (n) => String(n).padStart(2, "0");
      const y = d.getFullYear();
      const m = pad(d.getMonth() + 1);
      const day = pad(d.getDate());
      return `${y}-${m}-${day}T${endOfDay ? "23:59:59" : "00:00:00"}`;
    }

    function calcDateRange(preset) {
      if (!preset) return null;
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const dow = today.getDay(); // 0=일, 6=토
      if (preset === "today") {
        return { from: toIsoLocal(today, false), to: toIsoLocal(today, true) };
      }
      if (preset === "weekend") {
        const sat = new Date(today);
        const sun = new Date(today);
        if (dow === 0) {
          // 일요일이면 오늘 하루가 이번 주말의 남은 날
          sat.setDate(today.getDate() - 1);
        } else {
          sat.setDate(today.getDate() + (6 - dow));
          sun.setDate(sat.getDate() + 1);
        }
        return { from: toIsoLocal(sat, false), to: toIsoLocal(sun, true) };
      }
      if (preset === "nextweek") {
        const daysUntilNextMon = dow === 0 ? 1 : 8 - dow;
        const mon = new Date(today);
        mon.setDate(today.getDate() + daysUntilNextMon);
        const sun = new Date(mon);
        sun.setDate(mon.getDate() + 6);
        return { from: toIsoLocal(mon, false), to: toIsoLocal(sun, true) };
      }
      return null;
    }

    // 마지막 날(ends_at, 없으면 starts_at — 러닝처럼 하루짜리) 기준으로 "종료" / "마감 임박(2주 이내)" 판정
    function dateBadge(a) {
      const last = a.ends_at || a.starts_at;
      if (!last) return "";
      const e = new Date(last);
      if (Number.isNaN(e.getTime())) return "";
      // 날짜만 있는 공공 API 행사(00:00)는 그날 하루가 끝날 때까지 진행 중으로 본다
      if (e.getHours() === 0 && e.getMinutes() === 0) e.setHours(23, 59, 59, 999);
      const diffDays = (e.getTime() - Date.now()) / (1000 * 3600 * 24);
      if (diffDays < 0) return `<span class="pill">종료</span>`;
      if (diffDays <= 14) return `<span class="pill danger">마감 임박</span>`;
      return "";
    }

    // 상설·장기 행사(기간 90일 초과)는 '상설'로 구분하고, 진행 중이어도 "곧 시작하는 행사" 뒤로 보낸다.
    // 서버는 진행 중인 행사를 모두 앞에 두기 때문에, 이렇게 하지 않으면 상설 전시가 이번 주말에 새로 시작하는 행사를 가린다.
    // 끝난 행사는 서버 순서대로 맨 뒤에 둔다.
    const LONG_RUN_DAYS = 90;
    function isLongRun(a) {
      if (!a.starts_at || !a.ends_at) return false;
      const s = new Date(a.starts_at);
      const e = new Date(a.ends_at);
      if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return false;
      return (e.getTime() - s.getTime()) / 86400000 > LONG_RUN_DAYS;
    }
    function isOver(a) {
      return dateBadge(a).includes("종료");
    }
    function longRunLast(rows) {
      const over = rows.filter(isOver);
      const live = rows.filter((a) => !isOver(a));
      return [...live.filter((a) => !isLongRun(a)), ...live.filter(isLongRun), ...over];
    }

    function fmtSource(src) {
      if (src === "user") return "사용자 등록";
      return src || "";
    }

    async function load() {
      const regionSel = document.getElementById("region");
      const region = regionSel.value;
      // 고른 항목의 도시(data-city). '중구'처럼 두 도시에 다 있는 구와 '서울 전체/대전 전체'를 구분한다
      const city = regionSel.selectedOptions[0]?.dataset.city || "";
      const type = document.getElementById("type").value;
      const qs = new URLSearchParams();
      if (region) qs.set("region", region);
      if (city) qs.set("city", city);
      if (type) qs.set("type", type);
      const range = calcDateRange(datePreset);
      if (range) {
        qs.set("date_from", range.from);
        qs.set("date_to", range.to);
      }
      const status = document.getElementById("listStatus");
      const list = document.getElementById("list");
      try {
        const rows = longRunLast(await api(`/activities?${qs}`));
        setStatus(status, `${rows.length}개 활동`, true);
        list.innerHTML =
          rows
            .map(
              (a) => {
                const badge = dateBadge(a);
                return `
          <article class="card ${badge.includes("종료") ? "disabled-card" : ""}">
            <div style="display:flex;flex-wrap:wrap;gap:6px">
              <span class="pill">${escapeHtml(a.activity_type)}</span>
              <span class="pill warn">${escapeHtml(fmtSource(a.source))}</span>
              ${isLongRun(a) ? `<span class="pill">상설</span>` : ""}
              ${badge}
            </div>
            <h3>${escapeHtml(a.title)}</h3>
            <div class="meta">
              <span>${escapeHtml(a.region || "지역 미상")}</span>
              <span>${escapeHtml(a.place || "")}</span>
              <span>${fmtPeriod(a.starts_at, a.ends_at)}</span>
              <span>${escapeHtml(a.cost || "")}</span>
            </div>
            <p class="hint" style="margin:0">${escapeHtml(a.description || "")}</p>
            <div class="actions">
              <a href="activity.html?id=${a.activity_id}"><button type="button">상세·모임</button></a>
            </div>
          </article>`;
              }
            )
            .join("") || `<p class="hint">조건에 맞는 활동이 없습니다.</p>`;
      } catch (e) {
        setStatus(status, `API 연결 실패: ${e.message}`, false);
        list.innerHTML =
          `<p class="hint">백엔드가 켜져 있는지, config.js의 API_BASE_URL을 확인하세요.</p>`;
      }
    }

    document.getElementById("searchBtn").addEventListener("click", load);
    document.getElementById("region").addEventListener("change", load);
    document.getElementById("type").addEventListener("change", load);
    const dateFilter = document.getElementById("dateFilter");
    if (dateFilter) {
      dateFilter.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-date]");
        if (!btn) return;
        dateFilter.querySelectorAll(".chip-btn").forEach((b) => b.classList.toggle("on", b === btn));
        datePreset = btn.dataset.date || "";
        load();
      });
    }
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
