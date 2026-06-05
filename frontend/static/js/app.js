import { searchProducts, getHistory, getDeals, getStores, getTrending, getCategories, getInflation } from "./api.js";
import { isFavorite, toggleFavorite, getFavorites, getFavoriteCount } from "./favorites.js";

// ── SEO defaults ───────────────────────────────────────────────────────────
const DEFAULT_TITLE = "Precio Tracker CR — Historial de precios en Costa Rica";
const DEFAULT_DESC  = "Seguí los precios de electrodomésticos y tecnología en tiendas de Costa Rica. Detectá ofertas reales y monitoreá la inflación.";

function setMeta(title, description, url = location.href) {
  document.title = title;
  document.querySelector('meta[name="description"]')?.setAttribute("content", description);
  document.querySelector('meta[property="og:title"]')?.setAttribute("content", title);
  document.querySelector('meta[property="og:description"]')?.setAttribute("content", description);
  document.querySelector('meta[property="og:url"]')?.setAttribute("content", url);
  document.querySelector('meta[name="twitter:title"]')?.setAttribute("content", title);
  document.querySelector('meta[name="twitter:description"]')?.setAttribute("content", description);
}

function injectJsonLd(product, price) {
  removeJsonLd();
  const s = document.createElement("script");
  s.type = "application/ld+json";
  s.id   = "product-jsonld";
  s.textContent = JSON.stringify({
    "@context": "https://schema.org/",
    "@type": "Product",
    "name": product.name,
    "offers": {
      "@type": "Offer",
      "price": price ?? product.price,
      "priceCurrency": "CRC",
      "availability": product.in_stock === false
        ? "https://schema.org/OutOfStock"
        : "https://schema.org/InStock",
      "url": location.href,
    },
  });
  document.head.appendChild(s);
}

function removeJsonLd() {
  document.getElementById("product-jsonld")?.remove();
}

// ── Helpers ────────────────────────────────────────────────────────────────

const colones = (n) =>
  (n == null || n === 0) ? "—" : "₡" + Number(n).toLocaleString("es-CR", { maximumFractionDigits: 0 });

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function timeAgo(iso) {
  if (!iso) return "nunca";
  const diff = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (diff < 60) return `hace ${diff}m`;
  if (diff < 1440) return `hace ${Math.floor(diff / 60)}h`;
  return `hace ${Math.floor(diff / 1440)}d`;
}

// ── Modal ──────────────────────────────────────────────────────────────────

let chartInstance = null;

function openModal(product) {
  const overlay = document.getElementById("modal-overlay");
  const title   = document.getElementById("modal-title");
  const store   = document.getElementById("modal-store");
  const body    = document.getElementById("modal-body");

  title.textContent = product.name;
  store.textContent = product.store;
  body.innerHTML    = `<div class="spinner">Cargando historial…</div>`;
  overlay.classList.add("open");

  // History API routing — URL real e indexable
  const path = `/producto/${product.product_id}`;
  if (location.pathname !== path) {
    history.pushState({ productId: product.product_id }, "", path);
  }

  // Meta tags dinámicos
  const desc = `Precio actual: ${colones(product.price)} en ${product.store}. Seguí el historial de precios de ${product.name} en Precio Tracker CR.`;
  setMeta(`${product.name} — Precio Tracker CR`, desc);
  injectJsonLd(product, product.price);

  getHistory(product.product_id)
    .then((h) => renderHistory(h, body))
    .catch((e) => { body.innerHTML = `<p class="empty">Error cargando historial: ${e.message}</p>`; });
}

