const BASE = window.location.origin;

async function get(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function searchProducts(q = "", category = "", store = "") {
  const p = new URLSearchParams({ q });
  if (category) p.set("category", category);
  if (store) p.set("store", store);
  return get(`/products?${p}`);
}

export function getHistory(productId) {
  return get(`/products/${productId}/history`);
}

export function getDeals(limit = 50) {
  return get(`/deals?limit=${limit}`);
}

export function getTrending(days = 7, limit = 50) {
  return get(`/trending?days=${days}&limit=${limit}`);
}

export function getStores() {
  return get("/stores");
}

export function getCategories() {
  return get("/categories");
}

export function getInflation(days = 30) {
  return get(`/inflation?days=${days}`);
}
