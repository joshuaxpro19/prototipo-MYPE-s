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
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

RAW = ROOT / "demo_work" / "raw"
WORK = ROOT / "demo_work"
TOTAL = 6
COLS = ["frecuencia", "monetario", "ticket_promedio", "share_finde", "share_promo"]
ACCIONES = {"Hogar": "combo familiar quincenal", "Mayorista": "descuento por caja cerrada",
            "Fin de semana": "combo sábado familiar", "Promo-sensible": "2x1 en líneas seleccionadas",
            "Ocasional": "cupón de retorno a 30 días"}


def scatter(x, y, labels, ancho=58, alto=16):
    letras = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E", 5: "F"}
    colores = {0: "cyan", 1: "magenta", 2: "yellow", 3: "green", 4: "blue", 5: "red"}
    grid = [[" "] * ancho for _ in range(alto)]
    col = [[None] * ancho for _ in range(alto)]
    xs = (x - x.min()) / (x.max() - x.min() + 1e-9)
    ys = (y - y.min()) / (y.max() - y.min() + 1e-9)
    for xi, yi, lab in zip(xs, ys, labels):
        cx = min(ancho - 1, int(xi * (ancho - 1)))
        cy = min(alto - 1, int((1 - yi) * (alto - 1)))
        grid[cy][cx] = letras.get(lab, "?")
        col[cy][cx] = colores.get(lab, "gray")
    for f in range(alto):
        linea = "".join((ui.c(grid[f][j], col[f][j]) if col[f][j] else " ") for j in range(ancho))
        ui.p("   │" + linea + "│")
    ui.p("   └" + "─" * ancho + "┘")


def nombrar(summary):
    q75 = summary["monetario"].quantile(0.75)
    q25 = summary["frecuencia"].quantile(0.25)
    med = summary["frecuencia"].median()
    nombres = {}
    for c, r in summary.iterrows():
        if r["monetario"] >= q75 and r["frecuencia"] >= med:
            nombres[c] = "Mayorista"
        elif r["frecuencia"] <= q25:
            nombres[c] = "Ocasional"
        elif r["finde"] >= 0.6:
            nombres[c] = "Fin de semana"
        elif r["promo"] >= 0.45:
            nombres[c] = "Promo-sensible"
        else:
            nombres[c] = "Hogar"
    return nombres


