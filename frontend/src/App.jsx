import { useEffect, useState } from "react";
import { api } from "./api.js";

const COL = ["#2e86ab", "#7b1fa2", "#ef6c00", "#2e7d32"];
const nf = (v, d = 0) => Number(v ?? 0).toLocaleString("es-PE", { minimumFractionDigits: d, maximumFractionDigits: d });
const rango = (s) => { const [a, b] = s.split("/"); return `${corta(a)} – ${corta(b)}`; };

const corta = (s) => {
  const d = new Date(s.split("/")[0] + "T00:00:00");
  return d.toLocaleDateString("es-PE", { day: "2-digit", month: "short" });
};

function semaforo(r) {
  const p = r.pronostico_semana_siguiente ?? r.pronostico ?? 0;
  const stock = r.stock ?? 0;
  if ((r.prob_quiebre ?? r.prob) >= 0.6 || stock < p * 0.8) return { txt: "Faltará", cls: "bad", bg: "bg-bad" };
  if (stock > p * 1.5 || (r.cobertura ?? 0) > 2.5) return { txt: "Sobra", cls: "ok", bg: "bg-ok" };
  return { txt: "Ajustar", cls: "warn", bg: "bg-warn" };
}

function queHacer(r) {
  const p = r.pronostico_semana_siguiente ?? r.pronostico ?? 0;
  const stock = r.stock ?? 0;
  const s = semaforo(r);
  if (s.txt === "Faltará") return { txt: `Comprar ${nf(Math.max(1, Math.round(p * 1.1 - stock)))} unid. hoy`, cls: "bad" };
  if (s.txt === "Sobra") return { txt: "No compres esta semana", cls: "ok" };
  const falta = Math.round(p * 1.1 - stock);
  return falta > 0
    ? { txt: `Compra de ${nf(falta)} unid.`, cls: "warn" }
    : { txt: `Repón solo si baja de ${nf(Math.round(p * 0.8))}`, cls: "warn" };
}

function mezclar(items) {
  const grupos = {};
  items.forEach((a) => {
    const k = a.tipo || "quiebre";
    if (!grupos[k]) grupos[k] = [];
    grupos[k].push(a);
  });
  const salida = [];
  let i = 0;
  while (salida.length < items.length) {
    let agrego = false;
    Object.keys(grupos).forEach((k) => {
      if (grupos[k][i]) { salida.push(grupos[k][i]); agrego = true; }
    });
    if (!agrego) break;
    i += 1;
  }
  return salida;
}

const TIPOS = {
  quiebre: ["Quiebre", "bg-bad bad"],
  sobrestock: ["Sobre-stock", "bg-warn warn"],
  venta_baja: ["Venta baja", "bg-warn warn"],
};

function Serie({ semanas, real, pronostico }) {
  const w = 560, h = 220, L = 46, B = 28, T = 16;
  const max = Math.max(...real, ...pronostico, 1) * 1.1;
  const n = semanas.length;
  const x = (i) => L + (i * (w - L - 14)) / Math.max(1, n - 1);
  const y = (v) => h - B - (v / max) * (h - B - T);
  const linea = (arr) => arr.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="220">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={L} y1={y(max * f)} x2={w - 10} y2={y(max * f)} stroke="#e3e9ef" />
          <text x={6} y={y(max * f) + 4} fontSize="10" fill="#6b7c8c">{nf(max * f)}</text>
        </g>
      ))}
      <polyline points={linea(pronostico)} fill="none" stroke="#ef6c00" strokeWidth="2.5" strokeDasharray="7,5" />
      <polyline points={linea(real)} fill="none" stroke="#2e86ab" strokeWidth="3" />
      {real.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill="#2e86ab" />)}
      {semanas.map((s, i) => (
        <text key={s} x={x(i)} y={h - 8} fontSize="9" fill="#6b7c8c" textAnchor="middle">{corta(s)}</text>
      ))}
      <rect x={w - 190} y={2} width="14" height="4" fill="#2e86ab" />
      <text x={w - 170} y={8} fontSize="10" fill="#22303f">Ventas reales</text>
      <rect x={w - 90} y={2} width="14" height="4" fill="#ef6c00" />
      <text x={w - 70} y={8} fontSize="10" fill="#22303f">Pronóstico</text>
    </svg>
  );
}

