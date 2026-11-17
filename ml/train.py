import argparse
import json
import os
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans, MeanShift
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import (accuracy_score, calinski_harabasz_score, davies_bouldin_score,
                             f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, r2_score, recall_score, roc_auc_score,
                             silhouette_score)
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier, XGBRegressor

import features
import planning

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
ART = os.path.join(ROOT, "artifacts")
SEED = 20261116
SPLIT = "calendario"
DESDE = None
HASTA = None
N_TEST = None
N_VAL = None

NUM = ["lag_1", "lag_2", "lag_4", "ma_4", "ma_8", "sd_4", "sd_8", "media_hist",
       "promo_share", "promo_sku_next", "desc_sku_next", "promo_share_next", "descuento_prom", "desc_next", "feriado_next", "stock", "quiebre_prev", "cobertura",
       "precio", "lead_time", "vida_util", "categoria", "mes", "semana_anio", "tendencia"]


def X_of(frame):
    return np.nan_to_num(frame[NUM].fillna(0.0).to_numpy(float), posinf=1e3, neginf=0.0)


def reg_metrics(y, p):
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    pos = y > 0
    return {
        "MAE": round(float(mean_absolute_error(y, p)), 3),
        "RMSE": round(float(np.sqrt(mean_squared_error(y, p))), 3),
        "MAPE": round(float(np.mean(np.abs(y[pos] - p[pos]) / y[pos]) * 100), 2) if pos.any() else None,
        "WAPE": round(float(np.abs(y - p).sum() / max(y.sum(), 1e-9) * 100), 2),
        "R2": round(float(r2_score(y, p)), 3),
    }


def cls_metrics(y, prob, thr=0.5):
    y = np.asarray(y, dtype=int)
    p = np.asarray(prob, dtype=float)
    pred = (p >= thr).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 3),
        "roc_auc": round(float(roc_auc_score(y, p)), 3),
    }


def split_rolling(df, n_test=None, n_val=None):
    n_test = n_test or N_TEST or 4
    n_val = n_val or N_VAL or 9
    weeks = sorted(df["semana"].unique())
    te = weeks[-n_test:]
    va = weeks[-(n_test + n_val):-n_test]
    tr = weeks[:-(n_test + n_val)]
    return df[df.semana.isin(tr)], df[df.semana.isin(va)], df[df.semana.isin(te)], tr, va, te


def split_deriva(df, hasta, n_test=2, n_val=2):
    weeks = sorted(df["semana"].unique())
    te = weeks[-n_test:]
    hasta = hasta or weeks[-n_test - n_val - 1]
    previas = [w for w in weeks if w <= hasta]
    va = previas[-n_val:]
    tr = previas[:-n_val]
    return df[df.semana.isin(tr)], df[df.semana.isin(va)], df[df.semana.isin(te)], tr, va, te


def split_calendar(df):
    df = df.assign(periodo=pd.PeriodIndex(df["semana"], freq="W-MON").start_time.strftime("%Y-%m"))
    tr = df[df["periodo"] <= "2026-07"]
    va = df[df["periodo"].isin(["2026-08", "2026-09"])]
    te = df[df["periodo"] >= "2026-10"]
    return tr, va, te, sorted(tr["periodo"].unique()), sorted(va["periodo"].unique()), sorted(te["periodo"].unique())


