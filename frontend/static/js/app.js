(()=>{var ae=window.location.origin;async function g(e){let t=await fetch(ae+e);if(!t.ok)throw new Error(`${t.status} ${t.statusText}`);return t.json()}function D(e="",t="",n=""){let a=new URLSearchParams({q:e});t&&a.set("category",t),n&&a.set("store",n);let so=document.getElementById("sort-by").value;return so&&so.startsWith("price-")&&a.set("sort",so),g(`/products?${a}`)}function f(e){return g(`/products/${e}/history`)}function F(e=50){return g(`/deals?limit=${e}`)}function q(e=7,t=50){return g(`/trending?days=${e}&limit=${t}`)}function x(){return g("/stores")}function R(){return g("/categories")}function j(e=30){return g(`/inflation?days=${e}`)}var N="ptcr_favorites";function I(){try{return JSON.parse(localStorage.getItem(N)||"{}")}catch{return{}}}function O(e){localStorage.setItem(N,JSON.stringify(e))}function W(e){let t=I(),n=String(e.product_id);return n in t?(delete t[n],O(t),!1):(t[n]={...e,saved_price:e.price,saved_at:new Date().toISOString()},O(t),!0)}function k(){return Object.values(I()).sort((e,t)=>(t.saved_at??"").localeCompare(e.saved_at??""))}function z(){return Object.keys(I()).length}var M="TicoPrice \u2014 Historial de precios en Costa Rica",H="Monitoreamos los precios de electrodom\xE9sticos, celulares y tecnolog\xEDa en 7 tiendas de Costa Rica. Detect\xE1 ofertas reales.";function v(e,t,n=location.href){document.title=e,document.querySelector('meta[name="description"]')?.setAttribute("content",t),document.querySelector('meta[property="og:title"]')?.setAttribute("content",e),document.querySelector('meta[property="og:description"]')?.setAttribute("content",t),document.querySelector('meta[property="og:url"]')?.setAttribute("content",n),document.querySelector('meta[name="twitter:title"]')?.setAttribute("content",e),document.querySelector('meta[name="twitter:description"]')?.setAttribute("content",t)}function A(e,t){w();let n=document.createElement("script");n.type="application/ld+json",n.id="product-jsonld",n.textContent=JSON.stringify({"@context":"https://schema.org/","@type":"Product",name:e.name,offers:{"@type":"Offer",price:t??e.price,priceCurrency:"CRC",availability:e.in_stock===!1?"https://schema.org/OutOfStock":"https://schema.org/InStock",url:location.href}}),document.head.appendChild(n)}function w(){document.getElementById("product-jsonld")?.remove()}var l=e=>e==null||e===0?"\u2014":"\u20A1"+Number(e).toLocaleString("es-CR",{maximumFractionDigits:0}),i=e=>String(e??"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t]);function oe(e,t){let n;return(...a)=>{clearTimeout(n),n=setTimeout(()=>e(...a),t)}}function se(e){if(!e)return"nunca";let t=e.includes("T")||e.endsWith("Z")?e:e.replace(" ","T")+"Z",n=Math.floor((Date.now()-new Date(t))/6e4);return n<1?"reci\xE9n":n<60?`hace ${n}m`:n<1440?`hace ${Math.floor(n/60)}h`:`hace ${Math.floor(n/1440)}d`}function B(e){document.documentElement.setAttribute("data-theme",e);let t=document.getElementById("theme-toggle");t&&(t.textContent=e==="dark"?"\u2600\uFE0F":"\u{1F319}"),window.Chart&&(Chart.defaults.color=e==="dark"?"#94a3b8":"#64748b",Chart.defaults.borderColor=e==="dark"?"#334155":"rgba(0,0,0,.08)")}function re(){let e=localStorage.getItem("theme"),t=window.matchMedia("(prefers-color-scheme: dark)").matches;B(e??(t?"dark":"light")),document.getElementById("theme-toggle").addEventListener("click",()=>{let a=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";localStorage.setItem("theme",a),B(a);let o=document.querySelector(".period-btn.period-active");o&&!document.getElementById("inflation-banner").classList.contains("hidden")&&P(parseInt(o.dataset.days,10))}),window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",n=>{localStorage.getItem("theme")||B(n.matches?"dark":"light")})}var u=null,S=new Map,G=new Set;function _(){G=new Set(k().map(e=>e.product_id))}function C(e){try{let{protocol:t}=new URL(e);return t==="https:"||t==="http:"?e:"#"}catch{return"#"}}var h=null;function ce(e){let t='a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',n=()=>Array.from(e.querySelectorAll(t));h=a=>{if(a.key!=="Tab")return;let o=n();if(!o.length)return;let s=o.indexOf(document.activeElement);a.shiftKey?s<=0&&(a.preventDefault(),o[o.length-1].focus()):s===o.length-1&&(a.preventDefault(),o[0].focus())},e.addEventListener("keydown",h),n()[0]?.focus()}function ie(e){h&&(e.removeEventListener("keydown",h),h=null)}function de(e){let t=document.getElementById("modal-overlay"),n=document.getElementById("modal-title"),a=document.getElementById("modal-store"),o=document.getElementById("modal-body");n.textContent=e.name,a.textContent=e.store,o.innerHTML='<div class="spinner">Cargando historial\u2026</div>',t.classList.add("open"),ce(t.querySelector(".modal"));let s=`/producto/${e.product_id}`;location.pathname!==s&&history.pushState({productId:e.product_id},"",s),document.getElementById("modal-full-link").href=s;let c=`Precio actual: ${l(e.price)} en ${e.store}. Segu\xED el historial de precios de ${e.name} en TicoPrice.`;v(`${e.name} \u2014 TicoPrice`,c),A(e,e.price),f(e.product_id).then(r=>Q(r,o)).catch(r=>{o.innerHTML=`<p class="empty">Error cargando historial: ${i(r.message)}</p>`})}async function le(e){let t=document.getElementById("modal-overlay"),n=document.getElementById("modal-title"),a=document.getElementById("modal-store"),o=document.getElementById("modal-body");n.textContent="Cargando\u2026",a.textContent="",o.innerHTML='<div class="spinner">Cargando historial\u2026</div>',t.classList.add("open");try{let s=await f(e);n.textContent=s.name,a.textContent=s.store,Q(s,o);let c=`Precio actual: ${l(s.current_price)} en ${s.store}. Segu\xED el historial de precios de ${s.name}.`;v(`${s.name} \u2014 TicoPrice`,c),A({name:s.name,in_stock:!0},s.current_price)}catch(s){n.textContent="Producto no encontrado",a.textContent="",o.innerHTML=`<p class="empty">No se pudo cargar el producto: ${i(s.message)}</p>`}}function T(){let e=document.getElementById("modal-overlay");ie(e.querySelector(".modal")),e.classList.remove("open"),u&&(u.destroy(),u=null),w(),v(M,H,location.origin+"/"),location.pathname.startsWith("/producto/")&&history.pushState({},"","/")}function lc(){return window.Chart?Promise.resolve():lc.p||(lc.p=new Promise((y,x)=>{let s=document.createElement("script");s.src="/static/js/chart.umd.min.js";s.onload=y;s.onerror=x;document.head.appendChild(s)}))}function K(e,t,n){let a=t.map(r=>Y(r.scraped_at)),o=t.map(r=>r.price),s=r=>"\u20A1"+Number(r).toLocaleString("es-CR",{maximumFractionDigits:0}),c=document.getElementById(e).getContext("2d");return new Chart(c,{type:"line",data:{labels:a,datasets:[{label:"Precio",data:o,borderColor:"#2563eb",backgroundColor:"rgba(37,99,235,.08)",borderWidth:2,pointRadius:o.length>30?2:4,pointHoverRadius:6,tension:.3,fill:!0},n!=null&&{label:"Promedio",data:Array(o.length).fill(Math.round(n)),borderColor:"#d97706",borderDash:[5,4],borderWidth:1.5,pointRadius:0,fill:!1}].filter(Boolean)},options:{responsive:!0,maintainAspectRatio:!1,interaction:{mode:"index",intersect:!1},plugins:{legend:{labels:{boxWidth:12,font:{size:11}}},tooltip:{callbacks:{label:r=>`  ${r.dataset.label}: ${s(r.parsed.y)}`}}},scales:{x:{ticks:{maxTicksLimit:8,font:{size:10}}},y:{ticks:{callback:s,font:{size:10}}}}}})}function Y(e){return new Date(e.slice(0,10)+"T12:00:00Z").toLocaleDateString("es-CR",{day:"numeric",month:"short"})}function Q(e,t){let n=e.oferta_real?'<span class="badge badge-deal">Oferta real</span>':"",a=[...e.history].reverse(),o="";if(a.length>=2){let s=a[0].price,c=a[a.length-1].price;if(s>0){let r=((c-s)/s*100).toFixed(1);o=r>0?`<span class="badge badge-up">\u2191 +${r}% en 90d</span>`:r<0?`<span class="badge badge-down">\u2193 ${r}% en 90d</span>`:""}}t.innerHTML=`
    <div class="stats-row">
      <div class="stat-box">
        <div class="val">${l(e.current_price)}</div>
        <div class="lbl">Precio actual ${n}</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_min)}</div>
        <div class="lbl">M\xEDnimo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_max)}</div>
        <div class="lbl">M\xE1ximo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_avg)}</div>
        <div class="lbl">Promedio 90d</div>
      </div>
    </div>
    ${a.length>=2?'<div class="chart-wrap"><canvas id="history-chart"></canvas></div>':""}
    ${e.sample_count<3?`<p class="history-note">
      Solo ${e.sample_count} registro(s) disponibles. ${o} El historial crecer\xE1 con m\xE1s scrapes.</p>`:""}
    <div class="modal-cta">
      <a href="${C(e.url)}" target="_blank" rel="noopener" class="btn-store">
        Ver en ${i(e.store)} \u2192
      </a>
    </div>
  `,a.length>=2&&lc().then(()=>{document.getElementById("history-chart")&&(u=K("history-chart",a,e.price_avg))})}function X(e){document.querySelectorAll(".view").forEach(o=>o.classList.remove("active")),document.querySelectorAll("nav button[data-view]").forEach(o=>o.classList.remove("active")),document.getElementById("view-product").classList.add("active");let n=document.getElementById("detail-title"),a=document.getElementById("detail-content");n.textContent="Cargando\u2026",a.innerHTML='<div class="spinner">Cargando historial\u2026</div>',u&&(u.destroy(),u=null),f(e).then(o=>{n.textContent=o.name,ue(o,a);let s=`Precio actual: ${l(o.current_price)} en ${o.store}. Historial de precios de ${o.name} en TicoPrice.`;v(`${o.name} \u2014 TicoPrice`,s),A({name:o.name,in_stock:!0},o.current_price)}).catch(o=>{n.textContent="Error",a.innerHTML=`<p class="empty">No se pudo cargar el producto: ${i(o.message)}</p>`})}function ue(e,t){let n=e.oferta_real?'<span class="badge badge-deal">Oferta real</span>':"",a=(e.history||[]).map((c,r,d)=>{let p=d[r+1],m='<td class="change-flat">\u2014</td>';if(p&&p.price>0){let y=((c.price-p.price)/p.price*100).toFixed(1);y>0?m=`<td class="change-up">\u2191 +${y}%</td>`:y<0?m=`<td class="change-down">\u2193 ${y}%</td>`:m='<td class="change-flat">Sin cambio</td>'}let ne=c.in_stock?'<span class="dot dot-green"></span>':'<span class="dot dot-gray"></span>';return`<tr>
      <td>${Y(c.scraped_at)}</td>
      <td class="price-cell">${l(c.price)}</td>
      ${m}
      <td>${ne}</td>
    </tr>`}).join(""),o=[...e.history||[]].reverse(),s=o.length>=2?'<div class="chart-wrap" style="height:260px"><canvas id="history-chart"></canvas></div>':`<p class="history-note">Solo ${e.sample_count} registro(s) \u2014 el historial crecer\xE1 con m\xE1s scrapes.</p>`;t.innerHTML=`
    <div class="detail-store-row">
      <span class="card-store">${i(e.store)}</span>
      ${n}
    </div>
    <div class="stats-row">
      <div class="stat-box">
        <div class="val">${l(e.current_price)}</div>
        <div class="lbl">Precio actual</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_min)}</div>
        <div class="lbl">M\xEDnimo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_max)}</div>
        <div class="lbl">M\xE1ximo 90d</div>
      </div>
      <div class="stat-box">
        <div class="val">${l(e.price_avg)}</div>
        <div class="lbl">Promedio 90d</div>
      </div>
    </div>
    ${s}
    <div class="modal-cta" style="margin-bottom:1.5rem">
      <a href="${C(e.url)}" target="_blank" rel="noopener" class="btn-store">
        Ver en ${i(e.store)} \u2192
      </a>
    </div>
    ${a.length?`
    <div class="price-history-section">
      <h3>Historial de precios (${e.sample_count} registros)</h3>
      <div class="table-wrap">
        <table class="history-table">
          <thead><tr><th>Fecha</th><th>Precio</th><th>Cambio</th><th>Stock</th></tr></thead>
          <tbody>${a}</tbody>
        </table>
      </div>
    </div>`:""}
  `,o.length>=2&&lc().then(()=>{document.getElementById("history-chart")&&(u=K("history-chart",o,e.price_avg))})}function V(){u&&(u.destroy(),u=null),w(),v(M,H,location.origin+"/"),document.getElementById("view-product").classList.remove("active"),document.getElementById("view-products").classList.add("active"),document.querySelector('nav button[data-view="view-products"]').classList.add("active"),location.pathname.startsWith("/producto/")&&history.pushState({},"","/")}var b="";function pe(e){if(e==null)return"";let t=Math.abs(e).toFixed(1);return e>0?`<span class="badge badge-up">\u2191 +${t}% 7d</span>`:e<0?`<span class="badge badge-down">\u2193 ${e.toFixed(1)}% 7d</span>`:""}function E(e,fe){S.set(e.product_id,e);let t=e.discount_pct?`<span class="badge badge-discount">${Math.round(e.discount_pct)}% off</span>`:"",n=e.original_price&&e.original_price!==e.price?`<span class="card-original">${l(e.original_price)}</span>`:"",a=pe(e.price_change_7d),o=e.in_stock?'<span class="dot dot-green"></span> En stock':'<span class="dot dot-gray"></span> Agotado',s=G.has(e.product_id),r={celulares:"\u{1F4F1}",televisores:"\u{1F4FA}",audio:"\u{1F50A}","linea-blanca":"\u{1F3E0}",electrodomesticos:"\u26A1",computacion:"\u{1F4BB}",videojuegos:"\u{1F3AE}",tablets:"\u{1F4F2}","aires-acondicionados":"\u2744\uFE0F","cuidado-cabello":"\u{1F487}"}[e.category]??"\u{1F4E6}",d=e.image_url?`<img class="card-img" src="${i(e.image_url)}" alt="${i(e.name)}" data-emoji="${r}" loading="${fe?"eager":"lazy"}"${fe?" fetchpriority=\"high\"":""}">`:`<div class="card-img-placeholder">${r}</div>`,p="";if(e.price_change_since_saved!=null&&Math.abs(e.price_change_since_saved)>=100){let m=e.price_change_since_saved;p=m<0?`<span class="badge badge-down badge-saved" title="Desde que lo guardaste">\u2193 baj\xF3 ${l(Math.abs(m))}</span>`:`<span class="badge badge-up badge-saved" title="Desde que lo guardaste">\u2191 subi\xF3 ${l(Math.abs(m))}</span>`}return`
    <div class="product-card${e.in_stock===!1?" card-out-of-stock":""}" data-id="${e.product_id}">
      <button class="fav-btn${s?" fav-active":""}" data-pid="${e.product_id}" aria-label="Guardar en favoritos">\u2665</button>
      ${d}
      <div class="card-store">${i(e.store)}</div>
      <div class="card-name">${i(e.name)}</div>
      <div class="card-price-row">
        <span class="card-price">${l(e.price)}</span>
        ${n}
        ${t}
        ${a}
        ${p}
      </div>
      <div class="card-footer">
        <span>${o}</span>
        <span style="font-size:.72rem">${i(e.category??"")}</span>
      </div>
    </div>`}function ee(){let e=document.getElementById("fav-badge"),t=z();e.textContent=t,e.classList.toggle("hidden",t===0)}function te(e,t){let n=[...e];switch(t){case"price-asc":return n.sort((a,o)=>(a.price||0)-(o.price||0));case"price-desc":return n.sort((a,o)=>(o.price||0)-(a.price||0));case"discount-desc":return n.sort((a,o)=>(o.discount_pct||0)-(a.discount_pct||0));case"change-desc":return n.sort((a,o)=>(o.price_change_7d??-999)-(a.price_change_7d??-999));case"change-asc":return n.sort((a,o)=>(a.price_change_7d??999)-(o.price_change_7d??999));default:return n}}function L(e){e.querySelectorAll(".product-card").forEach(t=>{if(t.dataset.b)return;t.dataset.b=1;t.addEventListener("click",n=>{n.target.closest(".fav-btn")||de(S.get(+t.dataset.id))}),t.querySelector(".fav-btn").addEventListener("click",n=>{n.stopPropagation();let a=S.get(+t.dataset.id),o=W(a);n.currentTarget.classList.toggle("fav-active",o),ee()})})}async function me(e,t,n){let a=document.getElementById("products-grid"),o=document.getElementById("results-count");a.innerHTML='<div class="spinner">Buscando\u2026</div>';try{let s=await D(e,t,n);_();let c=document.getElementById("sort-by").value,r=te(s,c);if(!r.length){a.innerHTML=`<p class="empty">Sin resultados para "${i(e)}".</p>`,o.textContent="";return}o.textContent=`${r.length} productos`,a.innerHTML=r.map(E).join(""),L(a)}catch(s){a.innerHTML=`<p class="empty">Error: ${i(s.message)}</p>`}}async function J(){let e=document.getElementById("trending-grid");e.innerHTML='<div class="spinner">Cargando\u2026</div>';try{let t=await q(7,50);if(!t.length){e.innerHTML='<p class="empty">A\xFAn no hay suficientes datos hist\xF3ricos para calcular aumentos. Volv\xE9 en unos d\xEDas.</p>';return}_();let n=document.getElementById("sort-by").value,a=n==="price-asc"?t:te(t,n);e.innerHTML=a.slice(0,12).map((p,b)=>E(p,b===0)).join(""),L(e),a.length>12&&(window.requestIdleCallback||setTimeout)(()=>{e.insertAdjacentHTML("beforeend",a.slice(12).map(p=>E(p,!1)).join("")),L(e)})}catch(t){e.innerHTML=`<p class="empty">Error: ${i(t.message)}</p>`}}function U(){document.getElementById("inflation-banner").classList.remove("hidden"),document.getElementById("trending-section").classList.remove("hidden"),document.getElementById("search-results-section").classList.add("hidden")}function ge(){document.getElementById("inflation-banner").classList.add("hidden"),document.getElementById("trending-section").classList.add("hidden"),document.getElementById("search-results-section").classList.remove("hidden")}function ve(){let e=document.getElementById("search-input"),t=document.getElementById("filter-store"),n=oe(()=>{let a=e.value.trim(),o=t.value;!a&&!b&&!o?U():(ge(),me(a,b,o))},350);e.addEventListener("input",n),t.addEventListener("change",n),document.getElementById("sort-by").addEventListener("change",()=>{!e.value.trim()&&!b&&!t.value?J():n()}),x().then(a=>{a.forEach(o=>{let s=document.createElement("option");s.value=o.name,s.textContent=o.name,t.appendChild(s)})}),R().then(a=>{let o=document.getElementById("category-pills");a.forEach(s=>{let c=document.createElement("button");c.className="pill",c.dataset.cat=s,c.textContent=s.replace(/-/g," "),c.setAttribute("aria-pressed","false"),o.appendChild(c)})}),document.getElementById("category-pills").addEventListener("click",a=>{let o=a.target.closest(".pill");o&&(document.querySelectorAll(".pill").forEach(s=>{s.classList.remove("pill-active"),s.setAttribute("aria-pressed","false")}),o.classList.add("pill-active"),o.setAttribute("aria-pressed","true"),b=o.dataset.cat,n())}),U(),J()}function fe(e){return e>=20?"gap-high":e>=10?"gap-medium":"gap-low"}function he(e){return`
    <tr>
      <td class="td-name">
        <a href="${C(e.url)}" target="_blank" rel="noopener">${i(e.name)}</a>
        <small>${i(e.store)} \xB7 ${i(e.category??"")}</small>
      </td>
      <td>${l(e.current_price)}</td>
      <td>${l(e.original_price)}</td>
      <td>${e.advertised_discount.toFixed(1)}%</td>
      <td>${e.real_discount.toFixed(1)}%</td>
      <td class="${fe(e.deception_gap)}">${e.deception_gap.toFixed(1)}%</td>
      <td style="color:var(--text-muted)">${e.sample_count}</td>
    </tr>`}async function ye(){let e=document.getElementById("deals-tbody");e.innerHTML='<tr><td colspan="7" class="spinner">Calculando\u2026</td></tr>';try{let t=await F(100);if(!t.length){e.innerHTML=`<tr><td colspan="7" class="empty">
        No hay datos suficientes a\xFAn. Se necesitan \u2265 3 scrapes por producto.</td></tr>`;return}e.innerHTML=t.map(he).join("")}catch(t){e.innerHTML=`<tr><td colspan="7" class="empty">Error: ${i(t.message)}</td></tr>`}}var $=null;function Z(e){if(e==null)return{text:"\u2014",cls:""};let t=e>0?"+":"",n=e>0?"inf-up":e<0?"inf-down":"inf-flat";return{text:`${t}${e.toFixed(1)}%`,cls:n}}function be(e){let t=document.getElementById("inflation-cards"),n=document.getElementById("inflation-banner");if(!e.product_count){n.classList.add("hidden");return}n.classList.remove("hidden");let a=Z(e.overall_change_pct),o=e.by_category.filter(d=>d.category&&d.product_count>=3).slice(0,5).map(d=>{let p=Z(d.avg_change_pct);return`
        <div class="inf-card">
          <div class="inf-val ${p.cls}">${p.text}</div>
          <div class="inf-label">${i(d.category.replace(/-/g," "))}</div>
          <div class="inf-count">${d.product_count} productos</div>
        </div>`}).join("");if(t.innerHTML=`
    <div class="inf-card inf-card-main">
      <div class="inf-val ${a.cls}">${a.text}</div>
      <div class="inf-label">General</div>
      <div class="inf-count">${e.product_count} productos</div>
    </div>
    ${o}`,$&&($.destroy(),$=null),e.weekly_trend.length<2)return;lc().then(()=>{if(!document.getElementById("inflation-chart"))return;let s=e.weekly_trend.map(d=>d.week),c=e.weekly_trend.map(d=>d.avg_price),r=document.getElementById("inflation-chart").getContext("2d");$=new Chart(r,{type:"line",data:{labels:s,datasets:[{label:"Precio promedio",data:c,borderColor:"#2563eb",backgroundColor:"rgba(37,99,235,.07)",borderWidth:2,pointRadius:3,tension:.35,fill:!0}]},options:{responsive:!0,maintainAspectRatio:!1,plugins:{legend:{display:!1},tooltip:{callbacks:{label:d=>"  \u20A1"+Number(d.parsed.y).toLocaleString("es-CR",{maximumFractionDigits:0})}}},scales:{x:{ticks:{maxTicksLimit:6,font:{size:10}}},y:{ticks:{callback:d=>"\u20A1"+Number(d).toLocaleString("es-CR",{maximumFractionDigits:0}),font:{size:10}}}}}})})}async function P(e=30){try{let t=await j(e);be(t)}catch{document.getElementById("inflation-banner").classList.add("hidden")}}function $e(){document.querySelectorAll(".period-btn").forEach(e=>{e.addEventListener("click",()=>{document.querySelectorAll(".period-btn").forEach(t=>t.classList.remove("period-active")),e.classList.add("period-active"),P(parseInt(e.dataset.days,10))})})}async function _e(){let e=document.getElementById("favorites-grid"),t=k();if(!t.length){e.innerHTML=`<p class="empty">Todav\xEDa no ten\xE9s favoritos.<br>
      Hac\xE9 clic en <strong>\u2665</strong> en cualquier producto para guardarlo aqu\xED.</p>`;return}_(),e.innerHTML=t.map(E).join(""),L(e);let n=await Promise.all(t.map(async a=>{try{let s=(await f(a.product_id)).current_price??a.price,c=a.saved_price??a.price;return{...a,price:s,price_change_since_saved:c&&s!=null?s-c:null}}catch{return a}}));_(),e.innerHTML=n.map(E).join(""),L(e)}function Ee(e){let t=e.active?e.status==="requires_attention"?'<span class="badge badge-attention">Requiere atenci\xF3n</span>':'<span class="badge badge-ok">Activa</span>':'<span class="badge badge-attention">Inactiva</span>';return`
    <div class="store-card">
      <h3>${i(e.name)}</h3>
      <p>${i(e.scraper_type.toUpperCase())} \xB7 <a href="${C(e.base_url)}" target="_blank" rel="noopener">${i(e.base_url)}</a></p>
      <div class="store-meta">
        ${t}
        <span class="badge" style="background:var(--bg);color:var(--text-muted);border:1px solid var(--border)">
          ${e.total_products.toLocaleString()} productos
        </span>
      </div>
      <p style="margin-top:.6rem;font-size:.78rem;color:var(--text-muted)">
        \xDAltimo scrape: ${se(e.last_scraped_at)}
      </p>
    </div>`}async function Le(){let e=document.getElementById("stores-grid");e.innerHTML='<div class="spinner">Cargando\u2026</div>';try{let t=await x();e.innerHTML=t.map(Ee).join("")}catch(t){e.innerHTML=`<p class="empty">Error: ${i(t.message)}</p>`}}function we(){let e=document.querySelectorAll("nav button[data-view]"),t=document.querySelectorAll(".view");e.forEach(n=>{n.addEventListener("click",()=>{e.forEach(a=>a.classList.remove("active")),t.forEach(a=>a.classList.remove("active")),n.classList.add("active"),document.getElementById(n.dataset.view).classList.add("active"),n.dataset.view==="view-deals"&&ye(),n.dataset.view==="view-stores"&&Le(),n.dataset.view==="view-favorites"&&_e()})})}function Ce(){document.getElementById("modal-close").addEventListener("click",T),document.getElementById("modal-overlay").addEventListener("click",e=>{e.target===e.currentTarget&&T()}),document.addEventListener("keydown",e=>{e.key==="Escape"&&T()}),document.getElementById("back-btn").addEventListener("click",V),document.getElementById("modal-share").addEventListener("click",()=>{let e=document.getElementById("share-label");navigator.clipboard.writeText(location.href).then(()=>{e.textContent="\xA1Copiado!",setTimeout(()=>{e.textContent="Compartir"},2e3)}).catch(()=>{let t=Object.assign(document.createElement("input"),{value:location.href});document.body.appendChild(t),t.select(),document.execCommand("copy"),document.body.removeChild(t),e.textContent="\xA1Copiado!",setTimeout(()=>{e.textContent="Compartir"},2e3)})}),window.addEventListener("popstate",()=>{let e=location.pathname.match(/^\/producto\/(\d+)$/);e?document.getElementById("view-product").classList.contains("active")?X(parseInt(e[1],10)):le(parseInt(e[1],10)):(document.getElementById("modal-overlay").classList.remove("open"),document.getElementById("view-product").classList.contains("active")&&V(),u&&(u.destroy(),u=null),w(),v(M,H))})}document.addEventListener("DOMContentLoaded",()=>{re(),we(),Ce(),ve(),$e(),ee(),P(7);let e=location.pathname.match(/^\/producto\/(\d+)$/);e&&X(parseInt(e[1],10))});"serviceWorker"in navigator&&window.addEventListener("load",()=>{navigator.serviceWorker.register("/sw.js").catch(()=>{})});})();
;(function(){var o=new MutationObserver(function(ms){ms.forEach(function(m){m.addedNodes.forEach(function(n){if(n.nodeType!==1)return;var imgs=n.classList&&n.classList.contains('card-img')?[n]:n.querySelectorAll('.card-img');imgs.forEach(function(img){img.addEventListener('error',function(){img.parentElement.innerHTML='<div class="card-img-placeholder">'+(img.dataset.emoji||'📦')+'</div>';},{once:true});});});});});o.observe(document.body,{childList:true,subtree:true});})();