/** Abre el modal cargando el producto directo por ID (para deep links desde URL). */
async function openModalById(productId) {
  const overlay = document.getElementById("modal-overlay");
  const title   = document.getElementById("modal-title");
  const store   = document.getElementById("modal-store");
  const body    = document.getElementById("modal-body");

  title.textContent = "Cargando…";
  store.textContent = "";
  body.innerHTML    = `<div class="spinner">Cargando historial…</div>`;
  overlay.classList.add("open");

  try {
    const h = await getHistory(productId);
    title.textContent = h.name;
    store.textContent = h.store;
    renderHistory(h, body);

    const desc = `Precio actual: ${colones(h.current_price)} en ${h.store}. Seguí el historial de precios de ${h.name}.`;
    setMeta(`${h.name} — Precio Tracker CR`, desc);
    injectJsonLd({ name: h.name, in_stock: true }, h.current_price);
  } catch (e) {
    title.textContent = "Producto no encontrado";
    store.textContent = "";
    body.innerHTML = `<p class="empty">No se pudo cargar el producto: ${e.message}</p>`;
  }
}

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("open");
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  removeJsonLd();
  setMeta(DEFAULT_TITLE, DEFAULT_DESC, location.origin + "/");
  // Volver a la raíz si estamos en /producto/*
  if (location.pathname.startsWith("/producto/")) {
    history.pushState({}, "", "/");
  }
}

function renderHistory(h, container) {
  const ofertaBadge = h.oferta_real
    ? `<span class="badge badge-deal">Oferta real</span>`
    : "";

  container.innerHTML = `
    <div class="stats-row">
      <div class="stat-box">
        <div class="val">${colones(h.current_price)}</div>
        <div class="lbl">Precio actual ${ofertaBadge}</div>
      </div>
      <div class="stat-box">
        <div class="val">${colones(h.price_min)}</div>
        <div class="lbl">Mínimo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${colones(h.price_max)}</div>
        <div class="lbl">Máximo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${colones(h.price_avg)}</div>
        <div class="lbl">Promedio 90d</div>
      </div>
    </div>
    <div class="chart-wrap"><canvas id="history-chart"></canvas></div>
    ${h.sample_count < 3 ? `<p style="margin-top:.75rem;font-size:.8rem;color:var(--text-muted)">
      Solo ${h.sample_count} registro(s). Los datos mejorarán con más scrapes.</p>` : ""}
  `;

  const points = [...h.history].reverse();
  if (!points.length) return;

  const labels = points.map((p) => p.scraped_at.slice(0, 10));
  const prices = points.map((p) => p.price);

  const avg = h.price_avg;
  const ctx = document.getElementById("history-chart").getContext("2d");
  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Precio",
          data: prices,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37,99,235,.08)",
          borderWidth: 2,
          pointRadius: prices.length > 30 ? 2 : 4,
          tension: 0.3,
          fill: true,
        },
        avg != null && {
          label: "Promedio",
          data: Array(prices.length).fill(Math.round(avg)),
          borderColor: "#d97706",
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
        },
      ].filter(Boolean),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: {
          ticks: {
            callback: (v) => "₡" + Number(v).toLocaleString("es-CR", { maximumFractionDigits: 0 }),
            font: { size: 10 },
          },
        },
      },
    },
  });
}

// ── Products view ──────────────────────────────────────────────────────────

let activeCategory = "";   // categoría seleccionada en las pills

function variationBadge(pct) {
  if (pct == null) return "";
  const abs = Math.abs(pct).toFixed(1);
  if (pct > 0) return `<span class="badge badge-up">↑ +${abs}% 7d</span>`;
  if (pct < 0) return `<span class="badge badge-down">↓ ${pct.toFixed(1)}% 7d</span>`;
  return "";
}

function productCard(p) {
  const discount   = p.discount_pct
    ? `<span class="badge badge-discount">${Math.round(p.discount_pct)}% off</span>`
    : "";
  const original = p.original_price && p.original_price !== p.price
    ? `<span class="card-original">${colones(p.original_price)}</span>`
    : "";
  const variation = variationBadge(p.price_change_7d);
  const stock = p.in_stock
    ? `<span class="dot dot-green"></span> En stock`
    : `<span class="dot dot-gray"></span> Agotado`;
  const fav = isFavorite(p.product_id);

  const image = p.image_url
    ? `<img class="card-img" src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy" onerror="this.style.display='none'">`
    : `<div class="card-img-placeholder">${esc((p.name ?? "?")[0].toUpperCase())}</div>`;

  return `
    <div class="product-card${p.in_stock === false ? " card-out-of-stock" : ""}" data-id='${esc(JSON.stringify(p))}'>
      <button class="fav-btn${fav ? " fav-active" : ""}" data-pid="${p.product_id}" aria-label="Guardar en favoritos">♥</button>
      ${image}
      <div class="card-store">${esc(p.store)}</div>
      <div class="card-name">${esc(p.name)}</div>
      <div class="card-price-row">
        <span class="card-price">${colones(p.price)}</span>
        ${original}
        ${discount}
        ${variation}
      </div>
      <div class="card-footer">
        <span>${stock}</span>
        <span style="font-size:.72rem">${esc(p.category ?? "")}</span>
      </div>
    </div>`;
}

