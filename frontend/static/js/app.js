import { searchProducts, getHistory, getDeals, getStores, getTrending, getCategories, getInflation } from "./api.js";
import { isFavorite, toggleFavorite, getFavorites, getFavoriteCount } from "./favorites.js";

// ── SEO defaults ───────────────────────────────────────────────────────────
const DEFAULT_TITLE = "TicoPrice — Historial de precios en Costa Rica";
const DEFAULT_DESC  = "Monitoreamos los precios de electrodomésticos, celulares y tecnología en 7 tiendas de Costa Rica. Detectá ofertas reales.";

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
  // SQLite devuelve sin zona horaria — forzar UTC añadiendo "Z"
  const utc  = iso.includes("T") || iso.endsWith("Z") ? iso : iso.replace(" ", "T") + "Z";
  const diff = Math.floor((Date.now() - new Date(utc)) / 60000);
  if (diff < 1)    return "recién";
  if (diff < 60)   return `hace ${diff}m`;
  if (diff < 1440) return `hace ${Math.floor(diff / 60)}h`;
  return `hace ${Math.floor(diff / 1440)}d`;
}

// ── Theme ──────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
  // Update Chart.js defaults so new charts use theme colors
  if (window.Chart) {
    Chart.defaults.color = theme === "dark" ? "#94a3b8" : "#64748b";
    Chart.defaults.borderColor = theme === "dark" ? "#334155" : "rgba(0,0,0,.08)";
  }
}

function initTheme() {
  const saved = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved ?? (prefersDark ? "dark" : "light"));

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next);
    applyTheme(next);
    // Re-render active chart if inflation chart is visible
    const activePeriodBtn = document.querySelector(".period-btn.period-active");
    if (activePeriodBtn && !document.getElementById("inflation-banner").classList.contains("hidden")) {
      loadInflation(parseInt(activePeriodBtn.dataset.days, 10));
    }
  });

  // Follow OS preference changes if user hasn't overridden
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (!localStorage.getItem("theme")) applyTheme(e.matches ? "dark" : "light");
  });
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
  document.getElementById("modal-full-link").href = path;

  // Meta tags dinámicos
  const desc = `Precio actual: ${colones(product.price)} en ${product.store}. Seguí el historial de precios de ${product.name} en TicoPrice.`;
  setMeta(`${product.name} — TicoPrice`, desc);
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
    setMeta(`${h.name} — TicoPrice`, desc);
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

function shortDate(iso) {
  const d = new Date(iso.slice(0, 10) + "T12:00:00Z");
  return d.toLocaleDateString("es-CR", { day: "numeric", month: "short" });
}

function renderHistory(h, container) {
  const ofertaBadge = h.oferta_real
    ? `<span class="badge badge-deal">Oferta real</span>`
    : "";

  // Variación vs precio más antiguo del período
  const points = [...h.history].reverse();
  let trendBadge = "";
  if (points.length >= 2) {
    const oldest = points[0].price;
    const newest = points[points.length - 1].price;
    if (oldest > 0) {
      const pct = ((newest - oldest) / oldest * 100).toFixed(1);
      trendBadge = pct > 0
        ? `<span class="badge badge-up">↑ +${pct}% en 90d</span>`
        : pct < 0
          ? `<span class="badge badge-down">↓ ${pct}% en 90d</span>`
          : "";
    }
  }

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
    ${points.length >= 2 ? `<div class="chart-wrap"><canvas id="history-chart"></canvas></div>` : ""}
    ${h.sample_count < 3 ? `<p class="history-note">
      Solo ${h.sample_count} registro(s) disponibles. ${trendBadge} El historial crecerá con más scrapes.</p>` : ""}
    <div class="modal-cta">
      <a href="${esc(h.url)}" target="_blank" rel="noopener" class="btn-store">
        Ver en ${esc(h.store)} →
      </a>
    </div>
  `;

  if (!points.length || points.length < 2) return;

  const labels = points.map((p) => shortDate(p.scraped_at));
  const prices = points.map((p) => p.price);
  const avg    = h.price_avg;

  const crFormat = (v) =>
    "₡" + Number(v).toLocaleString("es-CR", { maximumFractionDigits: 0 });

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
          pointHoverRadius: 6,
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
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `  ${ctx.dataset.label}: ${crFormat(ctx.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
        y: {
          ticks: { callback: crFormat, font: { size: 10 } },
        },
      },
    },
  });
}

// ── Product detail page ───────────────────────────────────────────────────

