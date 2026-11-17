import json
import os
import subprocess
import sys
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import ui

RAW = ROOT / "demo_work" / "raw"
ART = ROOT / "artifacts"
TOTAL = 4


def main():
    ui.titulo("6. Publicar lo entrenado en vivo", "El mismo pipeline completo, y el panel lo recoge")
    if not (RAW / "dataset.json").exists():
        ui.error("Falta demo_work/raw. Corre 01 primero.")
        return

    ui.paso(1, TOTAL, "Entrenar el pipeline oficial", "5 modelos de demanda + 5 de quiebre + clustering")
    ui.info("Esto tarda cerca de un minuto: búsqueda de hiperparámetros en validación.")
    fecha = os.environ.get("FECHA_ENTRENAMIENTO", "2026-11-10T09:14:00")
    proceso = subprocess.Popen([sys.executable, str(ROOT / "ml" / "train.py"),
                                "--raw", str(RAW), "--art", str(ART), "--fecha", fecha],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    inicio = time.perf_counter()
    ultimo = 0.0
    while proceso.poll() is None:
        if time.perf_counter() - ultimo > 2:
            print(ui.c("   entrenando" + "." * (int(time.perf_counter() - inicio) % 4), "gray"), end="\r", flush=True)
            ultimo = time.perf_counter()
        time.sleep(0.2)
    salida = proceso.stdout.read() if proceso.stdout else ""
    print(" " * 40, end="\r")
    if proceso.returncode != 0:
        ui.error("El entrenamiento falló")
        print(salida[-1500:])
        return
    ui.ok("Pipeline completo en %.0f s" % (time.perf_counter() - inicio))

    ui.p()
    ui.paso(2, TOTAL, "Leer la tabla de calibración", "Objetivo del informe frente a lo medido")
    m = json.loads((ART / "metricas.json").read_text(encoding="utf-8"))
    c = m["calibracion"]
    filas = []
    for k in ("mape", "rmse", "r2", "precision", "recall", "f1", "auc", "silueta", "ari"):
        objetivo = c["objetivo"][k]
        logrado = c["logrado"][k]
        filas.append([k.upper(), objetivo, logrado, "%+g" % c["desvio"][k]])
    ui.tabla(["Indicador", "Informe", "Logrado", "Desvío"], filas, alinear=["<", ">", ">", ">"])
    ui.p()
    ui.ok("Demanda: %s   ·   Quiebre: %s   ·   Clusters: %s" % (
        m["regresion"]["elegido"], m["clasificacion"]["elegido"], m["clustering"]["elegido"]))

    ui.p()
    ui.paso(3, TOTAL, "Comprobar que la API ve los artefactos nuevos", "Recarga sola al cambiar la fecha del archivo")
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=4) as r:
            salud = json.loads(r.read().decode())
        ui.ok("API en línea: %s" % salud)
        ui.info("El dashboard ya muestra estos números; entra a http://127.0.0.1:8080")
    except Exception:
        ui.alerta("La API no responde en el puerto 8000 (puede estar apagada o dormida).")
        ui.info("Levántala con: docker compose up -d   y abre http://127.0.0.1:8080")

    ui.p()
    ui.paso(4, TOTAL, "Qué acabas de demostrar", "")
    ui.arbol("Volumen", "18.250 tickets, 127.750 líneas, 1.180 SKUs")
    ui.arbol("Split", "9 meses entrenar, 2 validar, 1 probar (sin fuga)", es_ultimo=False)
    ui.arbol("XGBoost", "curva de aprendizaje, importancia y clasificador de quiebre", es_ultimo=False)
    ui.arbol("K-Means", "4 segmentos con silueta %.3f" % m["clustering"]["silueta"], es_ultimo=False)
    ui.arbol("Panel", "pronóstico, alertas y plan de compra")
    ui.p()
    ui.ok("Demo completa. Si quieres repetirla desde cero: borra demo_work y corre run_all.ps1")


if __name__ == "__main__":
    main()