function updateFavBadge() {
  const badge = document.getElementById("fav-badge");
  const count = getFavoriteCount();
  badge.textContent = count;
  badge.classList.toggle("hidden", count === 0);
}

function attachCardHandlers(container) {
  container.querySelectorAll(".product-card").forEach((card) => {
    // Abrir modal al hacer clic en la card (no en el corazón)
    card.addEventListener("click", (e) => {
      if (e.target.closest(".fav-btn")) return;
      openModal(JSON.parse(card.dataset.id));
    });

    // Toggle favorito
    card.querySelector(".fav-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      const product = JSON.parse(card.dataset.id);
      const nowFav  = toggleFavorite(product);
      e.currentTarget.classList.toggle("fav-active", nowFav);
      updateFavBadge();
    });
  });
}

async function loadProducts(q, category, store) {
  const grid = document.getElementById("products-grid");
  grid.innerHTML = `<div class="spinner">Buscando…</div>`;
  try {
    const results = await searchProducts(q, category, store);
    if (!results.length) {
      grid.innerHTML = `<p class="empty">Sin resultados para "${esc(q)}".</p>`;
      return;
    }
    grid.innerHTML = results.map(productCard).join("");
    attachCardHandlers(grid);
  } catch (e) {
    grid.innerHTML = `<p class="empty">Error: ${e.message}</p>`;
  }
}

async function loadTrending() {
  const grid = document.getElementById("trending-grid");
  grid.innerHTML = `<div class="spinner">Cargando…</div>`;
  try {
    const results = await getTrending(7, 50);
    if (!results.length) {
      grid.innerHTML = `<p class="empty">Aún no hay suficientes datos históricos para calcular aumentos. Volvé en unos días.</p>`;
      return;
    }
    grid.innerHTML = results.map(productCard).join("");
    attachCardHandlers(grid);
  } catch (e) {
    grid.innerHTML = `<p class="empty">Error: ${e.message}</p>`;
  }
}

function showTrending() {
  document.getElementById("inflation-banner").classList.remove("hidden");
  document.getElementById("trending-section").classList.remove("hidden");
  document.getElementById("search-results-section").classList.add("hidden");
}

function showSearchResults() {
  document.getElementById("inflation-banner").classList.add("hidden");
  document.getElementById("trending-section").classList.add("hidden");
  document.getElementById("search-results-section").classList.remove("hidden");
}

function initSearch() {
  const input    = document.getElementById("search-input");
  const selStore = document.getElementById("filter-store");

  const run = debounce(() => {
    const q     = input.value.trim();
    const store = selStore.value;
    const isDefault = !q && !activeCategory && !store;

    if (isDefault) {
      showTrending();
    } else {
      showSearchResults();
      loadProducts(q, activeCategory, store);
    }
  }, 350);

  input.addEventListener("input", run);
  selStore.addEventListener("change", run);

  // Poblar filtro de tiendas
  getStores().then((stores) => {
    stores.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.name; opt.textContent = s.name;
      selStore.appendChild(opt);
    });
  });

  // Poblar pills de categorías dinámicamente
  getCategories().then((cats) => {
    const container = document.getElementById("category-pills");
    cats.forEach((cat) => {
      const btn = document.createElement("button");
      btn.className = "pill";
      btn.dataset.cat = cat;
      btn.textContent = cat.replace(/-/g, " ");
      container.appendChild(btn);
    });
  });

  // Delegación de eventos para las pills
  document.getElementById("category-pills").addEventListener("click", (e) => {
    const btn = e.target.closest(".pill");
    if (!btn) return;
    document.querySelectorAll(".pill").forEach((p) => p.classList.remove("pill-active"));
    btn.classList.add("pill-active");
    activeCategory = btn.dataset.cat;
    run();
  });

  // Arrancar con vista trending
  showTrending();
  loadTrending();
}