function showProductDetail(productId) {
  // Hide other views, show detail view (not as modal)
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll("nav button[data-view]").forEach((b) => b.classList.remove("active"));
  const view = document.getElementById("view-product");
  view.classList.add("active");

  const titleEl   = document.getElementById("detail-title");
  const contentEl = document.getElementById("detail-content");
  titleEl.textContent  = "Cargando…";
  contentEl.innerHTML  = `<div class="spinner">Cargando historial…</div>`;

  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }

  getHistory(productId)
    .then((h) => {
      titleEl.textContent = h.name;
      renderDetailContent(h, contentEl);
      const desc = `Precio actual: ${colones(h.current_price)} en ${h.store}. Historial de precios de ${h.name} en TicoPrice.`;
      setMeta(`${h.name} — TicoPrice`, desc);
      injectJsonLd({ name: h.name, in_stock: true }, h.current_price);
    })
    .catch((e) => {
      titleEl.textContent = "Error";
      contentEl.innerHTML = `<p class="empty">No se pudo cargar el producto: ${e.message}</p>`;
    });
}

function renderDetailContent(h, container) {
  const ofertaBadge = h.oferta_real
    ? `<span class="badge badge-deal">Oferta real</span>` : "";

  // Price history table rows (history comes newest-first from API)
  const historyRows = (h.history || []).map((row, i, arr) => {
    const prev = arr[i + 1];
    let changeTd = `<td class="change-flat">—</td>`;
    if (prev && prev.price > 0) {
      const pct = ((row.price - prev.price) / prev.price * 100).toFixed(1);
      if (pct > 0)
        changeTd = `<td class="change-up">↑ +${pct}%</td>`;
      else if (pct < 0)
        changeTd = `<td class="change-down">↓ ${pct}%</td>`;
      else
        changeTd = `<td class="change-flat">Sin cambio</td>`;
    }
    const stock = row.in_stock
      ? `<span class="dot dot-green"></span>`
      : `<span class="dot dot-gray"></span>`;
    return `<tr>
      <td>${shortDate(row.scraped_at)}</td>
      <td class="price-cell">${colones(row.price)}</td>
      ${changeTd}
      <td>${stock}</td>
    </tr>`;
  }).join("");

  const points = [...(h.history || [])].reverse();
  const chartHtml = points.length >= 2
    ? `<div class="chart-wrap" style="height:260px"><canvas id="history-chart"></canvas></div>`
    : `<p class="history-note">Solo ${h.sample_count} registro(s) — el historial crecerá con más scrapes.</p>`;

  container.innerHTML = `
    <div class="detail-store-row">
      <span class="card-store">${esc(h.store)}</span>
      ${ofertaBadge}
    </div>
    <div class="stats-row">
      <div class="stat-box">
        <div class="val">${colones(h.current_price)}</div>
        <div class="lbl">Precio actual</div>
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
    ${chartHtml}
    <div class="modal-cta" style="margin-bottom:1.5rem">
      <a href="${esc(h.url)}" target="_blank" rel="noopener" class="btn-store">
        Ver en ${esc(h.store)} →
      </a>
    </div>
    ${historyRows.length ? `
    <div class="price-history-section">
      <h3>Historial de precios (${h.sample_count} registros)</h3>
      <div class="table-wrap">
        <table class="history-table">
          <thead><tr><th>Fecha</th><th>Precio</th><th>Cambio</th><th>Stock</th></tr></thead>
          <tbody>${historyRows}</tbody>
        </table>
      </div>
    </div>` : ""}
  `;

  // Draw chart if enough points
  if (points.length >= 2) {
    const labels = points.map((p) => shortDate(p.scraped_at));
    const prices = points.map((p) => p.price);
    const avg    = h.price_avg;
    const crFmt  = (v) => "₡" + Number(v).toLocaleString("es-CR", { maximumFractionDigits: 0 });
    const ctx    = document.getElementById("history-chart").getContext("2d");
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
            pointHoverRadius: 6,
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
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: { label: (c) => `  ${c.dataset.label}: ${crFmt(c.parsed.y)}` },
          },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 8, font: { size: 10 } } },
          y: { ticks: { callback: crFmt, font: { size: 10 } } },
        },
      },
    });
  }
}

