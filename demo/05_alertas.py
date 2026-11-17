import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "ml"))

import joblib
import numpy as np
import pandas as pd
import ui
import features
import planning

RAW = ROOT / "demo_work" / "raw"
WORK = ROOT / "demo_work"
TOTAL = 6


def main():
    ui.titulo("5. De los modelos a la decisión", "Qué reponer, qué no comprar y qué avisar en el panel")
    faltan = [p.name for p in (WORK / "modelo_demanda.joblib", WORK / "modelo_quiebre.joblib") if not p.exists()]
    if faltan:
        ui.error("Faltan modelos: " + ", ".join(faltan) + ". Corre 03_xgboost.py primero.")
        return

    ui.paso(1, TOTAL, "Cargar los modelos ya entrenados", "Los mismos que sirve la API")
    reg = joblib.load(WORK / "modelo_demanda.joblib")
    clf = joblib.load(WORK / "modelo_quiebre.joblib")
    NUM = reg["features"]
    ui.ok(f"demanda : {type(reg['model']).__name__} · {reg['model'].n_estimators} árboles")
    ui.ok(f"quiebre : {type(clf['model']).__name__} · umbral {clf['threshold']}")

    ui.p()
    ui.paso(2, TOTAL, "Predecir la semana siguiente", "Solo con datos hasta la última semana observada")
    raw = features.load_raw(str(RAW))
    df, *_ = features.build_model_table(raw)
    df = df[df["semanas_con_venta"] >= 26].reset_index(drop=True)
    ultima = df["semana"].max()
    X = np.nan_to_num(df[df.semana == ultima][NUM].fillna(0.0).to_numpy(float), posinf=1e3, neginf=0.0)
    base = df[df.semana == ultima].reset_index(drop=True)
    base["pronostico"] = np.clip(reg["model"].predict(X), 0, None)
    base["prob_quiebre"] = clf["model"].predict_proba(X)[:, 1]
    ui.ok(f"{len(base):,} SKUs pronosticados para la semana posterior a {ultima}")
    ui.info("Nada de esta tabla usa datos de la semana que se predice.")

    ui.p()
    ui.paso(3, TOTAL, "Aplicar las reglas de decisión", "El modelo da números; las reglas dan acciones")
    ui.p("   prob ≥ 0.60 o cobertura < 1.0  → REPONER", "red")
    ui.p("   prob ≥ 0.35                    → REVISAR", "yellow")
    ui.p("   cobertura > 2.5 semanas        → NO COMPRAR", "blue")
    ui.p("   resto                          → MANTENER", "green")
    ui.p()

    def decidir(r):
        if r["prob_quiebre"] >= 0.60 or (np.isfinite(r["cobertura"]) and r["cobertura"] < 1.0):
            return "REPONER", "red"
        if r["prob_quiebre"] >= 0.35:
            return "REVISAR", "yellow"
        if np.isfinite(r["cobertura"]) and r["cobertura"] > 2.5:
            return "NO COMPRAR", "blue"
        return "MANTENER", "green"

    skus = pd.read_csv(RAW / "skus.csv").set_index("sku_id")
    base["nombre"] = base["sku_id"].map(skus["nombre"])
    base["accion"], base["color"] = zip(*base.apply(decidir, axis=1))
    orden = {"REPONER": 0, "REVISAR": 1, "MANTENER": 2, "NO COMPRAR": 3}
    top = base.sort_values(["prob_quiebre"], ascending=False).head(4)
    sobre = base[base.accion == "NO COMPRAR"].sort_values("cobertura", ascending=False).head(2)
    tranquilos = base[base.accion == "MANTENER"].sort_values("pronostico", ascending=False).head(2)
    muestra = pd.concat([top, sobre, tranquilos]).drop_duplicates("sku_id")

    filas = []
    for _, r in muestra.iterrows():
        filas.append([r["nombre"], int(r["y_demanda"]), round(r["pronostico"], 1),
                      f'{r["prob_quiebre"]:.2f}', round(r["cobertura"], 1) if np.isfinite(r["cobertura"]) else "—",
                      ui.c(r["accion"], r["color"])])
    ui.tabla(["Producto", "Venta sem.", "Pronóstico", "Prob. quiebre", "Cobertura", "Acción"], filas,
             alinear=["<", ">", ">", ">", ">", "<"])

    conteo = base["accion"].value_counts()
    ui.p()
    ui.p("   Reparto de decisiones: " + "  ·  ".join(
        ui.c("%s %d" % (k, v), {"REPONER": "red", "REVISAR": "yellow", "MANTENER": "green", "NO COMPRAR": "blue"}[k])
        for k, v in conteo.items()))

    ui.p()
    ui.paso(4, TOTAL, "El plan de compra con A*", "Cuánto pedir cada semana para minimizar costo")
    pronosticos = dict(zip(base["sku_id"], base["pronostico"]))
    for sku_id in top["sku_id"].head(3):
        row = skus.loc[sku_id].copy()
        row["sku_id"] = sku_id
        demanda = [max(float(pronosticos[sku_id]), 0.1)] * 4
        plan = planning.plan_sku(demanda, row, stock_inicial=float(min(base.loc[base.sku_id == sku_id, "stock"].iloc[0], 4 * max(demanda))))
        ui.p()
        ui.p(f"  {sku_id} · {row['nombre']} · lead time {int(row['lead_time_dias'])} días · costo plan S/ {plan['costo']}", "bold")
        ui.tabla(["Semana", "Pedido", "Stock final", "Costo"],
                 [[p["semana"], p["pedido"], p["stock_final"], p["costo"]] for p in plan["plan"]],
                 alinear=[">", ">", ">", ">"])

    ui.p()
    ui.paso(5, TOTAL, "Lo mismo que recibe el front", "El JSON exacto de /api/v1/forecast")
    payload = base.sort_values("pronostico", ascending=False).head(2)[
        ["sku_id", "pronostico", "prob_quiebre"]].round(3).to_dict(orient="records")
    ui.p(json.dumps({"n": len(payload), "items": payload}, ensure_ascii=False, indent=2), "cyan")
    ui.info("El dashboard pinta ese JSON en la tabla de pronóstico y en las alertas.")

    ui.p()
    ui.paso(6, TOTAL, "Resumen de la cadena", "")
    ui.arbol("Datos", "18.250 tickets → 127.750 líneas")
    ui.arbol("Features", "SKU × semana, 25 variables sin fuga", es_ultimo=False)
    ui.arbol("XGBoost", "demanda (poisson) + riesgo de quiebre", es_ultimo=False)
    ui.arbol("Reglas + A*", "REPONER / REVISAR / NO COMPRAR y pedido óptimo", es_ultimo=False)
    ui.arbol("Panel", "tabla de pronóstico, alertas y plan de compra")
    ui.p()
    ui.ok("Siguiente: 06_publicar.py  →  entrenar el pipeline completo y verlo en el navegador")


if __name__ == "__main__":
    main()