// ── Deals view ─────────────────────────────────────────────────────────────

function gapClass(gap) {
  if (gap >= 20) return "gap-high";
  if (gap >= 10) return "gap-medium";
  return "gap-low";
}

function dealRow(d) {
  return `
    <tr>
      <td class="td-name">
        <a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.name)}</a>
        <small>${esc(d.store)} · ${esc(d.category ?? "")}</small>
      </td>
      <td>${colones(d.current_price)}</td>
      <td>${colones(d.original_price)}</td>
      <td>${d.advertised_discount.toFixed(1)}%</td>
      <td>${d.real_discount.toFixed(1)}%</td>
      <td class="${gapClass(d.deception_gap)}">${d.deception_gap.toFixed(1)}%</td>
      <td style="color:var(--text-muted)">${d.sample_count}</td>
    </tr>`;
}

async function loadDeals() {
  const tbody = document.getElementById("deals-tbody");
  tbody.innerHTML = `<tr><td colspan="7" class="spinner">Calculando…</td></tr>`;
  try {
    const deals = await getDeals(100);
    if (!deals.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty">
        No hay datos suficientes aún. Se necesitan ≥ 3 scrapes por producto.</td></tr>`;
      return;
    }
    tbody.innerHTML = deals.map(dealRow).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">Error: ${e.message}</td></tr>`;
  }
}

// ── Inflation banner ───────────────────────────────────────────────────────

let inflationChartInstance = null;

function changePct(val) {
  if (val == null) return { text: "—", cls: "" };
  const sign = val > 0 ? "+" : "";
  const cls  = val > 0 ? "inf-up" : val < 0 ? "inf-down" : "inf-flat";
  return { text: `${sign}${val.toFixed(1)}%`, cls };
}

function renderInflationBanner(data) {
  const cards  = document.getElementById("inflation-cards");
  const banner = document.getElementById("inflation-banner");

  if (!data.product_count) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");

  // Tarjeta general
  const gen = changePct(data.overall_change_pct);
  const catCards = data.by_category
    .filter((c) => c.category && c.product_count >= 3)
    .slice(0, 5)
    .map((c) => {
      const v = changePct(c.avg_change_pct);
      return `
        <div class="inf-card">
          <div class="inf-val ${v.cls}">${v.text}</div>
          <div class="inf-label">${esc(c.category.replace(/-/g, " "))}</div>
          <div class="inf-count">${c.product_count} productos</div>
        </div>`;
    })
    .join("");

  cards.innerHTML = `
    <div class="inf-card inf-card-main">
      <div class="inf-val ${gen.cls}">${gen.text}</div>
      <div class="inf-label">General</div>
      <div class="inf-count">${data.product_count} productos</div>
    </div>
    ${catCards}`;

  // Gráfico de tendencia semanal
  if (inflationChartInstance) { inflationChartInstance.destroy(); inflationChartInstance = null; }
  if (data.weekly_trend.length < 2) return;

  const labels = data.weekly_trend.map((p) => p.week);
  const prices = data.weekly_trend.map((p) => p.avg_price);
  const ctx    = document.getElementById("inflation-chart").getContext("2d");

  inflationChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Precio promedio",
        data: prices,
        borderColor: "#2563eb",
        backgroundColor: "rgba(37,99,235,.07)",
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.35,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => "  ₡" + Number(ctx.parsed.y).toLocaleString("es-CR", { maximumFractionDigits: 0 }),
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 6, font: { size: 10 } } },
        y: {
          ticks: {
            callback: (v) => "₡" + Number(v).toLocaleString("es-CR", { maximumFractionDigits: 0 }),
            font: { size: 10 },
          },
        },
      },
    },
  });
}

async function loadInflation(days = 30) {
  try {
    const data = await getInflation(days);
    renderInflationBanner(data);
  } catch (e) {
    // Silencioso: si no hay datos suficientes el banner simplemente no aparece
    document.getElementById("inflation-banner").classList.add("hidden");
  }
}

