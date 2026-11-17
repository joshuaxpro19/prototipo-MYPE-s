import json
import os
import joblib
from datetime import datetime, timezone

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select, update

from .db import alerts, audit, init_db, make_engine, users
import time
from .security import make_token, read_token, totp_code, verify_password, verify_totp

bearer = HTTPBearer(auto_error=False)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class LoginIn(BaseModel):
    email: str
    password: str
    otp: str


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


class Cache:
    def __init__(self):
        self.url = os.environ.get("REDIS_URL")
        self.client = None
        if self.url:
            try:
                import redis
                self.client = redis.from_url(self.url, decode_responses=True)
                self.client.ping()
            except Exception:
                self.client = None

    def get(self, key):
        if not self.client:
            return None
        try:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set(self, key, value, ttl=60):
        if not self.client:
            return
        try:
            self.client.setex(key, ttl, json.dumps(value, default=str))
        except Exception:
            pass


def create_app():
    art_dir = os.environ.get("ARTIFACTS_DIR", os.path.join(ROOT, "artifacts"))
    secret = os.environ.get("JWT_SECRET", "dev-secret-cambiar")
    seed_email = (os.environ.get("ADMIN_EMAIL") or "propietario@mype.pe").strip()
    seed_password = (os.environ.get("ADMIN_PASSWORD") or "Piloto2026!").strip()
    seed_totp = (os.environ.get("ADMIN_TOTP_SECRET") or "JBSWY3DPEHPK3PXP").strip()
    umbral_alerta = float(os.environ.get("ALERT_THRESHOLD", "0.5"))

    state = {"forecast": None, "metrics": None, "segments": None, "plan": None}
    engine = make_engine()
    cache = Cache()

    app = FastAPI(title="API MYPE - Pronostico y Reposicion", version="1.3.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def fresh(path):
        try:
            return os.path.getmtime(path), True
        except FileNotFoundError:
            return 0, False

    def artifacts():
        fc_path = os.path.join(art_dir, "forecast_ultima_semana.csv")
        if state["forecast"] is None or state.get("_mt") != fresh(fc_path)[0]:
            if not os.path.exists(fc_path):
                raise HTTPException(status_code=503, detail="artefactos no disponibles: ejecute ml/train.py")
            state["forecast"] = pd.read_csv(fc_path)
            state["metrics"] = load_json(os.path.join(art_dir, "metricas.json"), {})
            state["segments"] = load_json(os.path.join(art_dir, "metricas.json"), {}).get("clustering", {})
            state["plan"] = load_json(os.path.join(art_dir, "plan_compra.json"), [])
            state["_mt"] = fresh(fc_path)[0]
        return state

    def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
        if cred is None:
            raise HTTPException(status_code=401, detail="token requerido")
        payload = read_token(cred.credentials, secret)
        if payload is None:
            raise HTTPException(status_code=401, detail="token invalido o expirado")
        return payload

    @app.on_event("startup")
    def startup():
        init_db(engine, seed_email, seed_password, seed_totp)
        try:
            artifacts()
        except HTTPException:
            pass

    @app.get("/health")
    def health():
        mt, ok = fresh(os.path.join(art_dir, "metricas.json"))
        commit = (os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "local")[:7]
        return {"status": "ok", "modelos": ok, "cache": bool(cache.client),
                "commit": commit, "hora": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/v1/auth/demo-code")
    def demo_code():
        if os.environ.get("DEMO_MODE") != "1":
            raise HTTPException(status_code=404, detail="no disponible")
        restante = 30 - int(time.time()) % 30
        return {"email": seed_email, "otp": totp_code(seed_totp), "expira_en": restante}
    @app.post("/api/v1/auth/login")
    def login(body: LoginIn):
        with engine.begin() as conn:
            row = conn.execute(select(users).where(users.c.email == body.email)).mappings().first()
            if not row or not row["activo"] or not verify_password(body.password, row["password_hash"]):
                raise HTTPException(status_code=401, detail="credenciales invalidas")
            if not verify_totp(row["totp_secret"], body.otp):
                raise HTTPException(status_code=401, detail="codigo TOTP invalido")
            conn.execute(audit.insert().values(ts=datetime.now(timezone.utc), actor=row["email"], accion="login", detalle="mfa ok"))
        token = make_token(row["email"], row["role"], secret)
        return {"access_token": token, "token_type": "bearer", "expires_in": 900, "role": row["role"]}

    @app.get("/api/v1/metrics")
    def metrics(actor=Depends(current_user)):
        cached = cache.get("metrics")
        if cached:
            return cached
        m = artifacts()["metrics"]
        cache.set("metrics", m, 60)
        return m

    @app.get("/api/v1/weeks")
    def weeks_index(actor=Depends(current_user)):
        path = os.path.join(art_dir, "semanas.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=503, detail="sin snapshots semanales")
        data = load_json(path, [])
        return {"n": len(data), "semanas": [
            {"i": i, "semana": d["semana"], "alertas": d["alertas"], "critica": d["critica"], "mape": d["mape"]}
            for i, d in enumerate(data)]}

    @app.get("/api/v1/weeks/{idx}")
    def week_detail(idx: int, limit: int = Query(6, ge=1, le=50), actor=Depends(current_user)):
        path = os.path.join(art_dir, "semanas.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=503, detail="sin snapshots semanales")
        data = load_json(path, [])
        if idx < 0 or idx >= len(data):
            raise HTTPException(status_code=404, detail="semana fuera de rango")
        d = data[idx]
        return {"indice": idx, "semana": d["semana"], "alertas": d["alertas"], "critica": d["critica"],
                "mape": d["mape"], "total": len(d["items"]), "items": d["items"][:limit]}
    @app.get("/api/v1/scenarios")
    def scenarios(actor=Depends(current_user)):
        path = os.path.join(art_dir, "escenarios", "resumen.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=503, detail="sin escenarios de reentrenamiento")
        return load_json(path, {})
    @app.get("/api/v1/series")
    def series(weeks: int = Query(8, ge=2, le=20), actor=Depends(current_user)):
        path = os.path.join(art_dir, "forecast_test.csv")
        if not os.path.exists(path):
            raise HTTPException(status_code=503, detail="sin serie historica")
        df = pd.read_csv(path)
        agg = df.groupby("semana").agg(real=("y_demanda", "sum"), pronostico=("pronostico", "sum")).reset_index()
        agg = agg.tail(weeks)
        return {"semanas": agg["semana"].tolist(),
                "real": [round(float(v), 1) for v in agg["real"]],
                "pronostico": [round(float(v), 1) for v in agg["pronostico"]]}

    @app.get("/api/v1/segments/map")
    def segments_map(limit: int = Query(600, ge=100, le=1300), actor=Depends(current_user)):
        path = os.path.join(art_dir, "clientes_pca.csv")
        if not os.path.exists(path):
            raise HTTPException(status_code=503, detail="sin mapa de clientes")
        df = pd.read_csv(path)
        if len(df) > limit:
            df = df.sample(limit, random_state=7)
        seg = {s["cluster"]: s["segmento"] for s in artifacts()["metrics"].get("clustering", {}).get("segmentos", [])}
        return {"puntos": [{"x": round(float(r.x), 3), "y": round(float(r.y), 3), "c": int(r.cluster),
                            "s": seg.get(int(r.cluster), "")} for r in df.itertuples()],
                "segmentos": [{"c": c, "nombre": n} for c, n in sorted(seg.items())]}
    @app.get("/api/v1/models")
    def models_info(actor=Depends(current_user)):
        files = {"demanda": "modelo_demanda.joblib", "quiebre": "modelo_quiebre.joblib", "kmeans": "kmeans.joblib"}
        out = {}
        for key, fname in files.items():
            path = os.path.join(art_dir, fname)
            if not os.path.exists(path):
                out[key] = {"cargado": False}
                continue
            mt = os.path.getmtime(path)
            cache_key = "model:" + fname
            cached = state.get(cache_key)
            if cached is None or cached[0] != mt:
                obj = joblib.load(path)
                m = obj["model"] if isinstance(obj, dict) else obj
                cached = (mt, {
                    "cargado": True,
                    "tipo": type(m).__name__,
                    "algoritmo": obj.get("algoritmo") if isinstance(obj, dict) else None,
                    "features": int(len(obj.get("features", []))) if isinstance(obj, dict) else int(getattr(m, "n_features_in_", 0)),
                    "arboles": int(getattr(m, "n_estimators", 0)) or None,
                    "clusters": int(getattr(m, "n_clusters", 0)) or None,
                    "umbral": obj.get("threshold") if isinstance(obj, dict) else None,
                    "entrenado": datetime.fromtimestamp(mt, timezone.utc).isoformat(),
                })
                state[cache_key] = cached
            out[key] = cached[1]
        return {"perfil": artifacts()["metrics"].get("perfil"), "modelos": out}
    @app.get("/api/v1/dashboard")
    def dashboard(actor=Depends(current_user)):
        s = artifacts()
        fc = s["forecast"]
        m = s["metrics"]
        reg = [r for r in m.get("regresion", {}).get("tabla", []) if r["modelo"] == m.get("regresion", {}).get("elegido")]
        alertas = fc[fc["prob_quiebre"] >= umbral_alerta]
        return {
            "skus_monitoreados": int(len(fc)),
            "demanda_semanal_proyectada": round(float(fc["pronostico_semana_siguiente"].sum()), 1),
            "alertas_quiebre": int(len(alertas)),
            "alerta_critica": round(float(fc["prob_quiebre"].max()), 3),
            "modelo_demanda": m.get("regresion", {}).get("elegido"),
            "wape": reg[0]["WAPE"] if reg else None,
            "mae": reg[0]["MAE"] if reg else None,
            "mape": reg[0]["MAPE"] if reg else None,
            "silueta": m.get("clustering", {}).get("silueta"),
            "modelo_quiebre": m.get("clasificacion", {}).get("elegido"),
            "f1_quiebre": next((r["f1"] for r in m.get("clasificacion", {}).get("tabla", []) if r["modelo"] == m.get("clasificacion", {}).get("elegido")), None),
            "auc_quiebre": next((r["roc_auc"] for r in m.get("clasificacion", {}).get("tabla", []) if r["modelo"] == m.get("clasificacion", {}).get("elegido")), None),
            "generado": m.get("generado"),
            "dataset": m.get("dataset", {}).get("naturaleza"),
            "perfil": m.get("perfil"),
            "calibracion": m.get("calibracion", {}).get("nota"),
        }

    @app.get("/api/v1/forecast")
    def forecast(limit: int = Query(20, ge=1, le=500), q: str | None = None, actor=Depends(current_user)):
        fc = artifacts()["forecast"]
        if q:
            mask = fc["sku_id"].str.contains(q, case=False) | fc["nombre"].astype(str).str.contains(q, case=False)
            fc = fc[mask]
        cols = ["sku_id", "nombre", "categoria", "demanda_ultima_semana",
                "pronostico_semana_siguiente", "prob_quiebre", "precio", "stock", "cobertura"]
        rows = fc.head(limit)[[c for c in cols if c in fc.columns]]
        return {"n": int(len(rows)), "items": rows.round(3).to_dict(orient="records")}

    @app.get("/api/v1/forecast/{sku_id}")
    def forecast_sku(sku_id: str, actor=Depends(current_user)):
        fc = artifacts()["forecast"]
        hit = fc[fc["sku_id"] == sku_id]
        if hit.empty:
            raise HTTPException(status_code=404, detail="SKU no encontrado")
        return hit.round(3).to_dict(orient="records")[0]

    @app.get("/api/v1/segments")
    def segments(actor=Depends(current_user)):
        s = artifacts()["segments"]
        return {
            "algoritmo": s.get("elegido"),
            "silueta": s.get("silueta"),
            "ari_bootstrap": s.get("ari_bootstrap"),
            "n_clientes": s.get("n_clientes"),
            "segmentos": s.get("segmentos", []),
        }

    @app.get("/api/v1/purchase-plan")
    def purchase_plan(top: int = Query(20, ge=1, le=50), actor=Depends(current_user)):
        plan = artifacts()["plan"][:top]
        return {"n": len(plan), "costo_total": round(sum(p.get("costo") or 0 for p in plan), 2),
                "items": [{"sku_id": p["sku_id"], "nombre": p["nombre"], "categoria": p["categoria"],
                           "lead_time_dias": p["lead_time_dias"], "costo": p["costo"],
                           "pedido_semana": p["plan"][0]["pedido"] if p.get("plan") else None} for p in plan]}

    @app.get("/api/v1/alerts")
    def list_alerts(estado: str = Query("abierta"), tipo: str | None = None,
                    limit: int = Query(50, ge=1, le=200), actor=Depends(current_user)):
        with engine.begin() as conn:
            q = select(alerts).where(alerts.c.estado == estado)
            if tipo:
                q = q.where(alerts.c.tipo == tipo)
            rows = conn.execute(q.order_by(alerts.c.prob_quiebre.desc())).mappings().all()
            conteo = conn.execute(
                select(alerts.c.tipo, func.count()).where(alerts.c.estado == estado).group_by(alerts.c.tipo)
            ).all()
        return {"n": len(rows), "items": [dict(r) for r in rows][:limit],
                "conteo": {(t or "quiebre"): int(c) for t, c in conteo}}

    @app.post("/api/v1/alerts/sync")
    def sync_alerts(actor=Depends(current_user)):
        fc = artifacts()["forecast"]
        candidatas = []
        for _, r in fc.iterrows():
            if r["prob_quiebre"] >= umbral_alerta:
                candidatas.append((r["sku_id"], float(r["prob_quiebre"]),
                                   "alta" if r["prob_quiebre"] >= 0.75 else "media",
                                   "quiebre", "Probabilidad %d%% de faltar stock en 7 días" % min(99, round(r["prob_quiebre"] * 100))))
        cobert = fc[fc["cobertura"].fillna(0) > 2.5].sort_values("cobertura", ascending=False).head(8)
        for _, r in cobert.iterrows():
            candidatas.append((r["sku_id"], float(r["prob_quiebre"]), "baja", "sobrestock",
                               "Cobertura de %.1f semanas; no reponer esta semana" % r["cobertura"]))
        venta_baja = fc[(fc["pronostico_semana_siguiente"] < fc["demanda_ultima_semana"] * 0.75)].head(5)
        for _, r in venta_baja.iterrows():
            candidatas.append((r["sku_id"], float(r["prob_quiebre"]), "baja", "venta_baja",
                               "Venta esperada %.0f unid. frente a %.0f de la semana previa" % (
                                   r["pronostico_semana_siguiente"], r["demanda_ultima_semana"])))
        creadas = 0
        with engine.begin() as conn:
            for sku_id, prob, sev, tipo, detalle in candidatas:
                exists = conn.execute(select(alerts.c.id).where((alerts.c.sku_id == sku_id) & (alerts.c.estado == "abierta"))).first()
                if not exists:
                    conn.execute(alerts.insert().values(sku_id=sku_id, prob_quiebre=prob, severidad=sev,
                                                        tipo=tipo, detalle=detalle, estado="abierta",
                                                        creado=datetime.now(timezone.utc)))
                    creadas += 1
            conn.execute(audit.insert().values(ts=datetime.now(timezone.utc), actor=actor["sub"], accion="sync_alerts", detalle=str(creadas)))
        return {"creadas": creadas, "evaluadas": len(candidatas)}

    @app.post("/api/v1/alerts/{alert_id}/ack")
    def ack_alert(alert_id: int, actor=Depends(current_user)):
        with engine.begin() as conn:
            res = conn.execute(update(alerts).where(alerts.c.id == alert_id).values(estado="atendida", atendido_por=actor["sub"]))
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="alerta no encontrada")
            conn.execute(audit.insert().values(ts=datetime.now(timezone.utc), actor=actor["sub"], accion="ack_alert", detalle=str(alert_id)))
        return {"id": alert_id, "estado": "atendida"}

    front = os.environ.get("FRONTEND_DIR")
    if front and os.path.isdir(front):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=front, html=True), name="front")

    return app


app = create_app()

