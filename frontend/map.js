(function () {
  const { api, UserStore, renderUserBox, setStatus, escapeHtml, fmtDate, typeStyle,
    meetupState, hostFilterProblem, condBadges, reasonNote } = window.Gachi;
  const KAIST = [36.3700, 127.3620];

  renderUserBox();

  const map = L.map("map", { zoomControl: true }).setView(KAIST, 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const layer = L.layerGroup().addTo(map);
  const markers = new Map();
  let currentType = "";
  let cards = [];
  let picked = null;
  let pickMarker = null;

  function pinIcon(card) {
    const s = typeStyle(card.activity.type);
    const full = card.who.count >= card.who.capacity;
    return L.divIcon({
      className: "pin-wrap",
      html: `<div class="pin" style="--c:${s.color}">
               <div class="pin-inner"><span>${s.emoji}</span><b>${card.who.count}/${card.who.capacity}</b></div>
             </div>${full ? '<i class="pin-full">마감</i>' : ""}`,
      iconSize: [54, 60],
      iconAnchor: [27, 56],
      popupAnchor: [0, -50],
    });
  }

  function whoLine(card) {
    const details = card.who.member_details || [];
    if (details.length) {
      return details.map((d) => escapeHtml(window.Gachi.fmtPerson ? window.Gachi.fmtPerson(d) : d.nickname)).join(", ");
    }
    const members = card.who.members.map((n) => escapeHtml(n));
    return members.length ? members.join(", ") : "아직 없음";
  }

  // 내가 이미 들어간 모임인지 (member_details 또는 닉네임 목록으로 판단)
  function isJoined(card, user) {
    if (!user) return false;
    const details = card.who.member_details || [];
    return details.some((d) => d.user_id === user.user_id) || card.who.members.includes(user.nickname);
  }

  function cardHtml(card, compact = false) {
    const s = typeStyle(card.activity.type);
    const user = UserStore.get();
    const ev = meetupState(card, user, isJoined(card, user));
    let joinBtn;
    if (ev.state === "joined") {
      joinBtn = `<span class="pill">참여 중</span>`;
    } else if (ev.state === "full") {
      joinBtn = `<button type="button" disabled>마감</button>`;
    } else if (ev.disabled) {
      joinBtn = `<button type="button" disabled>참여 불가</button>`;
    } else {
      joinBtn = `<button type="button" data-join="${card.meetup_id}">같이 갈래!</button>`;
    }
    return `
      <div class="m-card ${compact ? "compact" : ""} ${ev.disabled ? "disabled-card" : ""}" style="--c:${s.color}">
        <div class="m-top">
          <span class="type-tag">${s.emoji} ${escapeHtml(card.activity.type)}</span>
          ${condBadges(card)}
          <span class="muted">${escapeHtml(card.activity.title)}</span>
        </div>
        <h3>${escapeHtml(card.name)}</h3>
        <dl class="w4">
          <dt>누가</dt><dd><b>${escapeHtml(card.who.host || "?")}</b> 호스트 · ${whoLine(card)} <span class="muted">(${card.who.count}/${card.who.capacity})</span></dd>
          <dt>언제</dt><dd>${fmtDate(card.when)}</dd>
          <dt>어디서</dt><dd>${escapeHtml(card.where.place_name || "장소 미정")}</dd>
          <dt>어떻게</dt><dd>${escapeHtml(card.how || "자유롭게")}</dd>
        </dl>
        ${reasonNote(ev)}
        <div class="actions">
          ${joinBtn}
          <a href="talk.html?meetup=${card.meetup_id}"><button type="button" class="secondary">💬 모임톡 ${card.message_count || ""}</button></a>
        </div>
      </div>`;
  }

  function render() {
    layer.clearLayers();
    markers.clear();
    const list = document.getElementById("timeline");
    document.getElementById("count").textContent = `${cards.length}개`;

    const withPos = [];
    cards.forEach((card) => {
      if (card.where.lat == null || card.where.lng == null) return;
      const m = L.marker([card.where.lat, card.where.lng], { icon: pinIcon(card) })
        .bindPopup(cardHtml(card, true), { maxWidth: 300, className: "m-popup" });
      m.addTo(layer);
      markers.set(card.meetup_id, m);
      withPos.push([card.where.lat, card.where.lng]);
    });

    let lastDay = "";
    list.innerHTML = cards.length
      ? cards
          .map((card) => {
            const d = card.when ? new Date(card.when) : null;
            const day = d ? d.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" }) : "날짜 미정";
            const header = day !== lastDay ? `<div class="day-sep">${day}</div>` : "";
            lastDay = day;
            return `${header}<div class="tl-item" data-focus="${card.meetup_id}">${cardHtml(card)}</div>`;
          })
          .join("")
      : `<p class="hint">이 조건의 모임이 아직 없어요. 지도를 눌러 첫 모임을 열어보세요!</p>`;

    if (withPos.length && !render.fitted) {
      map.fitBounds(withPos, { padding: [40, 40], maxZoom: 15 });
      render.fitted = true;
    }
  }

  async function load() {
    const qs = currentType ? `?type=${encodeURIComponent(currentType)}` : "";
    try {
      const next = await api(`/map/meetups${qs}`);
      const sig = JSON.stringify(next);
      if (sig === load.lastSig) return;
      load.lastSig = sig;
      cards = next;
      render();
    } catch (e) {
      document.getElementById("timeline").innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
    }
  }

  async function join(meetupId) {
    const user = UserStore.get();
    if (!user) return (location.href = "register.html");
    try {
      await api(`/meetups/${meetupId}/participants`, {
        method: "POST",
        body: JSON.stringify({ user_id: user.user_id }),
      });
      location.href = `talk.html?meetup=${meetupId}`;
    } catch (e) {
      alert(e.message);
    }
  }

  document.addEventListener("click", (e) => {
    const joinBtn = e.target.closest("[data-join]");
    if (joinBtn) {
      e.stopPropagation();
      join(Number(joinBtn.dataset.join));
      return;
    }
    const item = e.target.closest("[data-focus]");
    if (item && !e.target.closest("a,button")) {
      const m = markers.get(Number(item.dataset.focus));
      if (m) {
        map.flyTo(m.getLatLng(), 17, { duration: 0.6 });
        m.openPopup();
      }
    }
  });

  document.getElementById("typeFilter").addEventListener("click", (e) => {
    const b = e.target.closest("[data-type]");
    if (!b) return;
    document.querySelectorAll("#typeFilter .chip-btn").forEach((x) => x.classList.toggle("on", x === b));
    currentType = b.dataset.type;
    render.fitted = false;
    load.lastSig = null;
    load();
  });

  // 지도 클릭 → 그 자리에서 모임 개설
  const dlg = document.getElementById("createDlg");
  map.on("click", async (e) => {
    if (!UserStore.get()) {
      if (confirm("모임을 열려면 먼저 닉네임으로 합류해야 해요. 합류하러 갈까요?")) location.href = "register.html";
      return;
    }
    picked = e.latlng;
    if (pickMarker) pickMarker.remove();
    pickMarker = L.circleMarker(picked, { radius: 10, color: "#e09b2f", weight: 3, fillOpacity: 0.4 }).addTo(map);
    document.getElementById("pickedPos").textContent = `📍 선택한 위치 ${picked.lat.toFixed(4)}, ${picked.lng.toFixed(4)}`;

    const sel = document.getElementById("activitySelect");
    try {
      const acts = await api("/activities");
      sel.innerHTML = acts
        .map((a) => `<option value="${a.activity_id}">${typeStyle(a.activity_type).emoji} ${escapeHtml(a.title)}</option>`)
        .join("");
    } catch (err) {
      sel.innerHTML = `<option value="">활동을 불러오지 못했어요</option>`;
    }
    const t = new Date(Date.now() + 2 * 3600 * 1000);
    t.setMinutes(0, 0, 0);
    const pad = (n) => String(n).padStart(2, "0");
    dlg.querySelector("[name=meet_at]").value =
      `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}T${pad(t.getHours())}:00`;
    setStatus(document.getElementById("createStatus"), "", true);
    dlg.showModal();
  });

  document.getElementById("cancelCreate").onclick = () => {
    dlg.close();
    if (pickMarker) pickMarker.remove();
  };

  document.getElementById("createForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const user = UserStore.get();
    const fd = new FormData(e.target);
    const payload = {
      activity_id: Number(fd.get("activity_id")),
      host_id: user.user_id,
      name: fd.get("name"),
      place_name: fd.get("place_name"),
      capacity: Number(fd.get("capacity") || 4),
      how: fd.get("how") || null,
      gender_filter: fd.get("gender_filter") || null,
      age_filter: fd.get("age_filter") || null,
      lat: picked.lat,
      lng: picked.lng,
      meet_at: fd.get("meet_at"),
    };
    // 호스트가 자기 조건을 못 맞추면 서버가 거절하므로 보내기 전에 알려준다
    const hostProblem = hostFilterProblem(user, payload.gender_filter, payload.age_filter);
    if (hostProblem) {
      setStatus(document.getElementById("createStatus"), hostProblem, false);
      return;
    }
    try {
      const m = await api("/meetups", { method: "POST", body: JSON.stringify(payload) });
      dlg.close();
      if (pickMarker) pickMarker.remove();
      e.target.reset();
      location.href = `talk.html?meetup=${m.meetup_id}`;
    } catch (err) {
      setStatus(document.getElementById("createStatus"), err.message, false);
    }
  });

  load();
  setInterval(load, 8000);
})();
