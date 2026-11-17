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
from xgboost import XGBClassifier, XGBRegressor
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)

RAW = ROOT / "demo_work" / "raw"
WORK = ROOT / "demo_work"
TOTAL = 6
NUM = ["lag_1", "lag_2", "lag_4", "ma_4", "ma_8", "sd_4", "sd_8", "media_hist",
       "promo_share", "promo_sku_next", "desc_sku_next", "promo_share_next", "descuento_prom",
       "desc_next", "feriado_next", "stock", "quiebre_prev", "cobertura",
       "precio", "lead_time", "vida_util", "categoria", "mes", "semana_anio", "tendencia"]


def X_of(df):
    return np.nan_to_num(df[NUM].fillna(0.0).to_numpy(float), posinf=1e3, neginf=0.0)


def mape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    pos = y > 0
    return float(np.mean(np.abs(y[pos] - p[pos]) / y[pos]) * 100)


def cargar():
    raw = features.load_raw(str(RAW))
    df, *_ = features.build_model_table(raw)
    df = df[df["semanas_con_venta"] >= 26].reset_index(drop=True)
    df["periodo"] = pd.PeriodIndex(df["semana"], freq="W-MON").start_time.strftime("%Y-%m")
    tr = df[df.periodo <= "2026-07"]
    va = df[(df.periodo >= "2026-08") & (df.periodo <= "2026-09")]
    te = df[df.periodo >= "2026-10"]
    return df, tr, va, te


def curva(evals, clave, etiqueta, cada=50, ancho=34):
    serie = evals[clave]
    picos = max(serie) or 1
    rondas = list(range(cada, len(serie) + 1, cada)) or [len(serie)]
    for r in rondas:
        idx = r - 1
        valor = serie[idx]
        ui.p("   %5d  %s  %8.3f" % (r, ui.barra(valor, picos, ancho, etiqueta[1]), valor))
        ui.dormir(0.03)