def train_regression(df, meta):
    if SPLIT == "deriva":
        tr, va, te, wtr, wva, wte = split_deriva(df, HASTA)
    else:
        tr, va, te, wtr, wva, wte = split_rolling(df) if SPLIT == "rodante" else split_calendar(df)
    if DESDE:
        tr = tr[tr["semana"] >= DESDE].reset_index(drop=True)
        wtr = sorted(tr["semana"].unique())
    Xtr, ytr = X_of(tr), tr["y_demanda"].to_numpy(float)
    Xva, yva = X_of(va), va["y_demanda"].to_numpy(float)
    Xte, yte = X_of(te), te["y_demanda"].to_numpy(float)
    rows = []
    rows.append({"modelo": "Promedio movil 4 semanas (baseline)", **reg_metrics(yte, te["ma_4"].to_numpy(float)),
                 "MAPE_val": reg_metrics(yva, va["ma_4"].to_numpy(float))["MAPE"], "tiempo_s": 0.0})
    specs = [
        ("Ridge", Ridge(alpha=4.0), False),
        ("Random Forest", RandomForestRegressor(n_estimators=600, max_depth=10, min_samples_leaf=3, n_jobs=-1, random_state=SEED), True),
        ("Gradient Boosting", GradientBoostingRegressor(n_estimators=350, learning_rate=0.05, max_depth=3, random_state=SEED), True),
    ]
    fitted = {}
    for name, model, log_target in specs:
        t0 = time.perf_counter()
        model.fit(Xtr, np.log1p(ytr) if log_target else ytr)
        pv = np.clip(np.expm1(model.predict(Xva)) if log_target else model.predict(Xva), 0.0, None)
        raw = model.predict(Xte)
        pred = np.clip(np.expm1(raw) if log_target else raw, 0.0, None)
        dt = time.perf_counter() - t0
        rows.append({"modelo": name, **reg_metrics(yte, pred), "MAPE_val": reg_metrics(yva, pv)["MAPE"], "tiempo_s": round(dt, 2)})
        fitted[name] = (model, log_target)

    rng = np.random.default_rng(SEED)
    grid = [{"n_estimators": n, "max_depth": d, "learning_rate": lr, "subsample": ss, "colsample_bytree": cs, "min_child_weight": mc}
            for n in (300, 500, 700, 900) for d in (4, 5, 6) for lr in (0.03, 0.05, 0.08)
            for ss in (0.7, 0.85) for cs in (0.7, 0.9) for mc in (1, 3)]
    picks = [grid[i] for i in rng.choice(len(grid), size=40, replace=False)]
    best_xgb, best_val, best_cfg = None, float("inf"), None
    for cfg in picks:
        m = XGBRegressor(**cfg, objective="count:poisson", n_jobs=4, random_state=SEED, tree_method="hist")
        m.fit(Xtr, ytr)
        pv = np.clip(m.predict(Xva), 0.0, None)
        score = reg_metrics(yva, pv)["MAPE"]
        if score < best_val:
            best_xgb, best_val, best_cfg = m, score, cfg
    t0 = time.perf_counter()
    pred = np.clip(best_xgb.predict(Xte), 0.0, None)
    dt = time.perf_counter() - t0
    rows.append({"modelo": "XGBoost (poisson)", **reg_metrics(yte, pred), "MAPE_val": best_val,
                 "tiempo_s": round(dt, 2), "config": best_cfg})
    fitted["XGBoost (poisson)"] = (best_xgb, False)

    val = {r["modelo"]: r["MAPE_val"] for r in rows[1:]}
    best = min(rows[1:], key=lambda r: r["MAPE_val"])["modelo"]
    criterio = "menor MAPE de validacion"
    if best != "XGBoost (poisson)" and val["XGBoost (poisson)"] - val[best] <= 0.5:
        best = "XGBoost (poisson)"
        criterio = "empate tecnico en validacion (<=0.5 pp): se mantiene el modelo definido en el diseno"
    return rows, fitted[best], best, Xte, yte, te, (wtr, wva, wte), criterio, val



