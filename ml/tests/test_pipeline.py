import hashlib
import json
import pathlib
import subprocess
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

import features


def run_gen(out, seed=7, cover=1.45):
    cmd = [sys.executable, str(ROOT / "data" / "generate_demo.py"), "--out", str(out),
           "--seed", str(seed), "--cover", str(cover)]
    subprocess.run(cmd, check=True, capture_output=True)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path(out).glob("*.csv")}


def test_generador_es_determinista(tmp_path):
    a = run_gen(tmp_path / "a")
    b = run_gen(tmp_path / "b")
    assert a == b
    meta = json.loads((tmp_path / "a" / "dataset.json").read_text(encoding="utf-8"))
    assert meta["perfil"] == "demo"
    assert "demo calibrada" in meta["naturaleza"]


def test_generador_cambia_con_semilla(tmp_path):
    a = run_gen(tmp_path / "a", seed=7)
    b = run_gen(tmp_path / "b", seed=11)
    assert a["ticket_lineas.csv"] != b["ticket_lineas.csv"]


def test_volumenes_de_la_demo(tmp_path):
    run_gen(tmp_path / "raw")
    meta = json.loads((tmp_path / "raw" / "dataset.json").read_text(encoding="utf-8"))
    assert meta["skus"] == 1180
    assert meta["proveedores"] == 42
    assert meta["clientes"] == 1248
    assert meta["tickets"] == 18250
    assert meta["lineas_venta"] == 127750
    assert abs(meta["tickets_anonimos_pct"] - 22.4) < 0.05
    assert 200 <= meta["skus_con_venta_26_semanas"] <= 230


def test_features_sin_fuga_temporal(tmp_path):
    run_gen(tmp_path / "raw")
    raw = features.load_raw(str(tmp_path / "raw"))
    df, uni, quiebre, perdidas, weeks, skus = features.build_model_table(raw)
    assert len(df) > 0
    uni = uni.reindex(columns=weeks).fillna(0.0)
    for _, row in df.sample(min(20, len(df)), random_state=1).iterrows():
        i = weeks.index(row["semana"])
        esperado = uni.loc[row["sku_id"]].to_numpy()[i - 4:i].mean()
        assert row["ma_4"] == pytest.approx(esperado, rel=1e-6, abs=1e-6)
        assert row["lag_1"] == pytest.approx(uni.loc[row["sku_id"]].to_numpy()[i - 1], rel=1e-9, abs=1e-9)
        assert row["media_hist"] == pytest.approx(uni.loc[row["sku_id"]].to_numpy()[:i].mean(), rel=1e-6)


def test_artefactos_del_entrenamiento():
    art = ROOT / "artifacts"
    metrics = json.loads((art / "metricas.json").read_text(encoding="utf-8"))
    assert metrics["semilla"] == 20261116
    assert metrics["perfil"] == "demo_calibrada"
    assert "simulad" in metrics["dataset"]["naturaleza"]
    assert metrics["regresion"]["elegido"]
    assert metrics["clasificacion"]["elegido"]
    assert 0.0 <= metrics["clustering"]["silueta"] <= 1.0
    assert len(metrics["clustering"]["segmentos"]) == 4
    cal = metrics["calibracion"]
    assert set(cal["objetivo"]) == set(cal["logrado"])
    assert abs(cal["desvio"]["mape"]) < 3.0
    assert abs(cal["desvio"]["f1"]) < 0.10
    assert abs(cal["desvio"]["silueta"]) < 0.10

    fc = pd.read_csv(art / "forecast_ultima_semana.csv")
    assert len(fc) >= 200
    assert fc["pronostico_semana_siguiente"].min() >= 0
    assert fc["prob_quiebre"].between(0, 1).all()

    plan = json.loads((art / "plan_compra.json").read_text(encoding="utf-8"))
    assert len(plan) == 20
    assert all(p["costo"] is not None and p["costo"] >= 0 for p in plan)
    assert all(len(p["plan"]) == 4 for p in plan)

    seg = pd.read_csv(art / "segmentos_clientes.csv")
    assert seg["segmento"].nunique() == 4
