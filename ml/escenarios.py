import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "data", "generate_demo.py")
TRAIN = os.path.join(ROOT, "ml", "train.py")
WORK = os.path.join(ROOT, "demo_work")
RAW = os.path.join(WORK, "drift")
ART = os.path.join(ROOT, "artifacts", "escenarios")
DIAS = 393
DERIVA = "2026-11-01"
FACTOR = 1.35
ESCENARIOS = [
    ("Sin datos nuevos", "2026-10-31", "entrenado hasta el 31 de octubre, sin ver la subida"),
    ("+1 semana", "2026-11-07", "un reentrenamiento con la primera semana del cambio"),
    ("+2 semanas", "2026-11-14", "dos semanas de datos nuevos antes de predecir"),
]


def generar():
    if os.path.exists(os.path.join(RAW, "dataset.json")):
        print("dataset con deriva ya existe")
        return
    shutil.rmtree(RAW, ignore_errors=True)
    os.makedirs(RAW, exist_ok=True)
    subprocess.run([sys.executable, GEN, "--out", RAW, "--dias", str(DIAS),
                    "--deriva-inicio", DERIVA, "--deriva-factor", str(FACTOR)],
                   check=True, capture_output=True)
    print("dataset con deriva generado (%d dias, +%d%% desde %s)" % (DIAS, round((FACTOR - 1) * 100), DERIVA))


def entrenar(hasta, art):
    os.makedirs(art, exist_ok=True)
    cmd = [sys.executable, TRAIN, "--raw", RAW, "--art", art,
           "--split", "deriva"]
    if hasta:
        cmd += ["--hasta", hasta]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout[-2000:], res.stderr[-2000:])
        raise SystemExit("fallo el entrenamiento")
    return json.load(open(os.path.join(art, "metricas.json"), encoding="utf-8"))


def main():
    os.makedirs(ART, exist_ok=True)
    generar()
    resumen = []
    for etiqueta, hasta, nota in ESCENARIOS:
        clave = "h_" + (hasta or "todo").replace("-", "")
        art = os.path.join(ART, clave)
        print("entrenando %-16s (hasta %s)" % (etiqueta, hasta or "todo"))
        m = entrenar(hasta, art)
        for f in os.listdir(art):
            if f.endswith(".joblib"):
                os.remove(os.path.join(art, f))
        reg = [r for r in m["regresion"]["tabla"] if r["modelo"] == m["regresion"]["elegido"]][0]
        cls = [r for r in m["clasificacion"]["tabla"] if r["modelo"] == m["clasificacion"]["elegido"]][0]
        resumen.append({
            "id": clave, "etiqueta": etiqueta, "nota": nota, "hasta": hasta or "todo",
            "semanas_train": len(m["particion"]["train"]),
            "filas_train": m["regresion"]["filas_train"], "filas_test": m["regresion"]["filas_test"],
            "mape": reg["MAPE"], "rmse": reg["RMSE"], "r2": reg["R2"],
            "f1": cls["f1"], "auc": cls["roc_auc"],
        })
        json.dump({"deriva": {"inicio": DERIVA, "factor": FACTOR}, "escenarios": resumen},
                  open(os.path.join(ART, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("   MAPE %.2f  RMSE %.2f  F1 %.3f  train %d filas" % (reg["MAPE"], reg["RMSE"], cls["f1"], m["regresion"]["filas_train"]))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