function closeDetail() {
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  removeJsonLd();
  setMeta(DEFAULT_TITLE, DEFAULT_DESC, location.origin + "/");
  document.getElementById("view-product").classList.remove("active");
  // Restore products view
  document.getElementById("view-products").classList.add("active");
  document.querySelector('nav button[data-view="view-products"]').classList.add("active");
  if (location.pathname.startsWith("/producto/")) history.pushState({}, "", "/");
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

  const CAT_ICON = {
    "celulares": "📱", "televisores": "📺", "audio": "🔊",
    "linea-blanca": "🏠", "electrodomesticos": "⚡", "computacion": "💻",
    "videojuegos": "🎮", "tablets": "📲", "aires-acondicionados": "❄️",
    "cuidado-cabello": "💇",
  };
  const icon = CAT_ICON[p.category] ?? "📦";
  const image = p.image_url
    ? `<img class="card-img" src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy"
         onerror="this.parentElement.innerHTML='<div class=\\'card-img-placeholder\\'>${icon}</div>'">`
    : `<div class="card-img-placeholder">${icon}</div>`;

  // Badge de delta desde que se guardó en favoritos
  let savedDelta = "";
  if (p.price_change_since_saved != null && Math.abs(p.price_change_since_saved) >= 100) {
    const diff = p.price_change_since_saved;
    savedDelta = diff < 0
      ? `<span class="badge badge-down badge-saved" title="Desde que lo guardaste">↓ bajó ${colones(Math.abs(diff))}</span>`
      : `<span class="badge badge-up badge-saved" title="Desde que lo guardaste">↑ subió ${colones(Math.abs(diff))}</span>`;
  }

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
        ${savedDelta}
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

// ── Sorting ────────────────────────────────────────────────────────────────

function sortProducts(products, sortBy) {
  const arr = [...products];
  switch (sortBy) {
    case "price-asc":
      return arr.sort((a, b) => (a.price || 0) - (b.price || 0));
    case "price-desc":
      return arr.sort((a, b) => (b.price || 0) - (a.price || 0));
    case "discount-desc":
      return arr.sort((a, b) => (b.discount_pct || 0) - (a.discount_pct || 0));
    case "change-desc":
      return arr.sort((a, b) => (b.price_change_7d ?? -999) - (a.price_change_7d ?? -999));
    case "change-asc":
      return arr.sort((a, b) => (a.price_change_7d ?? 999) - (b.price_change_7d ?? 999));
    default:
      return arr;
  }
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
  const grid    = document.getElementById("products-grid");
  const countEl = document.getElementById("results-count");
  grid.innerHTML = `<div class="spinner">Buscando…</div>`;
  try {
    const raw     = await searchProducts(q, category, store);
    const sortBy  = document.getElementById("sort-by").value;
    const results = sortProducts(raw, sortBy);
    if (!results.length) {
      grid.innerHTML = `<p class="empty">Sin resultados para "${esc(q)}".</p>`;
      countEl.textContent = "";
      return;
    }
    countEl.textContent = `${results.length} productos`;
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
    const raw     = await getTrending(7, 50);
    if (!raw.length) {
      grid.innerHTML = `<p class="empty">Aún no hay suficientes datos históricos para calcular aumentos. Volvé en unos días.</p>`;
      return;
    }
    const sortBy  = document.getElementById("sort-by").value;
    const results = sortBy === "price-asc" ? raw : sortProducts(raw, sortBy);
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
  document.getElementById("sort-by").addEventListener("change", () => {
    // Si está en trending, re-renderizar trending ordenado; si no, re-buscar
    const isDefault = !input.value.trim() && !activeCategory && !selStore.value;
    if (isDefault) loadTrending();
    else run();
  });

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

async function loadFavoritesView() {
  const grid = document.getElementById("favorites-grid");
  const favs = getFavorites();

  if (!favs.length) {
    grid.innerHTML = `<p class="empty">Todavía no tenés favoritos.<br>
      Hacé clic en <strong>♥</strong> en cualquier producto para guardarlo aquí.</p>`;
    return;
  }

  // 1. Mostrar datos guardados al instante (pueden ser viejos)
  grid.innerHTML = favs.map(productCard).join("");
  attachCardHandlers(grid);

  // 2. Refrescar precios en paralelo desde la API
  const refreshed = await Promise.all(
    favs.map(async (fav) => {
      try {
        const h = await getHistory(fav.product_id);
        const currentPrice = h.current_price ?? fav.price;
        const savedPrice   = fav.saved_price ?? fav.price;
        return {
          ...fav,
          price: currentPrice,
          price_change_since_saved:
            savedPrice && currentPrice != null ? currentPrice - savedPrice : null,
        };
      } catch {
        return fav; // si falla, mantener datos guardados
      }
    })
  );

  // 3. Re-renderizar con precios frescos y badge de variación
  grid.innerHTML = refreshed.map(productCard).join("");
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

  // Back button on product detail page
  document.getElementById("back-btn").addEventListener("click", closeDetail);

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
      // Check if we came from detail page or modal
      const detailView = document.getElementById("view-product");
      if (detailView.classList.contains("active")) {
        showProductDetail(parseInt(match[1], 10));
      } else {
        openModalById(parseInt(match[1], 10));
      }
    } else {
      // Close whatever is open
      document.getElementById("modal-overlay").classList.remove("open");
      if (document.getElementById("view-product").classList.contains("active")) {
        closeDetail();
      }
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
      removeJsonLd();
      setMeta(DEFAULT_TITLE, DEFAULT_DESC);
    }
  });
}

// ── Boot ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTabs();
  initModal();
  initSearch();
  initInflationPeriodBtns();
  updateFavBadge();
  loadInflation(7);

  // Deep link: si la URL es /producto/{id}, mostrar página de detalle
  const deepLink = location.pathname.match(/^\/producto\/(\d+)$/);
  if (deepLink) showProductDetail(parseInt(deepLink[1], 10));
});
