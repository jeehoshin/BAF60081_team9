(function () {
  function boot() {
    const { api, renderUserBox, setStatus, escapeHtml, fmtDate } = window.Gachi;
    renderUserBox();

    async function load() {
      const region = document.getElementById("region").value;
      const type = document.getElementById("type").value;
      const qs = new URLSearchParams();
      if (region) qs.set("region", region);
      if (type) qs.set("type", type);
      const status = document.getElementById("listStatus");
      const list = document.getElementById("list");
      try {
        const rows = await api(`/activities?${qs}`);
        setStatus(status, `${rows.length}개 활동`, true);
        list.innerHTML =
          rows
            .map(
              (a) => `
          <article class="card">
            <div><span class="pill">${escapeHtml(a.activity_type)}</span>
              <span class="pill warn">${escapeHtml(a.source)}</span></div>
            <h3>${escapeHtml(a.title)}</h3>
            <div class="meta">
              <span>${escapeHtml(a.region || "지역 미상")}</span>
              <span>${escapeHtml(a.place || "")}</span>
              <span>${fmtDate(a.starts_at)}</span>
              <span>${escapeHtml(a.cost || "")}</span>
            </div>
            <p class="hint" style="margin:0">${escapeHtml(a.description || "")}</p>
            <div class="actions">
              <a href="activity.html?id=${a.activity_id}"><button type="button">상세·모임</button></a>
            </div>
          </article>`
            )
            .join("") || `<p class="hint">조건에 맞는 활동이 없습니다.</p>`;
      } catch (e) {
        setStatus(status, `API 연결 실패: ${e.message}`, false);
        list.innerHTML =
          `<p class="hint">백엔드가 켜져 있는지, config.js의 API_BASE_URL을 확인하세요.</p>`;
      }
    }

    document.getElementById("searchBtn").addEventListener("click", load);
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
