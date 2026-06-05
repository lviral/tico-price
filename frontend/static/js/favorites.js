/**
 * Gestión de favoritos en localStorage.
 * Guarda el objeto completo del producto para no depender de la API al mostrar la vista.
 */

const KEY = "ptcr_favorites";

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}");
  } catch {
    return {};
  }
}

function save(data) {
  localStorage.setItem(KEY, JSON.stringify(data));
}

export function isFavorite(productId) {
  return String(productId) in load();
}

/**
 * Alterna el favorito. Retorna true si quedó como favorito, false si se eliminó.
 */
export function toggleFavorite(product) {
  const data = load();
  const key  = String(product.product_id);
  if (key in data) {
    delete data[key];
    save(data);
    return false;
  }
  data[key] = { ...product, saved_at: new Date().toISOString() };
  save(data);
  return true;
}

/** Retorna todos los favoritos como array, ordenados por guardado más reciente. */
export function getFavorites() {
  return Object.values(load()).sort((a, b) =>
    (b.saved_at ?? "").localeCompare(a.saved_at ?? ""),
  );
}

export function getFavoriteCount() {
  return Object.keys(load()).length;
}