def main():
    ui.titulo("4. K-Means formando segmentos", "Cómo se agrupan 1.248 clientes sin decirle quién es quién")
    if not (RAW / "dataset.json").exists():
        ui.error("Falta demo_work/raw. Corre 01 primero.")
        return

    ui.paso(1, TOTAL, "Construir el perfil de cada cliente", "RFM + hábitos de compra")
    raw = features.load_raw(str(RAW))
    cf = features.client_features(raw)
    ui.ok(f"{len(cf):,} clientes con al menos una compra identificada")
    ui.p()
    ui.tabla(["Cliente", "Frecuencia", "Monetario", "Ticket", "Finde", "Promo"],
             [[idx, int(r.frecuencia), round(r.monetario), round(r.ticket_promedio, 1),
               round(r.share_finde, 2), round(r.share_promo, 2)] for idx, r in cf.head(5).iterrows()],
             alinear=["<", ">", ">", ">", ">", ">"])
    ui.info("Cada fila es un cliente; el algoritmo no ve su nombre, solo estos números.")

    ui.p()
    ui.paso(2, TOTAL, "Estandarizar y barrer k", "Si una variable mide miles y otra 0-1, domina la de miles")
    x = features.winsorize(cf[COLS])
    Z = StandardScaler().fit_transform(x)
    ui.ok(f"matriz Z: {Z.shape[0]:,} clientes × {Z.shape[1]} variables estandarizadas")
    ui.p()
    ui.p("   k   inercia    silueta", "bold")
    resultados = {}
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=10, random_state=20261116).fit(Z)
        s = silhouette_score(Z, km.labels_)
        resultados[k] = (km.inertia_, s)
        marca = "  ← elegido" if k == 4 else ""
        ui.p("   %d   %9.1f   %s %.3f%s" % (k, km.inertia_, ui.barra(s, 0.7, 26, "magenta"), s, ui.c(marca, "green")))
        ui.dormir(0.05)
    ui.info("k=4 no es el de mejor silueta: se elige por legibilidad para el dueño de la tienda.")

    ui.p()
    ui.paso(3, TOTAL, "Ver los centroides moverse", "Cada iteración recoloca el centro de cada grupo")
    pca = PCA(n_components=2, random_state=20261116)
    xy = pca.fit_transform(Z)
    anterior = None
    for it in (1, 2, 3, 5, 8, 12):
        km = KMeans(n_clusters=4, init="k-means++", n_init=1, max_iter=it, random_state=20261116).fit(Z)
        centros = pca.transform(km.cluster_centers_)
        if anterior is not None:
            mov = float(np.mean(np.linalg.norm(centros - anterior, axis=1)))
        else:
            mov = 0.0
        ui.p("   iteración %2d  " % it + "  ".join("(%5.1f,%5.1f)" % (c[0], c[1]) for c in centros)
             + ui.c("   desplazamiento %.2f" % mov, "gray"))
        anterior = centros
        ui.dormir(0.12)

    ui.p()
    ui.paso(4, TOTAL, "El resultado en un plano", "Cada letra es un cliente; A-D son los grupos")
    km = KMeans(n_clusters=4, n_init=10, random_state=20261116).fit(Z)
    labels = km.labels_
    scatter(xy[:, 0], xy[:, 1], labels)
    ui.p("   varianza explicada por el plano: %.0f %%" % (sum(pca.explained_variance_ratio_) * 100))
    ui.info("Silueta %.3f · Davies-Bouldin %.2f" % (silhouette_score(Z, labels), davies_bouldin_score(Z, labels)))

    ui.p()
    ui.paso(5, TOTAL, "Traducir los grupos a perfiles", "El algoritmo agrupa; el negocio interpreta")
    perfil = cf.copy()
    perfil["cluster"] = labels
    summary = perfil.groupby("cluster").agg(
        n=("frecuencia", "size"), frecuencia=("frecuencia", "mean"), monetario=("monetario", "mean"),
        ticket=("ticket_promedio", "mean"), finde=("share_finde", "mean"), promo=("share_promo", "mean")).round(1)
    summary["pct"] = (summary["n"] / summary["n"].sum() * 100).round(1)
    nombres = nombrar(summary)
    filas = []
    for c, r in summary.sort_values("n", ascending=False).iterrows():
        nombre = nombres[c]
        filas.append([f"{chr(65 + c)} · {nombre}", f"{int(r.n):,}", f"{r.pct:.1f} %", f"{r.ticket:.0f}",
                      f"{r.frecuencia:.1f}", f"{r.finde:.2f}", f"{r.promo:.2f}", ACCIONES.get(nombre, "revisar")])
    ui.tabla(["Segmento", "Clientes", "%", "Ticket S/", "Frec.", "Finde", "Promo", "Acción sugerida"], filas,
             alinear=["<", ">", ">", ">", ">", ">", ">", "<"])

    ui.p()
    ui.paso(6, TOTAL, "Guardar", "El front consume estos segmentos tal cual")
    joblib.dump({"model": km, "scaler": StandardScaler().fit(x), "features": COLS, "algoritmo": "K-Means",
                 "perfil": "demo"}, WORK / "kmeans.joblib")
    salida = pd.DataFrame({"cliente_ref": cf.index, "cluster": labels,
                           "segmento": [nombres[c] for c in labels]})
    salida.to_csv(WORK / "segmentos_demo.csv", index=False)
    ui.ok("demo_work/kmeans.joblib")
    ui.ok("demo_work/segmentos_demo.csv")
    ui.p()
    ui.ok("Siguiente: 05_alertas.py  →  qué hace el sistema con todo esto")


if __name__ == "__main__":
    main()
