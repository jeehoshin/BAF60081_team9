(function () {
  const { api, UserStore, escapeHtml, fmtDate, fmtTime, typeStyle } = window.Gachi;
  const user = UserStore.get();
  const params = new URLSearchParams(location.search);
  let activeId = params.get("meetup") ? Number(params.get("meetup")) : null;
  let pollTimer = null;
  let lastMsgSig = "";
  let miniMap = null;

  const roomsEl = document.getElementById("rooms");
  const roomEl = document.getElementById("room");

  function avatar(name) {
    const palette = ["#1f5fd6", "#16a36a", "#e5832f", "#7b4fe0", "#d64f7a", "#0f8fa8"];
    let h = 0;
    for (const ch of name || "?") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const c = palette[h % palette.length];
    return `<span class="avatar" style="background:${c}">${escapeHtml((name || "?").slice(0, 1))}</span>`;
  }

  async function loadRooms() {
    if (!user) {
      roomsEl.innerHTML = `<p class="hint">닉네임으로 <a href="register.html">합류</a>하면 내 모임톡이 여기 모여요.</p>`;
      return [];
    }
    try {
      const rooms = await api(`/users/${user.user_id}/meetups`);
      roomsEl.innerHTML = rooms.length
        ? rooms
            .map((r) => {
              const s = typeStyle(r.activity.type);
              const last = r.last_message
                ? `${escapeHtml(r.last_message.nickname)}: ${escapeHtml(r.last_message.body)}`
                : "아직 대화가 없어요";
              return `
                <a class="room-item ${r.meetup_id === activeId ? "on" : ""}" href="talk.html?meetup=${r.meetup_id}" data-room="${r.meetup_id}">
                  <span class="room-emoji" style="background:${s.color}">${s.emoji}</span>
                  <span class="room-body">
                    <b>${escapeHtml(r.name)}</b>
                    <small>${last}</small>
                  </span>
                  <span class="room-meta">${r.who.count}/${r.who.capacity}</span>
                </a>`;
            })
            .join("")
        : `<p class="hint">참여한 모임이 없어요. <a href="map.html">지도</a>에서 골라보세요!</p>`;
      return rooms;
    } catch (e) {
      roomsEl.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
      return [];
    }
  }

  function renderMessages(msgs) {
    const box = document.getElementById("msgs");
    if (!box) return;
    const sig = msgs.map((m) => m.message_id).join(",");
    if (sig === lastMsgSig) return;
    lastMsgSig = sig;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;

    let lastDay = "";
    box.innerHTML = msgs.length
      ? msgs
          .map((m) => {
            const mine = user && m.user_id === user.user_id;
            const day = new Date(m.created_at).toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" });
            const sep = day !== lastDay ? `<div class="day-sep">${day}</div>` : "";
            lastDay = day;
            return `${sep}
              <div class="bubble-row ${mine ? "mine" : ""}">
                ${mine ? "" : avatar(m.nickname)}
                <div class="bubble-col">
                  ${mine ? "" : `<span class="who">${escapeHtml(m.nickname || "?")}</span>`}
                  <div class="bubble-line">
                    <div class="bubble">${escapeHtml(m.body)}</div>
                    <time>${fmtTime(m.created_at)}</time>
                  </div>
                </div>
              </div>`;
          })
          .join("")
      : `<div class="talk-hello">첫 인사를 남겨보세요 👋<br><span class="muted">“정문에서 봬요!” 같은 한 마디면 충분해요</span></div>`;
    if (nearBottom || !renderMessages.scrolled) {
      box.scrollTop = box.scrollHeight;
      renderMessages.scrolled = true;
    }
  }

  async function pollMessages() {
    if (!activeId) return;
    try {
      renderMessages(await api(`/meetups/${activeId}/messages`));
    } catch (e) {
      /* 일시적 오류는 다음 폴링에서 재시도 */
    }
  }

  async function openRoom(id) {
    activeId = id;
    lastMsgSig = "";
    renderMessages.scrolled = false;
    if (pollTimer) clearInterval(pollTimer);

    let card;
    try {
      card = await api(`/meetups/${id}/card`);
    } catch (e) {
      roomEl.innerHTML = `<p class="status err">${escapeHtml(e.message)}</p>`;
      return;
    }
    const s = typeStyle(card.activity.type);
    const joined = user && card.who.members.includes(user.nickname);
    const full = card.who.count >= card.who.capacity;

    roomEl.innerHTML = `
      <header class="room-head" style="--c:${s.color}">
        <div class="room-title">
          <span class="type-tag">${s.emoji} ${escapeHtml(card.activity.type)}</span>
          <h2>${escapeHtml(card.name)}</h2>
          <span class="muted">${escapeHtml(card.activity.title)}</span>
        </div>
        <div class="room-info">
          <dl class="w4">
            <dt>누가</dt><dd>${card.who.members.map((n) => `<span class="pill">${escapeHtml(n)}${n === card.who.host ? " 👑" : ""}</span>`).join(" ")} <span class="muted">${card.who.count}/${card.who.capacity}</span></dd>
            <dt>언제</dt><dd>${fmtDate(card.when)}</dd>
            <dt>어디서</dt><dd>${escapeHtml(card.where.place_name || "장소 미정")}</dd>
            <dt>어떻게</dt><dd>${escapeHtml(card.how || "자유롭게")}</dd>
          </dl>
          <div id="miniMap" class="mini-map"></div>
        </div>
      </header>
      <div class="msgs" id="msgs"></div>
      ${
        joined
          ? `<form class="composer" id="composer">
               <div class="quick">
                 <button type="button" class="q">지금 출발해요 🏃</button>
                 <button type="button" class="q">도착했어요 📍</button>
                 <button type="button" class="q">5분 늦어요 🙏</button>
                 <button type="button" class="q">튀소 사갈게요 🥖</button>
               </div>
               <div class="composer-row">
                 <input name="body" maxlength="280" autocomplete="off" placeholder="메시지 입력…" required>
                 <button type="submit">보내기</button>
               </div>
             </form>`
          : `<div class="join-bar">
               <span>${full ? "정원이 다 찼어요" : "참여하면 대화에 들어갈 수 있어요"}</span>
               ${full ? "" : `<button type="button" id="joinBtn" class="bun">같이 갈래!</button>`}
             </div>`
      }`;

    if (miniMap) {
      miniMap.remove();
      miniMap = null;
    }
    if (card.where.lat != null && window.L) {
      miniMap = L.map("miniMap", { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false })
        .setView([card.where.lat, card.where.lng], 16);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(miniMap);
      L.circleMarker([card.where.lat, card.where.lng], { radius: 9, color: s.color, weight: 3, fillOpacity: 0.6 }).addTo(miniMap);
      miniMap.on("click", () => (location.href = "map.html"));
    } else {
      document.getElementById("miniMap").remove();
    }

    const composer = document.getElementById("composer");
    if (composer) {
      const input = composer.querySelector("input");
      const send = async (body) => {
        body = body.trim();
        if (!body) return;
        try {
          await api(`/meetups/${id}/messages`, {
            method: "POST",
            body: JSON.stringify({ user_id: user.user_id, body }),
          });
          input.value = "";
          await pollMessages();
          document.getElementById("msgs").scrollTop = 1e9;
          loadRooms();
        } catch (e) {
          alert(e.message);
        }
      };
      composer.addEventListener("submit", (e) => {
        e.preventDefault();
        send(input.value);
      });
      composer.querySelectorAll(".q").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
      input.focus();
    }

    const joinBtn = document.getElementById("joinBtn");
    if (joinBtn) {
      joinBtn.onclick = async () => {
        if (!user) return (location.href = "register.html");
        try {
          await api(`/meetups/${id}/participants`, { method: "POST", body: JSON.stringify({ user_id: user.user_id }) });
          await api(`/meetups/${id}/messages`, {
            method: "POST",
            body: JSON.stringify({ user_id: user.user_id, body: "저도 같이 갈래요! 🙌" }),
          });
          await loadRooms();
          openRoom(id);
        } catch (e) {
          alert(e.message);
        }
      };
    }

    await pollMessages();
    pollTimer = setInterval(pollMessages, 2000);
    document.querySelectorAll(".room-item").forEach((a) => a.classList.toggle("on", Number(a.dataset.room) === id));
  }

  roomsEl.addEventListener("click", (e) => {
    const a = e.target.closest("[data-room]");
    if (!a) return;
    e.preventDefault();
    const id = Number(a.dataset.room);
    history.replaceState(null, "", `talk.html?meetup=${id}`);
    openRoom(id);
  });

  (async () => {
    const rooms = await loadRooms();
    if (!activeId && rooms.length) activeId = rooms[0].meetup_id;
    if (activeId) openRoom(activeId);
    setInterval(loadRooms, 6000);
  })();
})();
