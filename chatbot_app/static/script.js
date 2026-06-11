/* ============================================================
   Recomendador de Hoteles · Despegar NLP
   Vanilla JS — sin build step, sin dependencias.
   ============================================================ */

(() => {
  "use strict";

  // ----- Config -----
  // El frontend se sirve desde el mismo origen que la API (FastAPI en :8000),
  // así que usamos paths relativos. Cambiar a "http://localhost:8000" si se
  // sirve el HTML desde otro origen durante el desarrollo.
  const API_BASE = "";
  const ENDPOINT_CHAT = `${API_BASE}/chat`;
  const ENDPOINT_DESTINATIONS = `${API_BASE}/destinations`;
  const ENDPOINT_HEALTH = `${API_BASE}/health`;

  // ----- Despegar city GIDs (módulo 2 → links a despegar.com.ar) -----
  const CITY_GIDS = {
    "Argentina - Buenos Aires":              "CIT_982",
    "Argentina - Córdoba":                   "CIT_1445",
    "Argentina - El Calafate":               "CIT_2346",
    "Argentina - Mar Del Plata":             "CIT_4445",
    "Argentina - Mendoza":                   "CIT_4451",
    "Argentina - Puerto Iguazú":             "CIT_3071",
    "Argentina - Rosario":                   "CIT_6460",
    "Argentina - Salta":                     "CIT_6846",
    "Argentina - San Carlos De Bariloche":   "CIT_901",
    "Argentina - Ushuaia":                   "CIT_7781",
    "Argentina - Villa Carlos Paz":          "CIT_7848",
    "Brasil - Aracaju":                      "CIT_180",
    "Brasil - Arraial Do Cabo":              "CIT_8978",
    "Brasil - Arraial D´ajuda":              "CIT_339",
    "Brasil - Balneário Camboriú":           "CIT_192594",
    "Brasil - Belo Horizonte":               "CIT_701",
    "Brasil - Brasilia":                     "CIT_926",
    "Brasil - Búzios":                       "CIT_1077",
    "Brasil - Campos Do Jordão":             "CIT_6116",
    "Brasil - Curitiba":                     "CIT_1595",
    "Brasil - Florianópolis":                "CIT_2261",
    "Brasil - Fortaleza":                    "CIT_2302",
    "Brasil - Foz De Iguazú":               "CIT_3072",
    "Brasil - Gramado":                      "CIT_2611",
    "Brasil - Joao Pessoa":                  "CIT_3399",
    "Brasil - Maceió":                       "CIT_4430",
    "Brasil - Maragogi":                     "CIT_4499",
    "Brasil - Morro De San Pablo":           "CIT_4678",
    "Brasil - Natal":                        "CIT_4971",
    "Brasil - Peña":                         "CIT_9261",
    "Brasil - Porto Alegre":                 "CIT_5822",
    "Brasil - Porto De Galinhas":            "CIT_5648",
    "Brasil - Porto Seguro":                 "CIT_881",
    "Brasil - Praia Da Pipa":                "CIT_5875",
    "Brasil - Recife":                       "CIT_6322",
    "Brasil - Rio De Janeiro":               "CIT_6381",
    "Brasil - Salvador":                     "CIT_7018",
    "Brasil - San Pablo":                    "CIT_6574",
    "Brasil - Vitoria":                      "CIT_7907",
    "Chile - Iquique":                       "CIT_3176",
    "Chile - San Pedro De Atacama":          "CIT_394",
    "Chile - Santiago De Chile":             "CIT_6624",
    "Colombia - Bogotá":                     "CIT_854",
    "Colombia - Cartagena De Indias":        "CIT_1535",
    "Colombia - Medellín":                   "CIT_4434",
    "Colombia - San Andrés":                 "CIT_89",
    "Colombia - Santa Marta":                "CIT_6890",
    "Estados Unidos - Las Vegas":            "CIT_3944",
    "Estados Unidos - Miami Beach":          "CIT_31684",
    "Estados Unidos - Nueva York":           "CIT_5227",
    "Estados Unidos - Orlando":              "CIT_5419",
    "México - Acapulco":                     "CIT_49",
    "México - Cancún":                       "CIT_1569",
    "México - Ciudad De México":             "CIT_4474",
    "México - Guadalajara":                  "CIT_2442",
    "México - Mazatlán":                     "CIT_4948",
    "México - Monterrey":                    "CIT_4817",
    "México - Mérida":                       "CIT_4545",
    "México - Playa Del Carmen":             "CIT_5584",
    "México - Puerto Vallarta":              "CIT_5991",
    "México - Riviera Maya":                 "CIT_8934",
    "México - Veracruz":                     "CIT_7874",
    "Panamá - Panamá":                       "CIT_5950",
    "Perú - Cusco":                          "CIT_1579",
    "Perú - Lima":                           "CIT_4088",
    "República Dominicana - Punta Cana":     "CIT_5963",
    "Uruguay - Montevideo":                  "CIT_4844",
  };

  // ----- Atributos estructurados (módulo 2 de Franco) -----
  const ATTR_META = {
    wifi:               { emoji: "📶", label: "Wi-Fi" },
    vista:              { emoji: "🌅", label: "Vista" },
    ubicacion:          { emoji: "📍", label: "Ubicación" },
    ruido:              { emoji: "🔇", label: "Tranquilo" },
    limpieza:           { emoji: "🧼", label: "Limpieza" },
    desayuno:           { emoji: "🥐", label: "Desayuno" },
    personal:           { emoji: "👔", label: "Personal" },
    habitacion:         { emoji: "🛏️", label: "Habitación" },
    restaurante:        { emoji: "🍝", label: "Restaurante" },
    aire_acondicionado: { emoji: "❄️", label: "A/C" },
    transporte:         { emoji: "🚌", label: "Transporte" },
    estacionamiento:    { emoji: "🅿️", label: "Parking" },
    seguridad:          { emoji: "🛡️", label: "Seguridad" },
    checkin:            { emoji: "🛎️", label: "Check-in" },
  };

  function attrMeta(a) {
    return ATTR_META[a] || { emoji: "•", label: a };
  }

  function despegarUrl(destination, hotelName) {
    const gid = CITY_GIDS[destination];
    const today = new Date();
    const checkIn  = new Date(today.getTime() + 30 * 86400000);
    const checkOut = new Date(today.getTime() + 37 * 86400000);
    const fmt = (d) => d.toISOString().slice(0, 10);
    if (gid) {
      return `https://www.despegar.com.ar/accommodations/results/${gid}/${fmt(checkIn)}/${fmt(checkOut)}/2`;
    }
    return `https://www.google.com/search?q=${encodeURIComponent(hotelName + " despegar.com.ar")}`;
  }

  // ----- DOM refs -----
  const $ = (id) => document.getElementById(id);
  const chatScroll = $("chatScroll");
  const chatInner = $("chatInner");
  const welcome = $("welcome");
  const input = $("input");
  const sendBtn = $("sendBtn");
  const destList = $("destList");
  const destCount = $("destCount");
  const destStatCount = $("destStatCount");
  const destSearch = $("destSearch");
  const statusDot = $("statusDot");
  const statusText = $("statusText");

  // ----- State -----
  let isLoading = false;
  let destinations = [];

  // ============================================================
  // Init
  // ============================================================

  document.addEventListener("DOMContentLoaded", () => {
    bindComposer();
    bindDemoButtons();
    bindWelcomeTips();
    bindDestinationsSearch();
    autoResizeTextarea();
    checkHealth();
    loadDestinations();
  });

  // ============================================================
  // Health check (status pill)
  // ============================================================

  async function checkHealth() {
    try {
      const res = await fetch(ENDPOINT_HEALTH, { method: "GET" });
      if (!res.ok) throw new Error("not ok");
      statusDot.classList.remove("is-offline");
      statusText.textContent = "Servicio en línea";
    } catch {
      statusDot.classList.add("is-offline");
      statusText.textContent = "Servicio sin conexión";
    }
  }

  // ============================================================
  // Destinations
  // ============================================================

  async function loadDestinations() {
    try {
      const res = await fetch(ENDPOINT_DESTINATIONS);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      destinations = (data.destinations || []).filter(
        (d) => !String(d).startsWith("...")
      );
      renderDestinations(destinations);
      destCount.textContent = destinations.length;
      destStatCount.textContent = destinations.length;
    } catch (err) {
      destList.innerHTML =
        '<li class="dest-empty">No se pudo cargar la lista de destinos.</li>';
      console.warn("loadDestinations failed:", err);
    }
  }

  function renderDestinations(items) {
    if (!items.length) {
      destList.innerHTML =
        '<li class="dest-empty">Sin coincidencias.</li>';
      return;
    }
    destList.innerHTML = items
      .map((d) => {
        const [country, ...rest] = String(d).split(" - ");
        const city = rest.join(" - ") || country;
        const ctry = rest.length ? country : "";
        return `
          <li class="dest-item" title="${escapeHtml(d)}">
            <span class="dest-country">${escapeHtml(ctry.slice(0, 3).toUpperCase())}</span>
            <span class="dest-city">${escapeHtml(city)}</span>
          </li>`;
      })
      .join("");
  }

  function bindDestinationsSearch() {
    destSearch.addEventListener("input", () => {
      const q = destSearch.value.trim().toLowerCase();
      if (!q) {
        renderDestinations(destinations);
        return;
      }
      const filtered = destinations.filter((d) =>
        String(d).toLowerCase().includes(q)
      );
      renderDestinations(filtered);
    });
  }

  // ============================================================
  // Composer
  // ============================================================

  function bindComposer() {
    sendBtn.addEventListener("click", handleSend);

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    input.addEventListener("input", autoResizeTextarea);
  }

  function autoResizeTextarea() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  }

  function bindDemoButtons() {
    document.querySelectorAll(".demo-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.dataset.query || "";
        input.value = q;
        autoResizeTextarea();
        input.focus();
      });
    });
  }

  function bindWelcomeTips() {
    document.querySelectorAll(".welcome-tip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.dataset.query || "";
        input.value = q;
        autoResizeTextarea();
        // Tips disparan envío directamente para máxima fluidez
        handleSend();
      });
    });
  }

  // ============================================================
  // Send / receive
  // ============================================================

  async function handleSend() {
    if (isLoading) return;
    const message = input.value.trim();
    if (!message) return;

    // 1) limpiar empty state
    if (welcome && welcome.parentNode) welcome.remove();

    // 2) burbuja del usuario
    appendUserMessage(message);

    // 3) limpiar y bloquear input
    input.value = "";
    autoResizeTextarea();
    setLoading(true);

    // 4) indicador "pensando…"
    const thinking = appendThinking();
    scrollToBottom();

    try {
      const res = await fetch(ENDPOINT_CHAT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      thinking.remove();

      if (data.error) {
        appendBotError(data.error);
      } else {
        appendBotMessage(data);
      }
    } catch (err) {
      console.error(err);
      thinking.remove();
      appendBotError(
        "No pude conectarme al servicio. Verificá que el backend esté corriendo en http://localhost:8000 y volvé a intentar."
      );
    } finally {
      setLoading(false);
      scrollToBottom();
      input.focus();
    }
  }

  function setLoading(loading) {
    isLoading = loading;
    sendBtn.disabled = loading;
    input.disabled = loading;
  }

  // ============================================================
  // Rendering helpers
  // ============================================================

  function appendUserMessage(text) {
    const el = document.createElement("div");
    el.className = "msg user";
    el.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
    chatInner.appendChild(el);
    scrollToBottom();
  }

  function appendBotMessage(data) {
    const {
      response = "",
      hoteles = [],
      alternativas_semanticas = [],
      alternativas_estructuradas = [],
      destination = null,
      filtro = {},
    } = data;

    const wrapper = document.createElement("div");
    wrapper.className = "msg bot";

    const hasHotels = hoteles.length > 0;
    const hasAlt    = alternativas_semanticas.length > 0 || alternativas_estructuradas.length > 0;

    if (hasHotels || hasAlt) {
      const dest = destination ? escapeHtml(destination) : "";
      const intro = dest
        ? `<div class="bot-intro">📍 <strong>${dest}</strong> · ${hoteles.length} hoteles recomendados</div>`
        : "";
      const altSemHtml  = alternativas_semanticas.length
        ? renderAlternativas(alternativas_semanticas, "Alternativas semánticas", destination, filtro)
        : "";
      const altEstrHtml = alternativas_estructuradas.length
        ? renderAlternativas(alternativas_estructuradas, "Alternativas estructuradas", destination, filtro)
        : "";
      wrapper.innerHTML = `
        <div class="avatar" aria-hidden="true">D</div>
        <div class="bot-content">
          ${intro}
          ${hasHotels ? renderHotels(hoteles, destination, response, filtro) : ""}
          ${altSemHtml}
          ${altEstrHtml}
        </div>
      `;
    } else {
      wrapper.innerHTML = `
        <div class="avatar" aria-hidden="true">D</div>
        <div class="bot-content">
          <div class="bubble">${formatText(response)}</div>
        </div>
      `;
    }

    chatInner.appendChild(wrapper);
  }

  function appendBotError(text) {
    const el = document.createElement("div");
    el.className = "msg bot is-error";
    el.innerHTML = `
      <div class="avatar" aria-hidden="true">!</div>
      <div class="bot-content">
        <div class="bubble">${formatText(text)}</div>
      </div>
    `;
    chatInner.appendChild(el);
  }

  function extractHotelBlurb(response, hotelName) {
    if (!response || !hotelName) return "";

    // Split on blank lines OR on lines that start a new bullet/numbered item
    const chunks = response
      .split(/\n{2,}|\n(?=\s*(?:[*\-]|\d+[\.\)])\s)/)
      .map((c) => c.trim())
      .filter(Boolean);

    const nameLower = hotelName.toLowerCase().trim();
    const strip = (s) => s.replace(/^\s*(?:\d+[\.\)]|[*\-])\s*/, "").trim();

    // 1. Exact full-name match — only accept if this chunk is the UNIQUE best
    const exactMatches = chunks.filter((c) => c.toLowerCase().includes(nameLower));
    if (exactMatches.length === 1) return strip(exactMatches[0]);

    // 2. If multiple chunks contain the name (e.g. intro paragraph), pick the
    //    one where the name appears closest to the start
    if (exactMatches.length > 1) {
      exactMatches.sort(
        (a, b) => a.toLowerCase().indexOf(nameLower) - b.toLowerCase().indexOf(nameLower)
      );
      // Prefer chunks that START with the hotel name (bullet entries)
      const leadMatch = exactMatches.find((c) => {
        const cl = c.toLowerCase().replace(/^\s*(?:\d+[\.\)]|[*\-]|\*\*)\s*/, "");
        return cl.startsWith(nameLower.replace(/\*\*/g, ""));
      });
      return strip(leadMatch || exactMatches[0]);
    }

    // 3. Fallback: pick the chunk with the most matching long unique words
    const keywords = nameLower.split(/\s+/).filter((w) => w.length > 4);
    if (!keywords.length) return "";
    let best = null, bestScore = 0;
    for (const chunk of chunks) {
      const cl = chunk.toLowerCase();
      const score = keywords.filter((w) => cl.includes(w)).length;
      if (score > bestScore) { bestScore = score; best = chunk; }
    }
    return best && bestScore >= 2 ? strip(best) : "";
  }

  function buildChip(attr, score, kind) {
    const meta = attrMeta(attr);
    const kindLabel = kind === "priority" ? "Imprescindible" : kind === "optional" ? "Preferencia" : "Destacado";
    return `<span class="tag tag-${kind}" title="${kindLabel}: ${escapeHtml(meta.label)}">${meta.emoji} ${escapeHtml(meta.label)}</span>`;
  }

  // filterApplied: si es true solo mostramos chips AND/OR (los que el usuario pidió).
  // Si es false (búsqueda solo semántica) mostramos los top atributos del hotel.
  function renderTags(atributos = {}, must = [], nice = [], filterApplied = false) {
    if (!filterApplied) return "";
    const chips = [];
    const used = new Set();

    must.forEach((a) => {
      if ((atributos[a] || 0) > 0) {
        chips.push(buildChip(a, atributos[a], "priority"));
        used.add(a);
      }
    });
    nice.forEach((a) => {
      if ((atributos[a] || 0) > 0 && !used.has(a)) {
        chips.push(buildChip(a, atributos[a], "optional"));
        used.add(a);
      }
    });

    // Sin filtro activo: no mostrar chips para evitar confusión

    return chips.length ? `<div class="hotel-tags">${chips.join("")}</div>` : "";
  }

  function renderFilterSummary(filtro) {
    if (!filtro || !filtro.aplicado) return "";
    const must = filtro.must_haves || [];
    const nice = filtro.nice_to_haves || [];
    if (!must.length && !nice.length) return "";
    const fmt = (a) => {
      const m = attrMeta(a);
      return `${m.emoji} ${escapeHtml(m.label)}`;
    };
    const parts = [];
    if (must.length) {
      parts.push(
        `<span class="fs-block fs-must"><span class="fs-lbl">Imprescindible</span> ${must.map(fmt).join(", ")}</span>`
      );
    }
    if (nice.length) {
      parts.push(
        `<span class="fs-block fs-nice"><span class="fs-lbl">Preferencia</span> ${nice.map(fmt).join(", ")}</span>`
      );
    }
    return `<div class="filter-summary"><span class="fs-icon">📋</span>${parts.join('<span class="fs-sep">·</span>')}</div>`;
  }

  function renderHotels(hotels, destination, response = "", filtro = {}) {
    const cards = hotels
      .map((h, i) => {
        const name = escapeHtml(h.name || "Hotel");
        const score =
          typeof h.score === "number" ? h.score.toFixed(2) : "—";
        const afines = h.reviews_afines ?? 0;
        const reviews = Array.isArray(h.ejemplos_reviews)
          ? h.ejemplos_reviews.slice(0, 3)
          : [];

        const blurb = extractHotelBlurb(response, h.name || "");
        const blurbHtml = blurb
          ? `<p class="hotel-blurb">${formatText(blurb)}</p>`
          : "";

        const tagsHtml = renderTags(
          h.atributos || {},
          (filtro && filtro.must_haves) || [],
          (filtro && filtro.nice_to_haves) || [],
          !!(filtro && filtro.aplicado)
        );

        const reviewsHtml = reviews.length
          ? `
            <div class="hotel-reviews">
              ${reviews
                .map(
                  (r) =>
                    `<div class="review-quote">"${escapeHtml(truncate(r, 160))}"</div>`
                )
                .join("")}
            </div>`
          : "";

        const url = despegarUrl(destination, h.name || "");

        return `
          <a class="hotel-card" href="${url}" target="_blank" rel="noopener noreferrer">
            <div class="hotel-head">
              <div class="hotel-icon" aria-hidden="true">🏨</div>
              <div class="hotel-title-block">
                <h3 class="hotel-name">${name}</h3>
                <div class="hotel-stats">
                  <span class="hotel-rank">#${i + 1}</span>
                  <span class="dot-sep"></span>
                  <span><strong style="color:var(--text)">${afines}</strong> reviews afines</span>
                </div>
              </div>
              <div class="score-chip" title="Score de afinidad semántica">
                ${score}<small>score</small>
              </div>
            </div>
            ${tagsHtml}
            ${blurbHtml}
            ${reviewsHtml}
          </a>`;
      })
      .join("");

    const summary = renderFilterSummary(filtro);
    return `${summary}<div class="hotels">${cards}</div>`;
  }

  // Renderiza sección colapsable de alternativas (semánticas o estructuradas).
  // Sin blurb del agente — solo nombre, score, reviews afines y chips.
  function renderAlternativas(items, title, destination, filtro) {
    if (!items || !items.length) return "";
    const cards = items.map((h) => {
      const name    = escapeHtml(h.name || "Hotel");
      const score   = typeof h.score === "number" ? h.score.toFixed(2) : "—";
      const afines  = h.reviews_afines ?? 0;
      const reviews = Array.isArray(h.ejemplos_reviews) ? h.ejemplos_reviews.slice(0, 2) : [];
      const tagsHtml = renderTags(
        h.atributos || {},
        (filtro && filtro.must_haves) || [],
        (filtro && filtro.nice_to_haves) || [],
        !!(filtro && filtro.aplicado),
      );
      const reviewsHtml = reviews.length
        ? `<div class="hotel-reviews">${reviews.map((r) => `<div class="review-quote">"${escapeHtml(truncate(r, 130))}"</div>`).join("")}</div>`
        : "";
      const url = despegarUrl(destination, h.name || "");
      return `
        <a class="hotel-card hotel-card-alt" href="${url}" target="_blank" rel="noopener noreferrer">
          <div class="hotel-head">
            <div class="hotel-icon" aria-hidden="true">🏨</div>
            <div class="hotel-title-block">
              <h3 class="hotel-name">${name}</h3>
              <div class="hotel-stats">
                <span><strong style="color:var(--text)">${afines}</strong> reviews afines</span>
              </div>
            </div>
            <div class="score-chip score-chip-alt" title="Score de afinidad">${score}<small>score</small></div>
          </div>
          ${tagsHtml}
          ${reviewsHtml}
        </a>`;
    }).join("");
    return `
      <div class="alt-section">
        <div class="alt-title">${escapeHtml(title)}</div>
        <div class="hotels">${cards}</div>
      </div>`;
  }

  // ----- Thinking indicator with live timer + progress -----

  function appendThinking() {
    const el = document.createElement("div");
    el.className = "msg bot thinking";
    el.innerHTML = `
      <div class="avatar" aria-hidden="true">D</div>
      <div class="bubble">
        <div class="thinking-row">
          <span class="dots"><span></span><span></span><span></span></span>
          <span>El asistente está analizando reviews…</span>
        </div>
        <div class="thinking-sub">
          <span>Esto puede tardar entre 10 y 30 segundos</span>
          <span>·</span>
          <span>transcurrido: <span class="timer" data-timer>0s</span></span>
        </div>
        <div class="thinking-progress">
          <div class="thinking-progress-fill" data-progress></div>
        </div>
      </div>
    `;
    chatInner.appendChild(el);

    // timer + progress bar (asume ~60s como techo visual)
    const t0 = Date.now();
    const timerEl = el.querySelector("[data-timer]");
    const progEl = el.querySelector("[data-progress]");
    const TARGET = 60_000;

    const tick = () => {
      const elapsed = Date.now() - t0;
      const s = Math.floor(elapsed / 1000);
      timerEl.textContent = `${s}s`;
      const pct = Math.min(95, (elapsed / TARGET) * 100);
      progEl.style.width = pct + "%";
    };
    tick();
    const id = setInterval(tick, 500);

    // Devolvemos un wrapper que limpia el interval al remover
    return {
      remove() {
        clearInterval(id);
        el.remove();
      },
    };
  }

  // ============================================================
  // Utils
  // ============================================================

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Convierte saltos de línea en <br> + escapea html. Preserva **negritas**
  // simples por si el backend devuelve markdown ligero.
  function formatText(s) {
    let out = escapeHtml(s);
    out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/\n/g, "<br>");
    return out;
  }

  function truncate(s, max) {
    s = String(s);
    return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;
  }

  function scrollToBottom() {
    // smooth en mensajes nuevos, brusco la primera vez para no marear
    requestAnimationFrame(() => {
      chatScroll.scrollTo({
        top: chatScroll.scrollHeight,
        behavior: "smooth",
      });
    });
  }
})();