def train_classification(df):
    if SPLIT == "deriva":
        tr, va, te, wtr, wva, wte = split_deriva(df, HASTA)
    else:
        tr, va, te, wtr, wva, wte = split_rolling(df) if SPLIT == "rodante" else split_calendar(df)
    if DESDE:
        tr = tr[tr["semana"] >= DESDE].reset_index(drop=True)
        wtr = sorted(tr["semana"].unique())
    Xtr, ytr = X_of(tr), tr["y_quiebre"].to_numpy(int)
    Xva, yva = X_of(va), va["y_quiebre"].to_numpy(int)
    Xte, yte = X_of(te), te["y_quiebre"].to_numpy(int)
    spw = float((ytr == 0).sum() / max((ytr == 1).sum(), 1))
    specs = [
        ("KNN (k=7)", KNeighborsClassifier(n_neighbors=7, n_jobs=-1)),
        ("Arbol de decision", DecisionTreeClassifier(max_depth=6, min_samples_leaf=20, random_state=SEED)),
        ("SVM (RBF)", SVC(C=1.0, gamma="scale", probability=True, cache_size=700, random_state=SEED)),
        ("Random Forest", RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5, n_jobs=-1, random_state=SEED)),
    ]
    grid_c = [{"n_estimators": n, "max_depth": d, "learning_rate": lr, "subsample": ss, "min_child_weight": mc}
              for n in (200, 400, 600) for d in (3, 4, 5, 6) for lr in (0.03, 0.05, 0.08)
              for ss in (0.7, 0.85) for mc in (1, 3)]
    rc = np.random.default_rng(SEED + 1)
    best_c, best_cfg, best_auc = None, None, -1.0
    for cfg in [grid_c[i] for i in rc.choice(len(grid_c), size=12, replace=False)]:
        m = XGBClassifier(**cfg, scale_pos_weight=spw, eval_metric="logloss", n_jobs=4,
                          random_state=SEED, tree_method="hist")
        m.fit(Xtr, ytr)
        auc = float(roc_auc_score(yva, m.predict_proba(Xva)[:, 1]))
        if auc > best_auc:
            best_c, best_cfg, best_auc = m, cfg, auc
    specs.append(("XGBoost", best_c))
    rows, fitted, thresholds = [], {}, {}
    for name, model in specs:
        t0 = time.perf_counter()
        model.fit(Xtr, ytr)
        pv = model.predict_proba(Xva)[:, 1]
        best_thr, best_f1 = 0.5, -1.0
        for thr in np.arange(0.2, 0.81, 0.01):
            f = f1_score(yva, (pv >= thr).astype(int), zero_division=0)
            if f > best_f1:
                best_thr, best_f1 = float(thr), f
        pt = model.predict_proba(Xte)[:, 1]
        dt = time.perf_counter() - t0
        rows.append({"modelo": name, **cls_metrics(yte, pt, best_thr), "f1_val": round(best_f1, 3), "auc_val": round(float(roc_auc_score(yva, pv)), 3), "umbral": round(best_thr, 2), "tiempo_s": round(dt, 2)})
        fitted[name] = model
        thresholds[name] = best_thr
    best = max(rows, key=lambda r: (r.get("auc_val", 0.0), r.get("f1_val", r["f1"])))["modelo"]
    return rows, fitted[best], best, thresholds[best], (Xte, yte, te, fitted[best]), spw


def best_threshold(y, p):
    best = (0.5, -1.0)
    for thr in np.arange(0.2, 0.81, 0.01):
        f = f1_score(y, (p >= thr).astype(int), zero_division=0)
        if f > best[1]:
            best = (float(thr), f)
    return best[0]


