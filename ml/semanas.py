import json
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

import joblib
import numpy as np
import pandas as pd
import features

RAW = ROOT / "data" / "demo"
ART = ROOT / "artifacts"
K = 6
NUM = ["lag_1", "lag_2", "lag_4", "ma_4", "ma_8", "sd_4", "sd_8", "media_hist",
       "promo_share", "promo_sku_next", "desc_sku_next", "promo_share_next", "descuento_prom",
       "desc_next", "feriado_next", "stock", "quiebre_prev", "cobertura",
       "precio", "lead_time", "vida_util", "categoria", "mes", "semana_anio", "tendencia"]


def main():
    reg = joblib.load(ART / "modelo_demanda.joblib")
    clf = joblib.load(ART / "modelo_quiebre.joblib")
    raw = features.load_raw(str(RAW))
    df, *_ = features.build_model_table(raw)
    df = df[df["semanas_con_venta"] >= 26].reset_index(drop=True)
    skus = pd.read_csv(RAW / "skus.csv").set_index("sku_id")
    semanas = sorted(df["semana"].unique())[-K:]

    salida = []
    for w in semanas:
        sub = df[df["semana"] == w].copy()
        X = np.nan_to_num(sub[NUM].fillna(0.0).to_numpy(float), posinf=1e3, neginf=0.0)
        sub["pronostico"] = np.clip(reg["model"].predict(X), 0, None)
        sub["prob"] = clf["model"].predict_proba(X)[:, 1]
        sub["nombre"] = sub["sku_id"].map(skus["nombre"])
        items = (sub[["sku_id", "nombre", "pronostico", "prob", "stock", "cobertura", "y_demanda"]]
                 .rename(columns={"y_demanda": "real"})
                 .round(3).sort_values("prob", ascending=False))
        error = float(np.mean(np.abs(items["real"] - items["pronostico"]) / items["real"].clip(lower=1)) * 100)
        salida.append({
            "semana": w,
            "alertas": int((items["prob"] >= 0.5).sum()),
            "critica": float(items["prob"].max()),
            "mape": round(error, 1),
            "items": items.to_dict(orient="records"),
        })
        print("%s  alertas=%2d  critica=%.2f  mape=%.1f%%" % (w, salida[-1]["alertas"], salida[-1]["critica"], salida[-1]["mape"]))

    destino = ART / "semanas.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False)
    print("escrito %s (%.0f KB)" % (destino, destino.stat().st_size / 1024))


if __name__ == "__main__":
    main()
