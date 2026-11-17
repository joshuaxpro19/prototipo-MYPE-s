function normalizar(valor) {
  if (!valor) return "";
  const v = String(valor).trim().replace(/\/$/, "");
  if (/^https?:\/\//i.test(v)) return v;
  const host = v.includes(".") ? v : v + ".onrender.com";
  return "https://" + host;
}

const BASE = normalizar(import.meta.env.VITE_API_BASE);

export async function api(path, { token, method = "GET", body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new Error("El API no respondió JSON (revisa VITE_API_BASE)");
  }
  if (!res.ok) throw new Error((data && data.detail) || "Error " + res.status);
  return data;
}