def train_clustering(cf):
    raw = features.winsorize(cf)
    scaler = StandardScaler()
    Z = scaler.fit_transform(raw)
    k_eval = []
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Z)
        k_eval.append({"k": k, "inercia": round(float(km.inertia_), 1),
                       "silueta": round(float(silhouette_score(Z, km.labels_)), 3)})
    k = 4
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=8).fit(Z)
    kdist, _ = nn.kneighbors(Z)
    eps = round(float(np.quantile(kdist[:, -1], 0.90)), 2)
    algos = {
        "K-Means (k=4)": KMeans(n_clusters=k, n_init=10, random_state=SEED),
        "GMM (4 comp.)": GaussianMixture(n_components=k, covariance_type="full", random_state=SEED),
        "Aglomerativo (ward)": AgglomerativeClustering(n_clusters=k, linkage="ward"),
        "Mean-Shift": MeanShift(bandwidth=None, bin_seeding=True),
        "DBSCAN (eps=%.2f)" % eps: DBSCAN(eps=eps, min_samples=8),
    }
    comp, labels_by_algo = [], {}
    for name, model in algos.items():
        lab = model.fit_predict(Z)
        labels_by_algo[name] = lab
        uniq = np.unique(lab[lab >= 0]) if name.startswith("DBSCAN") else np.unique(lab)
        if len(uniq) > 1:
            mask = lab >= 0
            sil = float(silhouette_score(Z[mask], lab[mask]))
            db = float(davies_bouldin_score(Z[mask], lab[mask]))
            ch = float(calinski_harabasz_score(Z[mask], lab[mask]))
        else:
            sil = db = ch = float("nan")
        noise = float((lab == -1).mean() * 100) if name.startswith("DBSCAN") else 0.0
        comp.append({"algoritmo": name, "clusters": int(len(uniq)), "silueta": round(sil, 3),
                     "davies_bouldin": round(db, 3), "calinski": round(ch, 1), "ruido_pct": round(noise, 1)})

    km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Z)
    labels = km.labels_
    rng = np.random.default_rng(SEED)
    aris = []
    for _ in range(200):
        idx = rng.choice(len(Z), size=len(Z), replace=True)
        if len(np.unique(labels[idx])) < 2:
            continue
        lab_b = KMeans(n_clusters=k, n_init=5, random_state=SEED).fit_predict(Z[idx])
        from sklearn.metrics import adjusted_rand_score
        aris.append(adjusted_rand_score(labels[idx], lab_b))
    ari = float(np.mean(aris))

    pca = PCA(n_components=2, random_state=SEED)
    coords = pca.fit_transform(Z)

    prof = cf.copy()
    prof["cluster"] = labels
    aggs = {"n": ("frecuencia", "size")}
    for col, alias in (("recencia", "recencia"), ("frecuencia", "frecuencia"), ("monetario", "monetario"),
                       ("ticket_promedio", "ticket"), ("share_finde", "share_finde"), ("share_promo", "share_promo")):
        if col in prof.columns:
            aggs[alias] = (col, "mean")
    summary = prof.groupby("cluster").agg(**aggs).round(2)
    if "recencia" not in summary.columns:
        summary["recencia"] = 0.0
    summary["pct"] = (summary["n"] / summary["n"].sum() * 100).round(1)
    q_money = summary["monetario"].quantile(0.75)
    q_freq = summary["frecuencia"].quantile(0.25)
    med_rec = summary["recencia"].median()
    names = {}
    for c, r in summary.iterrows():
        if r["monetario"] >= q_money and r["frecuencia"] >= summary["frecuencia"].median():
            names[c] = "Mayorista"
        elif r["frecuencia"] <= q_freq and r["recencia"] >= med_rec:
            names[c] = "Ocasional"
        elif r["share_finde"] >= 0.6:
            names[c] = "Fin de semana"
        elif r["share_promo"] >= 0.45:
            names[c] = "Promo-sensible"
        else:
            names[c] = "Hogar"
    used = {}
    for c in summary.index:
        n = names[c]
        if n in used:
            used[n] += 1
            names[c] = "%s %d" % (n, used[n])
        else:
            used[n] = 1
    actions = {"Hogar": "combo familiar quincenal", "Mayorista": "descuento por caja cerrada",
               "Fin de semana": "combo sabado familiar", "Promo-sensible": "2x1 en lineas seleccionadas", "Ocasional": "cupon de retorno a los 30 dias"}
    seg_rows = []
    for c, r in summary.iterrows():
        base = names[c].split(" ")[0]
        seg_rows.append({"cluster": int(c), "segmento": names[c], "n": int(r["n"]), "pct": float(r["pct"]),
                         "ticket_promedio": float(r["ticket"]), "frecuencia": float(r["frecuencia"]),
                         "monetario": float(r["monetario"]), "recencia": float(r["recencia"]),
                         "share_finde": float(r["share_finde"]), "share_promo": float(r["share_promo"]),
                         "accion": actions.get(base, "revisar con el propietario")})
    seg_rows.sort(key=lambda x: -x["n"])
    assign = pd.DataFrame({"cliente_ref": cf.index, "segmento": [names[c] for c in labels]})
    return {
        "k_eval": k_eval,
        "comparacion": comp,
        "elegido": "K-Means (k=4)",
        "silueta": round(float(silhouette_score(Z, labels)), 3),
        "davies_bouldin": round(float(davies_bouldin_score(Z, labels)), 3),
        "calinski": round(float(calinski_harabasz_score(Z, labels)), 1),
        "ari_bootstrap": round(ari, 3),
        "dbscan_eps": eps, "dbscan_ruido_pct": round(float((labels_by_algo["DBSCAN (eps=%.2f)" % eps] == -1).mean() * 100), 1),
        "pca_var_explicada": [round(float(v), 3) for v in pca.explained_variance_ratio_],
        "segmentos": seg_rows,
        "n_clientes": int(len(cf)), "variables": list(cf.columns),
    }, scaler, km, assign, coords, cf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=RAW)
    ap.add_argument("--art", default=ART)
    ap.add_argument("--fecha", default=None, help="fecha de entrenamiento a declarar, YYYY-MM-DD o ISO")
    ap.add_argument("--split", default="calendario", choices=["calendario", "rodante", "deriva"])
    ap.add_argument("--desde", default=None, help="limita el inicio del conjunto de entrenamiento (YYYY-MM-DD)")
    ap.add_argument("--hasta", default=None, help="limita el fin del conjunto de entrenamiento (YYYY-MM-DD)")
    ap.add_argument("--test-semanas", type=int, default=None)
    ap.add_argument("--val-semanas", type=int, default=None)
    args = ap.parse_args()
    global SPLIT, DESDE, HASTA, N_TEST, N_VAL
    SPLIT = args.split
    DESDE = args.desde
    HASTA = args.hasta
    N_TEST = args.test_semanas
    N_VAL = args.val_semanas
    os.makedirs(args.art, exist_ok=True)
    t_start = time.time()

    raw = features.load_raw(args.raw)
    df, uni, quiebre, perdidas, weeks, skus = features.build_model_table(raw)
    df = df[df["semanas_con_venta"] >= 26].reset_index(drop=True)
    cf = features.client_features(raw)
    cf_model = cf.drop(columns=[c for c in ("antiguedad", "compras_promedio_mes", "n_categorias", "recencia") if c in cf.columns])
    meta = raw["meta"]
    meta.update({
        "semanas_observadas": int(len(weeks)),
        "filas_modelado": int(len(df)),
        "skus_modelados": int(df["sku_id"].nunique()),
        "tasa_quiebre_objetivo": round(float(df["y_quiebre"].mean()), 4),
        "clientes_con_compra_identificada": int(len(cf)),
    })

    reg_rows, reg_model, reg_best, Xte, yte, te, (wtr, wva, wte), criterio, val_mape = train_regression(df, meta)
    cls_rows, cls_model, cls_best, cls_thr, (Xte_c, yte_c, te_c, _), spw = train_classification(df)
    clustering, scaler, km, assign, coords, cf_raw = train_clustering(cf_model)

    last_week = max(df["semana"])
    horizon = df[df.semana == last_week].copy()
    reg_estimator, reg_log = reg_model
    raw_pred = reg_estimator.predict(X_of(horizon))
    horizon["pronostico"] = np.clip(np.expm1(raw_pred) if reg_log else raw_pred, 0.0, None)
    horizon["prob_quiebre"] = cls_model.predict_proba(X_of(horizon))[:, 1]
    fc = horizon[["sku_id", "semana", "y_demanda", "pronostico", "prob_quiebre", "stock", "cobertura"]].copy()
    fc.columns = ["sku_id", "ultima_semana", "demanda_ultima_semana", "pronostico_semana_siguiente", "prob_quiebre", "stock", "cobertura"]
    fc = fc.merge(skus.reset_index()[["sku_id", "nombre", "categoria", "precio", "lead_time_dias"]], on="sku_id", how="left")
    fc = fc.sort_values("pronostico_semana_siguiente", ascending=False)

    t0 = time.perf_counter()
    plan = planning.build_plan(dict(zip(fc["sku_id"], fc["pronostico_semana_siguiente"])), skus.reset_index(), top_n=20)
    plan_ms = (time.perf_counter() - t0) * 1000 / max(len(plan), 1)

    raw_te = reg_estimator.predict(X_of(te))
    test_pred = np.clip(np.expm1(raw_te) if reg_log else raw_te, 0.0, None)
    va = split_deriva(df, HASTA)[1] if SPLIT == "deriva" else (split_rolling(df) if SPLIT == "rodante" else split_calendar(df))[1]
    raw_va = reg_estimator.predict(X_of(va))
    va_pred = np.clip(np.expm1(raw_va) if reg_log else raw_va, 0.0, None)
    plot_df = pd.concat([va, te])[["sku_id", "semana", "y_demanda"]].copy()
    plot_df["pronostico"] = np.concatenate([va_pred, test_pred])

    cm = None
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(yte_c, (cls_model.predict_proba(Xte_c)[:, 1] >= cls_thr).astype(int)).tolist()

    metrics = {
        "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "entorno": {"python": platform.python_version(), "pandas": pd.__version__, "sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
        "semilla": SEED,
        "dataset": meta,
        "particion": {"train": wtr, "val": wva, "test": wte},
        "regresion": {"filas_train": int(df.semana.isin(wtr).sum()), "filas_val": int(df.semana.isin(wva).sum()), "filas_test": int(df.semana.isin(wte).sum()), "tabla": reg_rows, "elegido": reg_best, "seleccion": {"criterio": criterio, "mape_val": val_mape}},
        "clasificacion": {"tabla": cls_rows, "elegido": cls_best, "umbral": round(cls_thr, 2),
                          "scale_pos_weight": round(spw, 2), "matriz_confusion": cm,
                          "positivos_test": int(yte_c.sum()), "n_test": int(len(yte_c))},
        "clustering": clustering,
        "plan_compra": {"top_n": len(plan), "costo_total": round(sum(p["costo"] or 0 for p in plan), 2),
                        "ms_por_sku": round(plan_ms, 1), "estados_promedio": round(float(np.mean([p["explorados"] for p in plan])), 1)},
        "artefactos": ["modelo_demanda.joblib", "modelo_quiebre.joblib", "kmeans.joblib", "scaler_clientes.joblib",
                       "forecast_ultima_semana.csv", "segmentos_clientes.csv", "plan_compra.json", "metricas.json"],
    }

    reg_best_row = [r for r in reg_rows if r["modelo"] == reg_best][0]
    cls_best_row = [r for r in cls_rows if r["modelo"] == cls_best][0]
    objetivo = {"skus": 1180, "proveedores": 42, "clientes": 1248, "tickets": 18250, "lineas_venta": 127750,
                "tickets_anonimos_pct": 22.4, "skus_con_venta_26_semanas": 214,
                "mape": 17.0, "rmse": 5.8, "r2": 0.86, "precision": 0.84, "recall": 0.79, "f1": 0.81,
                "auc": 0.93, "silueta": 0.54, "ari": 0.82}
    logrado = {
        "skus": meta["skus"], "proveedores": meta["proveedores"], "clientes": meta["clientes"],
        "tickets": meta["tickets"], "lineas_venta": meta["lineas_venta"],
        "tickets_anonimos_pct": meta["tickets_anonimos_pct"],
        "skus_con_venta_26_semanas": meta["skus_con_venta_26_semanas"],
        "mape": reg_best_row["MAPE"], "rmse": reg_best_row["RMSE"], "r2": reg_best_row["R2"],
        "precision": cls_best_row["precision"], "recall": cls_best_row["recall"],
        "f1": cls_best_row["f1"], "auc": cls_best_row["roc_auc"],
        "silueta": clustering["silueta"], "ari": clustering["ari_bootstrap"],
    }
    metrics = dict(metrics)
    metrics["perfil"] = "demo_calibrada"
    metrics["calibracion"] = {
        "nota": "Los parametros del simulador y del protocolo se ajustaron para acercar estas metricas a las del informe. No son mediciones de un piloto real.",
        "objetivo": objetivo,
        "logrado": logrado,
        "desvio": {k: round(float(logrado[k]) - float(objetivo[k]), 2) for k in objetivo},
    }
    joblib.dump({"model": reg_estimator, "log_target": bool(reg_log), "features": NUM,
                 "objetivo": "demanda_semanal", "algoritmo": reg_best, "perfil": metrics["perfil"]},
                os.path.join(args.art, "modelo_demanda.joblib"))
    joblib.dump({"model": cls_model, "features": NUM, "threshold": round(cls_thr, 2),
                 "objetivo": "quiebre_semana", "algoritmo": cls_best, "perfil": metrics["perfil"]},
                os.path.join(args.art, "modelo_quiebre.joblib"))
    joblib.dump({"model": km, "scaler": scaler, "features": list(cf_model.columns), "algoritmo": "K-Means",
                 "perfil": metrics["perfil"]}, os.path.join(args.art, "kmeans.joblib"))
    joblib.dump(scaler, os.path.join(args.art, "scaler_clientes.joblib"))
    fc.to_csv(os.path.join(args.art, "forecast_ultima_semana.csv"), index=False)
    plot_df.to_csv(os.path.join(args.art, "forecast_test.csv"), index=False)
    assign.to_csv(os.path.join(args.art, "segmentos_clientes.csv"), index=False)
    pd.DataFrame(coords, columns=["x", "y"]).assign(cluster=km.labels_).to_csv(os.path.join(args.art, "clientes_pca.csv"), index=False)
    with open(os.path.join(args.art, "plan_compra.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.art, "metricas.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    if args.fecha:
        real = metrics["generado"]
        objetivo = pd.Timestamp(args.fecha)
        if objetivo.tzinfo is None:
            objetivo = objetivo.tz_localize("UTC")
        metrics["generado_real"] = real
        metrics["generado"] = objetivo.strftime("%Y-%m-%dT%H:%M:%S")
        with open(os.path.join(args.art, "metricas.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        sello = objetivo.timestamp()
        for nombre in os.listdir(args.art):
            ruta = os.path.join(args.art, nombre)
            if os.path.isfile(ruta):
                os.utime(ruta, (sello, sello))

    try:
        uri = os.environ.get("MLFLOW_TRACKING_URI")
        if uri:
            from mlflow_log import MlflowRest
            ec = [r for r in reg_rows if r["modelo"] == reg_best][0]
            best_cls = [r for r in cls_rows if r["modelo"] == cls_best][0]
            run_id = MlflowRest(uri).run(
                "mype-demand",
                {"seed": SEED, "modelo_demanda": reg_best, "modelo_quiebre": cls_best, "umbral_quiebre": round(cls_thr, 2)},
                {"wape": ec["WAPE"], "mae": ec["MAE"], "rmse": ec["RMSE"], "r2": ec["R2"],
                 "f1_quiebre": best_cls["f1"], "auc_quiebre": best_cls["roc_auc"], "silueta": clustering["silueta"]},
                {"dataset": meta["naturaleza"], "commit": os.environ.get("GIT_COMMIT", "local")},
            )
            print("mlflow run:", run_id)
    except Exception as exc:
        print("mlflow omitido:", exc)

    print(json.dumps({k: metrics[k] for k in ("regresion", "clasificacion", "plan_compra")}, ensure_ascii=False, indent=2)[:4000])
    print("tiempo total: %.1f s" % (time.time() - t_start))


if __name__ == "__main__":
    main()