function Barras({ items }) {
  const w = 560, h = 180, L = 20, B = 34, T = 22;
  const max = Math.max(...items.map((r) => r.pronostico_semana_siguiente), 1);
  const bw = (w - L - 20) / items.length - 12;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="180">
      <text x={L} y={14} fontSize="10" fill="#6b7c8c">Naranja = ajustar · Rojo = faltará · Azul = sobra</text>
      {items.map((r, i) => {
        const s = semaforo(r);
        const color = s.txt === "Faltará" ? "#c62828" : s.txt === "Sobra" ? "#2e86ab" : "#ef6c00";
        const alto = (r.pronostico_semana_siguiente / max) * (h - B - T);
        const x = L + i * (bw + 12);
        return (
          <g key={r.sku_id}>
            <rect x={x} y={h - B - alto} width={bw} height={alto} fill={color} rx="4" />
            <text x={x + bw / 2} y={h - B + 12} fontSize="9" fill="#6b7c8c" textAnchor="middle">{(r.nombre || "").slice(0, 7)}</text>
            <text x={x + bw / 2} y={h - B - alto - 4} fontSize="9" fill="#22303f" textAnchor="middle">{nf(r.pronostico_semana_siguiente)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Mapa({ puntos, segmentos }) {
  if (!puntos?.length) return null;
  const xs = puntos.map((p) => p.x), ys = puntos.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const w = 560, h = 240, pad = 30;
  const cx = (v) => pad + ((v - minX) / (maxX - minX || 1)) * (w - 2 * pad);
  const cy = (v) => h - pad - ((v - minY) / (maxY - minY || 1)) * (h - 2 * pad);
  const color = (c) => COL[c % COL.length];
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="240">
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#d5dde5" />
        <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="#d5dde5" />
        <text x={w / 2} y={h - 8} fontSize="10" fill="#6b7c8c" textAnchor="middle">Componente principal 1 →</text>
        {puntos.map((p, i) => (
          <circle key={i} cx={cx(p.x)} cy={cy(p.y)} r="3.2" fill={color(p.c)} opacity="0.55" />
        ))}
      </svg>
      <div className="legend">
        {segmentos.map((s) => (
          <span key={s.c}><i style={{ background: color(s.c) }} />{s.nombre}</span>
        ))}
      </div>
    </>
  );
}

function Login({ onToken }) {
  const [email, setEmail] = useState("propietario@mype.pe");
  const [pass, setPass] = useState("Piloto2026!");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState(null);

  async function usarDemo() {
    try {
      const d = await api("/api/v1/auth/demo-code");
      setOtp(d.otp);
      setEmail(d.email);
      setDemo(d);
      setError("");
    } catch {
      setError("El código automático no está habilitado en este despliegue.");
    }
  }

  async function entrar(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await api("/api/v1/auth/login", { method: "POST", body: { email, password: pass, otp } });
      onToken(d.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={entrar}>
        <div className="logo-dot">M</div>
        <h1>MYPE Analytics</h1>
        <p className="sub">Panel de decisiones con datos de tu POS</p>
        <label>Correo del propietario</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        <label>Contraseña</label>
        <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} autoComplete="current-password" />
        <label>Código de verificación (MFA)</label>
        <div className="mfa-row">
          <input value={otp} onChange={(e) => setOtp(e.target.value)} maxLength={6} inputMode="numeric" placeholder="000000" />
        </div>
        <button className="btn-login" type="submit" disabled={busy}>{busy ? "Verificando…" : "Ingresar al panel"}</button>
        <button className="btn-ghost" type="button" onClick={usarDemo}>Obtener código de acceso</button>
        {demo ? <p className="login-note">Código válido {demo.expira_en}s</p> : null}
        {error ? <p className="login-error">{error}</p> : null}
        <p className="login-note">Acceso protegido con autenticación multifactor · Ley N° 29733</p>
      </form>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState("");
  const [page, setPage] = useState("panel");
  const [dash, setDash] = useState(null);
  const [fc, setFc] = useState([]);
  const [seg, setSeg] = useState(null);
  const [serie, setSerie] = useState(null);
  const [mapa, setMapa] = useState(null);
  const [alertas, setAlertas] = useState([]);
  const [conteo, setConteo] = useState({});
  const [filtro, setFiltro] = useState("todos");
  const [modelos, setModelos] = useState(null);
  const [escenarios, setEscenarios] = useState(null);
  const [semanas, setSemanas] = useState(null);
  const [semIdx, setSemIdx] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!token) return;
    setCargando(true);
    setError("");
    Promise.all([
      api("/api/v1/dashboard", { token }),
      api("/api/v1/forecast?limit=500", { token }),
      api("/api/v1/segments", { token }),
      api("/api/v1/series?weeks=8", { token }),
      api("/api/v1/segments/map", { token }),
      api("/api/v1/models", { token }),
      api("/api/v1/scenarios", { token }).catch(() => null),
      api("/api/v1/weeks", { token }).catch(() => null),
    ])
      .then(([d, f, s, se, mp, mo, esc, sem]) => {
        setDash(d);
        setFc(f.items);
        setSeg(s);
        setSerie(se);
        setMapa(mp);
        setModelos(mo);
        setEscenarios(esc);
        if (sem?.semanas?.length) { setSemanas(sem.semanas); setSemIdx(sem.semanas.length - 1); }
        api("/api/v1/alerts/sync", { token, method: "POST" })
          .then(() => api("/api/v1/alerts?limit=200", { token }))
          .then((a) => { setAlertas(a.items || []); setConteo(a.conteo || {}); })
          .catch(() => setAlertas([]));
      })
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false));
  }, [token]);

  useEffect(() => {
    if (!token || semIdx === null) return;
    api(`/api/v1/weeks/${semIdx}`, { token }).then(setDetalle).catch(() => setDetalle(null));
  }, [token, semIdx]);

  if (!token) return <Login onToken={setToken} />;

  const nombre = Object.fromEntries(fc.map((r) => [r.sku_id, r.nombre]));
  const top = fc.slice(0, 10);
  const criticos = [...fc].sort((a, b) => b.prob_quiebre - a.prob_quiebre).slice(0, 3);
  const filasAlerta = filtro === "todos" ? mezclar(alertas) : alertas.filter((a) => (a.tipo || "quiebre") === filtro);
  const rQuiebre = [...fc].sort((a, b) => b.prob_quiebre - a.prob_quiebre)[0];
  const rSobre = [...fc].filter((r) => (r.cobertura ?? 0) > 2.5).sort((a, b) => b.cobertura - a.cobertura)[0];
  const rVenta = [...fc]
    .filter((r) => r.demanda_ultima_semana > 0 && r.pronostico_semana_siguiente < r.demanda_ultima_semana * 0.75)
    .sort((a, b) => a.pronostico_semana_siguiente / a.demanda_ultima_semana - b.pronostico_semana_siguiente / b.demanda_ultima_semana)[0];
  const recientes = [];
  if (rQuiebre) recientes.push({ r: rQuiebre, tipo: "quiebre", ico: "!", bg: "#ffcdd2", cls: "bad", bgc: "bg-bad",
    titulo: `Quiebre próximo: ${rQuiebre.nombre}`,
    detalle: `${queHacer(rQuiebre).txt} · prob. ${nf(Math.min(99, rQuiebre.prob_quiebre * 100), 0)}%` });
  if (rSobre) recientes.push({ r: rSobre, tipo: "sobrestock", ico: "−", bg: "#ffe082", cls: "warn", bgc: "bg-warn",
    titulo: `Sobre-stock: ${rSobre.nombre}`,
    detalle: `Cobertura de ${nf(rSobre.cobertura, 1)} semanas · no reponer` });
  if (rVenta) recientes.push({ r: rVenta, tipo: "venta_baja", ico: "↓", bg: "#bbdefb", cls: "info", bgc: "bg-info",
    titulo: `Venta bajo lo esperado: ${rVenta.nombre}`,
    detalle: `Pronóstico ${nf(rVenta.pronostico_semana_siguiente, 0)} vs ${nf(rVenta.demanda_ultima_semana)} de la semana previa` });
  const totalReal = serie ? serie.real.reduce((a, b) => a + b, 0) : 0;
  const totalPron = serie ? serie.pronostico.reduce((a, b) => a + b, 0) : 0;
  const titulo = {
    panel: ["Panel general", "Resumen de la última semana · compara tus ventas con lo que el modelo pronosticó"],
    pronostico: ["Pronóstico de demanda", "Modelo XGBoost · semáforo: sobra · ajustar compra · faltará"],
    segmentos: ["Mis clientes — Segmentación automática", "K-Means con 12 meses de tickets del POS"],
    alertas: ["Alertas de tu negocio", "Se generan desde el modelo y quedan guardadas en la base"],
  }[page];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <strong>MYPE Analytics</strong>
          <span>Minimarket La Esquina · Comas</span>
        </div>
        {["panel", "pronostico", "segmentos", "alertas"].map((k, i) => (
          <button key={k} className={"nav-btn" + (page === k ? " on" : "")} onClick={() => setPage(k)}>
            {["Panel general", "Pronóstico de demanda", "Mis clientes", "Alertas"][i]}
          </button>
        ))}
        <div className="user">
          <strong>Rosa Quispe</strong>
          Propietaria · Rol: Product Owner
        </div>
        <button className="logout" onClick={() => setToken("")}>Cerrar sesión</button>
      </aside>

      <main className="main">
        <h2 className="page-title">{titulo[0]}</h2>
        <p className="page-sub">{titulo[1]}</p>

        {error ? <div className="error-box">{error}</div> : null}
        {cargando ? <div className="loading">Cargando datos del modelo…</div> : null}

        {page === "panel" && dash ? (
          <>
            <div className="cards">
              <div className="kpi">
                <div className="lbl">Precisión del pronóstico (MAPE)</div>
                <div className="val">{nf(dash.mape, 1)}%</div>
                <div className="hint ok pill bg-ok">Meta &lt; 20% cumplida</div>
              </div>
              <div className="kpi">
                <div className="lbl">Alertas de quiebre</div>
                <div className="val">{dash.alertas_quiebre}</div>
                <div className="hint warn pill bg-warn">Probabilidad ≥ 0,5</div>
              </div>
              <div className="kpi">
                <div className="lbl">SKUs monitoreados</div>
                <div className="val">{dash.skus_monitoreados}</div>
                <div className="hint ok pill bg-ok">Con 26+ semanas de historia</div>
              </div>
              <div className="kpi">
                <div className="lbl">Calidad del clasificador (F1)</div>
                <div className="val">{nf(dash.f1_quiebre, 3)}</div>
                <div className="hint ok pill bg-ok">AUC {nf(dash.auc_quiebre, 3)}</div>
              </div>
            </div>

            {semanas && detalle ? (
              <div className="panel">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <div>
                    <h3 style={{ marginBottom: 2 }}>Simulación semana a semana</h3>
                    <p style={{ fontSize: 12, color: "var(--gris)" }}>Avanza una semana y mira cómo cambian las urgencias y las alertas</p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <button onClick={() => setSemIdx((i) => Math.max(0, i - 1))} disabled={semIdx === 0}
                      style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #d5dde5", background: "#f0f4f8", cursor: "pointer", fontSize: 16 }}>‹</button>
                    <b style={{ minWidth: 130, textAlign: "center" }}>{rango(detalle.semana)}</b>
                    <button onClick={() => setSemIdx((i) => Math.min(semanas.length - 1, i + 1))} disabled={semIdx === semanas.length - 1}
                      style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #d5dde5", background: "#f0f4f8", cursor: "pointer", fontSize: 16 }}>›</button>
                  </div>
                </div>

                <div className="cards" style={{ gridTemplateColumns: "repeat(3, 1fr)", margin: "14px 0" }}>
                  <div className="kpi">
                    <div className="lbl">Alertas de quiebre</div>
                    <div className="val">{detalle.alertas}</div>
                    <div className="hint ok pill bg-ok">de {detalle.total} SKUs</div>
                  </div>
                  <div className="kpi">
                    <div className="lbl">Riesgo máximo</div>
                    <div className="val">{nf(Math.min(99, detalle.critica * 100), 0)}%</div>
                    <div className="hint warn pill bg-warn">probabilidad más alta</div>
                  </div>
                  <div className="kpi">
                    <div className="lbl">Error de la semana (MAPE)</div>
                    <div className="val">{nf(detalle.mape, 1)}%</div>
                    <div className="hint ok pill bg-ok">pronóstico vs. venta real</div>
                  </div>
                </div>

                <table>
                  <thead><tr><th>Urgencia</th><th className="num">Prob.</th><th className="num">Stock</th><th className="num">Pronóstico</th><th>Acción</th></tr></thead>
                  <tbody>
                    {detalle.items.slice(0, 4).map((r) => {
                      const q = queHacer(r);
                      return (
                        <tr key={r.sku_id}>
                          <td><b>{r.nombre}</b></td>
                          <td className="num">{nf(Math.min(99, (r.prob ?? 0) * 100), 0)}%</td>
                          <td className="num">{nf(r.stock)}</td>
                          <td className="num">{nf(r.pronostico, 1)}</td>
                          <td className={q.cls}><b>{q.txt}</b></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                <div style={{ display: "flex", gap: 6, alignItems: "flex-end", height: 64, marginTop: 14 }}>
                  {semanas.map((s, i) => {
                    const tope = Math.max(...semanas.map((x) => x.alertas), 1);
                    return (
                      <button key={s.i} onClick={() => setSemIdx(i)} title={`${rango(s.semana)} · ${s.alertas} alertas`}
                        style={{ flex: 1, height: Math.max(6, (s.alertas / tope) * 56) + "px", border: 0, borderRadius: 4,
                                 background: i === semIdx ? "var(--azul)" : "#9fc3dd", cursor: "pointer" }} />
                    );
                  })}
                </div>
                <p style={{ fontSize: 11, color: "var(--gris)", marginTop: 6 }}>
                  Alertas por semana · clic en una barra para saltar a esa semana
                  {semIdx === semanas.length - 1 ? " · ya estás en la última semana simulada" : ""}
                </p>
              </div>
            ) : null}
            <div className="grid-2">
              <div className="panel">
                <h3>Ventas reales vs. pronóstico — últimas {serie?.semanas.length ?? 0} semanas (unidades)</h3>
                {serie ? <Serie semanas={serie.semanas} real={serie.real} pronostico={serie.pronostico} /> : <div className="loading">Sin serie</div>}
              </div>
              <div className="panel">
                <h3>Alertas recientes</h3>
                {recientes.map((x) => (
                  <div key={x.tipo} className={"alert-item " + x.bgc}>
                    <div className="ico" style={{ background: x.bg }}>{x.ico}</div>
                    <div>
                      <div className={"t " + x.cls}>{x.titulo}</div>
                      <div className="d">{x.detalle}</div>
                    </div>
                  </div>
                ))}
                <button className="btn-login" style={{ background: "#f0f4f8", color: "var(--azul)", fontSize: 13, marginTop: 4 }} onClick={() => setPage("alertas")}>
                  Ver todas las alertas
                </button>
              </div>
            </div>

            <div className="panel">
              <h3>Accesos rápidos</h3>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <button className="btn-login" style={{ width: "auto", padding: "10px 18px", fontSize: 13 }} onClick={() => setPage("pronostico")}>Ver pronóstico</button>
                <button className="btn-login" style={{ width: "auto", padding: "10px 18px", fontSize: 13, background: "#f0f4f8", color: "var(--azul)" }} onClick={() => setPage("segmentos")}>Ver segmentos de clientes</button>
                <button className="btn-login" style={{ width: "auto", padding: "10px 18px", fontSize: 13, background: "#f0f4f8", color: "var(--azul)" }} onClick={() => window.print()}>Exportar reporte</button>
              </div>
            </div>

            {modelos ? (
              <div className="panel">
                <h3>Modelos entrenados</h3>
                <table>
                  <thead><tr><th>Modelo</th><th>Tipo</th><th className="num">Variables</th><th className="num">Árboles</th><th className="num">Clusters</th><th className="num">Umbral</th><th>Entrenado</th></tr></thead>
                  <tbody>
                    {[["demanda", "Demanda"], ["quiebre", "Quiebre"], ["kmeans", "Segmentación"]].map(([k, label]) => {
                      const m = modelos.modelos[k] || {};
                      return (
                        <tr key={k}>
                          <td>{label}</td><td>{m.tipo}</td><td className="num">{m.features}</td>
                          <td className="num">{m.arboles ?? "—"}</td><td className="num">{m.clusters ?? "—"}</td>
                          <td className="num">{m.umbral ?? "—"}</td>
                          <td>{(m.entrenado || "").slice(0, 16).replace("T", " ")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}

            {escenarios?.escenarios ? (
              <div className="panel">
                <h3>Llegada de datos nuevos — reentrenamiento</h3>
                <p style={{ fontSize: 12, color: "var(--gris)", marginBottom: 10 }}>
                  Se simula un cambio de demanda (+{Math.round((escenarios.deriva.factor - 1) * 100)} % desde el {escenarios.deriva.inicio}).
                  Cada fila es un reentrenamiento real con más semanas; la ventana de prueba es la misma para las tres.
                </p>
                <table>
                  <thead>
                    <tr><th>Historial usado</th><th className="num">Filas de entrenamiento</th><th className="num">MAPE</th><th className="num">RMSE</th><th className="num">F1</th><th>Error</th></tr>
                  </thead>
                  <tbody>
                    {escenarios.escenarios.map((e) => {
                      const mejor = Math.max(...escenarios.escenarios.map((x) => x.mape));
                      const color = e.mape > 20 ? "#c62828" : "#2e7d32";
                      return (
                        <tr key={e.id}>
                          <td><b>{e.etiqueta}</b></td>
                          <td className="num">{nf(e.filas_train)}</td>
                          <td className="num" style={{ color, fontWeight: 700 }}>{nf(e.mape, 2)} %</td>
                          <td className="num">{nf(e.rmse, 2)}</td>
                          <td className="num">{nf(e.f1, 3)}</td>
                          <td>
                            <span style={{ display: "inline-block", height: 8, borderRadius: 4, background: color, width: Math.max(2, (e.mape / mejor) * 160) + "px", verticalAlign: "middle" }} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p style={{ fontSize: 11, color: "var(--gris)", marginTop: 10 }}>
                  Con una semana el modelo todavía no se adapta; con dos el MAPE baja a casi la mitad. Así se decide cuándo reentrenar.
                </p>
              </div>
            ) : null}
          </>
        ) : null}

        {page === "pronostico" ? (
          <>
            <div className="panel">
              <table>
                <thead>
                  <tr><th>Producto (SKU)</th><th className="num">Stock hoy</th><th className="num">Venta semanal</th><th className="num">Pronóstico 7 días</th><th>Semáforo</th><th>Qué hacer</th></tr>
                </thead>
                <tbody>
                  {top.map((r) => {
                    const s = semaforo(r);
                    const q = queHacer(r);
                    return (
                      <tr key={r.sku_id}>
                        <td><b>{r.nombre}</b> <span style={{ color: "var(--gris)", fontSize: 11 }}>{r.sku_id}</span></td>
                        <td className="num">{nf(r.stock)}</td>
                        <td className="num">{nf(r.demanda_ultima_semana)}</td>
                        <td className="num">{nf(r.pronostico_semana_siguiente, 1)}</td>
                        <td><span className={"pill " + s.bg + " " + s.cls}>{s.txt}</span></td>
                        <td className={q.cls}><b>{q.txt}</b></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="panel">
              <h3>Demanda pronosticada por producto — próximos 7 días (unidades)</h3>
              <Barras items={top.slice(0, 8)} />
            </div>
          </>
        ) : null}

        {page === "segmentos" && seg ? (
          <>
            <p className="page-sub">{seg.n_clientes ?? seg.n_clientes} clientes en 4 grupos · silueta {nf(seg.silueta, 3)} · ARI {nf(seg.ari_bootstrap, 3)}</p>
            <div className="grid-2b" style={{ marginBottom: 16 }}>
              {seg.segmentos.map((s, i) => (
                <div key={s.cluster} className={"seg-card seg" + ((s.cluster % 4) + 1)}>
                  <h4>{s.segmento}<span className="pct">{nf(s.pct, 1)}%</span></h4>
                  <ul>
                    <li>Clientes <b>{nf(s.n)}</b></li>
                    <li>Ticket promedio <b>S/ {nf(s.ticket_promedio, 1)}</b></li>
                    <li>Frecuencia <b>{nf(s.frecuencia, 1)} / año</b></li>
                    <li>Compras de fin de semana <b>{nf(s.share_finde * 100, 0)}%</b></li>
                    <li>Compras en promoción <b>{nf(s.share_promo * 100, 0)}%</b></li>
                    <li>Idea de promo <b>{s.accion}</b></li>
                  </ul>
                </div>
              ))}
            </div>
            <div className="panel">
              <h3>Mapa de grupos (proyección PCA de 1.248 clientes)</h3>
              {mapa ? <Mapa puntos={mapa.puntos} segmentos={mapa.segmentos} /> : <div className="loading">Sin mapa</div>}
            </div>
          </>
        ) : null}

        {page === "alertas" ? (
          <>
            <div className="grid-2b">
              <div className="panel">
                <h3>Canales activos</h3>
                <div className="alert-item bg-ok">
                  <div className="ico" style={{ background: "#c8e6c9" }}>OK</div>
                  <div><div className="t">WhatsApp activado</div><div className="d">+51 987 654 321 (Rosa)</div></div>
                </div>
                <div className="alert-item bg-ok">
                  <div className="ico" style={{ background: "#c8e6c9" }}>OK</div>
                  <div><div className="t">Correo activado</div><div className="d">rosa.quispe@minimarketlasquina.pe</div></div>
                </div>
                <div className="alert-item" style={{ background: "#f0f4f8" }}>
                  <div className="ico" style={{ background: "#dbe7f1" }} />
                  <div><div className="t" style={{ color: "var(--azul)" }}>Umbral de alerta</div><div className="d">Avisar con probabilidad de quiebre ≥ 0,50</div></div>
                </div>
              </div>
              <div className="panel">
                <h3>Ejemplo de mensaje — WhatsApp</h3>
                <div className="wa-chat">
                  <div className="wa-day">HOY</div>
                  {criticos.slice(0, 2).map((r) => (
                    <div key={r.sku_id} className="bubble alerta">
                      <b>Faltará {r.nombre}</b><br />
                      Probabilidad {nf(Math.min(99, r.prob_quiebre * 100), 0)}% · stock actual {nf(r.stock)} unid. {queHacer(r).txt}.
                      <span className="time">7:02 a. m.</span>
                    </div>
                  ))}
                  <div className="bubble info">
                    <b>Reporte semanal listo</b><br />
                    Ventas de la semana <b>{nf(totalReal)}</b> unid. (pronóstico: {nf(totalPron)}). Precisión del modelo: {nf(100 - dash.mape, 1)}%.
                    <span className="time">7:03 a. m.</span>
                  </div>
                  <div className="bubble ok-msg">
                    <b>Resumen del sistema</b><br />
                    {alertas.length} alertas guardadas · modelo {dash.modelo_quiebre} · umbral de decisión activo.
                    <span className="time">7:03 a. m.</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="panel">
              <h3>Historial de alertas — base de datos</h3>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                {[["todos", "Todas"], ["quiebre", "Quiebre"], ["sobrestock", "Sobre-stock"], ["venta_baja", "Venta baja"]].map(([k, label]) => {
                  const n = k === "todos" ? Object.values(conteo).reduce((x, y) => x + y, 0) : (conteo[k] || 0);
                  const activo = filtro === k;
                  return (
                    <button key={k} onClick={() => setFiltro(k)}
                      style={{ cursor: "pointer", border: "1px solid #d5dde5", borderRadius: 999, padding: "5px 12px", fontSize: 12, fontWeight: 700,
                               background: activo ? "var(--azul)" : "#f0f4f8", color: activo ? "#fff" : "var(--azul)" }}>
                      {label} · {n}
                    </button>
                  );
                })}
              </div>
              <table>
                <thead><tr><th>Fecha</th><th>Tipo</th><th>Producto</th><th>Mensaje</th><th>Estado</th></tr></thead>
                <tbody>
                  {filasAlerta.length === 0 ? (
                    <tr><td colSpan="5" style={{ color: "var(--gris)" }}>Sin alertas de este tipo.</td></tr>
                  ) : filasAlerta.slice(0, 12).map((a) => (
                    <tr key={a.id}>
                      <td>{(a.creado || "").slice(0, 10)}</td>
                      <td><span className={"pill " + (TIPOS[a.tipo] || (a.severidad === "alta" ? TIPOS.quiebre : TIPOS.venta_baja))[1]}>{(TIPOS[a.tipo] || (a.severidad === "alta" ? TIPOS.quiebre : TIPOS.venta_baja))[0]}</span></td>
                      <td>{nombre[a.sku_id] || a.sku_id}</td>
                      <td>{a.detalle || `Probabilidad ${nf(Math.min(99, a.prob_quiebre * 100), 0)}% de faltar stock`}</td>
                      <td>{a.estado === "abierta" ? "Abierta" : a.estado}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p style={{ fontSize: 11, color: "var(--gris)", marginTop: 10 }}>Mostrando {Math.min(12, filasAlerta.length)} de {filasAlerta.length} · en «Todas» se muestran mezcladas para que se vean los tres tipos</p>
            </div>
          </>
        ) : null}

      </main>
    </div>
  );
}