def main():
    ui.titulo("3. XGBoost entrenando en vivo", "Cómo el boosting corrige sus errores ronda a ronda")
    if not (RAW / "dataset.json").exists():
        ui.error("Falta demo_work/raw. Corre 01 y 02 primero.")
        return

    ui.paso(1, TOTAL, "Preparar las matrices", "1 fila = 1 SKU en 1 semana, 25 variables")
    df, tr, va, te = cargar()
    Xtr, ytr = X_of(tr), tr["y_demanda"].to_numpy(float)
    Xva, yva = X_of(va), va["y_demanda"].to_numpy(float)
    Xte, yte = X_of(te), te["y_demanda"].to_numpy(float)
    ui.ok(f"train {Xtr.shape[0]:,} × {Xtr.shape[1]}   ·   val {Xva.shape[0]:,}   ·   test {Xte.shape[0]:,}")

    ui.p()
    ui.paso(2, TOTAL, "Entrenar y mirar la curva", "Cada árbol aprende de los errores del anterior")
    modelo = XGBRegressor(n_estimators=600, learning_rate=0.05, max_depth=5, subsample=0.85,
                          colsample_bytree=0.9, objective="count:poisson", eval_metric=["rmse"],
                          n_jobs=4, random_state=20261116, tree_method="hist")
    modelo.fit(Xtr, ytr, eval_set=[(Xtr, ytr), (Xva, yva)], verbose=False)
    ev = modelo.evals_result()
    ui.p("   ronda   train RMSE                                  val RMSE", "bold")
    ui.p("   %5d   %s  %8.3f" % (1, ui.barra(ev["validation_0"]["rmse"][0], max(ev["validation_0"]["rmse"]), 34, "green"), ev["validation_0"]["rmse"][0]))
    for r in range(50, 601, 50):
        i = r - 1
        ui.p("   %5d   %s  %8.3f" % (r, ui.barra(ev["validation_0"]["rmse"][i], max(ev["validation_0"]["rmse"]), 34, "green"), ev["validation_0"]["rmse"][i]))
        ui.dormir(0.02)
    ui.p()
    ui.ok(f"RMSE final en prueba: {np.sqrt(np.mean((modelo.predict(Xte) - yte) ** 2)):.2f} unidades")
    ui.info(f"MAPE en prueba: {mape(yte, modelo.predict(Xte)):.1f} %   ·   baseline promedio móvil: {mape(yte, te['ma_4']):.1f} %")

    ui.p()
    ui.paso(3, TOTAL, "Qué pasa cuando entra más historia", "Reentrenar con las semanas nuevas reduce el error")
    parcial = tr[tr.periodo <= "2026-01"]
    m1 = XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=5, subsample=0.85,
                      objective="count:poisson", n_jobs=4, random_state=20261116, tree_method="hist")
    m1.fit(X_of(parcial), parcial["y_demanda"].to_numpy(float))
    mape_viejo = mape(yva, m1.predict(Xva))
    mape_nuevo = mape(yva, modelo.predict(Xva))
    ui.p("   con %2d semanas de entrenamiento  →  MAPE val %5.1f %%   %s" % (parcial.semana.nunique(), mape_viejo, ui.barra(mape_viejo, 40, 20, "yellow")))
    ui.p("   con %2d semanas de entrenamiento  →  MAPE val %5.1f %%   %s" % (tr.semana.nunique(), mape_nuevo, ui.barra(mape_nuevo, 40, 20, "green")))
    if mape_nuevo < mape_viejo:
        ui.ok(f"Al añadir {tr.semana.nunique() - parcial.semana.nunique()} semanas nuevas el error baja {mape_viejo - mape_nuevo:.1f} puntos")
    else:
        ui.alerta(f"Con más semanas el error sube {mape_nuevo - mape_viejo:.1f} puntos: más historia no siempre es mejor si el patrón cambia")
    ui.info("Así se retroalimenta el sistema: cada semana de ventas entra al histórico y se reentrena.")

    ui.p()
    ui.paso(4, TOTAL, "Qué variables pesan", "Importancia por ganancia del árbol")
    imp = sorted(zip(NUM, modelo.feature_importances_), key=lambda t: -t[1])[:10]
    for nombre, valor in imp:
        ui.p("   %-20s %s %5.1f %%" % (nombre, ui.barra(valor, imp[0][1], 30, "cyan"), valor * 100))
        ui.dormir(0.03)

    ui.p()
    ui.paso(5, TOTAL, "El segundo modelo: riesgo de quiebre", "Mismo XGBoost, ahora clasificando")
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    clf = XGBClassifier(n_estimators=400, learning_rate=0.05, max_depth=4, subsample=0.85,
                        scale_pos_weight=spw, eval_metric=["auc", "logloss"],
                        n_jobs=4, random_state=20261116, tree_method="hist")
    clf.fit(Xtr, tr["y_quiebre"].to_numpy(int), eval_set=[(Xva, va["y_quiebre"].to_numpy(int))], verbose=False)
    evc = clf.evals_result()["validation_0"]["auc"]
    ui.p("   ronda   AUC validación", "bold")
    for r in range(50, 401, 50):
        ui.p("   %5d   %s %6.3f" % (r, ui.barra(evc[r - 1], 1.0, 30, "magenta"), evc[r - 1]))
        ui.dormir(0.02)
    pv = clf.predict_proba(Xva)[:, 1]
    mejor_thr, mejor_f1 = 0.5, -1
    for thr in np.arange(0.2, 0.81, 0.01):
        f = f1_score(va["y_quiebre"], (pv >= thr).astype(int), zero_division=0)
        if f > mejor_f1:
            mejor_thr, mejor_f1 = float(thr), f
    pt = clf.predict_proba(Xte)[:, 1]
    pred = (pt >= mejor_thr).astype(int)
    cm = confusion_matrix(te["y_quiebre"].to_numpy(int), pred)
    ui.p()
    ui.p(f"  umbral elegido en validación: {mejor_thr:.2f}   ·   positivos en prueba: {int(te['y_quiebre'].sum())} de {len(te)}")
    ui.p(f"  matriz de confusión:  TN={cm[0,0]}  FP={cm[0,1]}  FN={cm[1,0]}  TP={cm[1,1]}")
    ui.p(f"  precision={precision_score(te['y_quiebre'], pred, zero_division=0):.3f}  recall={recall_score(te['y_quiebre'], pred, zero_division=0):.3f}  "
         f"F1={f1_score(te['y_quiebre'], pred, zero_division=0):.3f}  AUC={roc_auc_score(te['y_quiebre'], pt):.3f}")

    ui.p()
    ui.paso(6, TOTAL, "Guardar y ver una predicción", "Los modelos quedan en demo_work/")
    joblib.dump({"model": modelo, "log_target": False, "features": NUM, "objetivo": "demanda_semanal",
                 "algoritmo": "XGBoost (poisson)", "perfil": "demo"}, WORK / "modelo_demanda.joblib")
    joblib.dump({"model": clf, "features": NUM, "threshold": round(mejor_thr, 2),
                 "objetivo": "quiebre_semana", "algoritmo": "XGBoost", "perfil": "demo"}, WORK / "modelo_quiebre.joblib")
    ui.ok("demo_work/modelo_demanda.joblib")
    ui.ok("demo_work/modelo_quiebre.joblib")
    ui.p()
    ui.p("  Última semana observada → pronóstico de la siguiente", "bold")
    ult = df[df.semana == df.semana.max()].copy()
    ult["pronostico"] = np.clip(modelo.predict(X_of(ult)), 0, None)
    ult["prob"] = clf.predict_proba(X_of(ult))[:, 1]
    top = ult.sort_values("pronostico", ascending=False).head(5)
    ui.tabla(["SKU", "Semana pasada", "Pronóstico", "Prob. quiebre"],
             [[r["sku_id"], int(r["y_demanda"]), round(r["pronostico"], 1), f'{r["prob"]:.2f}'] for _, r in top.iterrows()],
             alinear=["<", ">", ">", ">"])
    ui.p()
    ui.ok("Siguiente: 04_kmeans.py  →  ver los segmentos formándose")


if __name__ == "__main__":
    main()
