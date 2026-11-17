const RAW = import.meta.env.VITE_API_BASE || "";
const BASE = RAW && !/^https?:\/\//i.test(RAW) ? "https://" + RAW.replace(/\/$/, "") : RAW.replace(/\/$/, "");

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
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error((data && data.detail) || "Error " + res.status);
  return data;
}