function initInflationPeriodBtns() {
  document.querySelectorAll(".period-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".period-btn").forEach((b) => b.classList.remove("period-active"));
      btn.classList.add("period-active");
      loadInflation(parseInt(btn.dataset.days, 10));
    });
  });
}

// ── Favorites view ────────────────────────────────────────────────────────

function loadFavoritesView() {
  const grid = document.getElementById("favorites-grid");
  const favs = getFavorites();
  if (!favs.length) {
    grid.innerHTML = `<p class="empty">Todavía no tenés favoritos.<br>
      Hacé clic en <strong>♥</strong> en cualquier producto para guardarlo aquí.</p>`;
    return;
  }
  grid.innerHTML = favs.map(productCard).join("");
  attachCardHandlers(grid);
}

// ── Stores view ────────────────────────────────────────────────────────────

function storeCard(s) {
  const statusBadge = s.active
    ? (s.status === "requires_attention"
        ? `<span class="badge badge-attention">Requiere atención</span>`
        : `<span class="badge badge-ok">Activa</span>`)
    : `<span class="badge badge-attention">Inactiva</span>`;

  return `
    <div class="store-card">
      <h3>${esc(s.name)}</h3>
      <p>${esc(s.scraper_type.toUpperCase())} · <a href="${esc(s.base_url)}" target="_blank" rel="noopener">${esc(s.base_url)}</a></p>
      <div class="store-meta">
        ${statusBadge}
        <span class="badge" style="background:var(--bg);color:var(--text-muted);border:1px solid var(--border)">
          ${s.total_products.toLocaleString()} productos
        </span>
      </div>
      <p style="margin-top:.6rem;font-size:.78rem;color:var(--text-muted)">
        Último scrape: ${timeAgo(s.last_scraped_at)}
      </p>
    </div>`;
}

async function loadStores() {
  const grid = document.getElementById("stores-grid");
  grid.innerHTML = `<div class="spinner">Cargando…</div>`;
  try {
    const stores = await getStores();
    grid.innerHTML = stores.map(storeCard).join("");
  } catch (e) {
    grid.innerHTML = `<p class="empty">Error: ${e.message}</p>`;
  }
}

// ── Tab navigation ─────────────────────────────────────────────────────────

function initTabs() {
  const tabs  = document.querySelectorAll("nav button[data-view]");
  const views = document.querySelectorAll(".view");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      views.forEach((v) => v.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.view).classList.add("active");

      if (tab.dataset.view === "view-deals")     loadDeals();
      if (tab.dataset.view === "view-stores")    loadStores();
      if (tab.dataset.view === "view-favorites") loadFavoritesView();
    });
  });
}

// ── Modal wiring ───────────────────────────────────────────────────────────

function initModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // Botón compartir: copia la URL al portapapeles
  document.getElementById("modal-share").addEventListener("click", () => {
    const label = document.getElementById("share-label");
    navigator.clipboard.writeText(location.href).then(() => {
      label.textContent = "¡Copiado!";
      setTimeout(() => { label.textContent = "Compartir"; }, 2000);
    }).catch(() => {
      // Fallback para navegadores sin clipboard API
      const input = Object.assign(document.createElement("input"), { value: location.href });
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      document.body.removeChild(input);
      label.textContent = "¡Copiado!";
      setTimeout(() => { label.textContent = "Compartir"; }, 2000);
    });
  });

  // Botón atrás / adelante del navegador
  window.addEventListener("popstate", () => {
    const match = location.pathname.match(/^\/producto\/(\d+)$/);
    if (match) {
      openModalById(parseInt(match[1], 10));
    } else {
      document.getElementById("modal-overlay").classList.remove("open");
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      removeJsonLd();
      setMeta(DEFAULT_TITLE, DEFAULT_DESC);
    }
  });
}

// ── Boot ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initModal();
  initSearch();
  initInflationPeriodBtns();
  updateFavBadge();
  loadInflation(30);

  // Deep link: si la URL es /producto/{id}, abrir modal directo
  const deepLink = location.pathname.match(/^\/producto\/(\d+)$/);
  if (deepLink) openModalById(parseInt(deepLink[1], 10));
});
