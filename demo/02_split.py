import json
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "ml"))

import pandas as pd
import ui
import features

RAW = ROOT / "demo_work" / "raw"
TOTAL = 6


def main():
    ui.titulo("2. Partición temporal 9 / 2 / 1", "Cómo se separa el histórico para entrenar, validar y probar")
    if not (RAW / "dataset.json").exists():
        ui.error("Falta demo_work/raw. Corre primero 01_dataset.py")
        return

    ui.paso(1, TOTAL, "Cargar ventas y quedarnos con los SKUs modelables",
            "Solo entran SKUs con al menos 26 semanas de historia")
    lineas = pd.read_csv(RAW / "ticket_lineas.csv", parse_dates=["fecha"])
    lineas["semana"] = lineas["fecha"].dt.to_period("W-MON").astype(str)
    semanas_por_sku = lineas.groupby("sku_id")["semana"].nunique()
    keep = semanas_por_sku[semanas_por_sku >= 26].index
    ui.ok(f"{len(keep)} SKUs con 26+ semanas de {semanas_por_sku.size} totales")
    sub = lineas[lineas.sku_id.isin(keep)]
    ui.info(f"{len(sub):,} líneas de venta entran al modelado")

    ui.p()
    ui.paso(2, TOTAL, "Asignar cada mes a un conjunto", "La regla es el calendario, no el azar")
    sub = sub.assign(mes=sub["fecha"].dt.to_period("M").astype(str))
    mensual = sub.groupby("mes").agg(lineas=("cantidad", "size"), unidades=("cantidad", "sum")).reset_index()
    filas = []
    for _, r in mensual.iterrows():
        if r["mes"] <= "2026-07":
            rol, color = "ENTRENAMIENTO", "green"
        elif r["mes"] <= "2026-09":
            rol, color = "VALIDACIÓN", "yellow"
        else:
            rol, color = "PRUEBA", "red"
        filas.append([r["mes"], ui.c(rol, color), f'{r["lineas"]:,}', f'{r["unidades"]:,}'])
    ui.tabla(["Mes", "Conjunto", "Líneas", "Unidades"], filas, alinear=["<", "<", ">", ">"])

    ui.p()
    ui.p("  Línea de tiempo", "bold")
    for _, r in mensual.iterrows():
        if r["mes"] <= "2026-07":
            color, marca = "green", "E"
        elif r["mes"] <= "2026-09":
            color, marca = "yellow", "V"
        else:
            color, marca = "red", "P"
        ui.p("   %s  %s %s" % (r["mes"], ui.c("█" * 3, color), ui.c(marca, color)), fin="\n")
        ui.dormir(0.04)

    ui.p()
    ui.paso(3, TOTAL, "Por qué no se baraja al azar", "Con series de tiempo, mezclar filtra el futuro")
    ui.p("   Si entrenas con semanas de octubre y validas con semanas de marzo,")
    ui.p("   el modelo ya 'vio' el futuro. Eso se llama fuga temporal y en producción")
    ui.p("   produce métricas bonitas que nunca se repiten.")
    ui.p()
    ui.p("   Regla del proyecto: todo lo de prueba es posterior a todo lo de entrenamiento.")

    ui.p()
    ui.paso(4, TOTAL, "Verificar el corte", "Comprobación automática de que no hay solapamiento")
    cortes = {
        "entrenamiento": sub[sub.mes <= "2026-07"]["fecha"],
        "validación": sub[(sub.mes >= "2026-08") & (sub.mes <= "2026-09")]["fecha"],
        "prueba": sub[sub.mes >= "2026-10"]["fecha"],
    }
    for nombre, fechas in cortes.items():
        filas_n = len(fechas)
        ui.p("   %-15s %s → %s   (%s líneas)" % (nombre, fechas.min().date(), fechas.max().date(), f"{filas_n:,}"))
        ui.dormir(0.1)
    fin_train = cortes["entrenamiento"].max()
    ini_val = cortes["validación"].min()
    fin_val = cortes["validación"].max()
    ini_test = cortes["prueba"].min()
    assert fin_train < ini_val and fin_val < ini_test
    ui.ok("Sin fuga temporal: entrenamiento < validación < prueba")

    ui.p()
    ui.paso(5, TOTAL, "Las filas que realmente ve el modelo", "Una fila = un SKU en una semana")
    raw = features.load_raw(str(RAW))
    df, *_ = features.build_model_table(raw)
    df = df[df["semanas_con_venta"] >= 26]
    df = df.assign(periodo=pd.PeriodIndex(df["semana"], freq="W-MON").start_time.strftime("%Y-%m"))
    conj = {
        "entrenamiento": df[df.periodo <= "2026-07"],
        "validación": df[(df.periodo >= "2026-08") & (df.periodo <= "2026-09")],
        "prueba": df[df.periodo >= "2026-10"],
    }
    filas = []
    for nombre, parte in conj.items():
        filas.append([nombre, f"{len(parte):,}", parte["sku_id"].nunique(),
                      f'{parte["semana"].min()}', f'{parte["semana"].max()}', f'{parte["y_demanda"].mean():.1f}'])
    ui.tabla(["Conjunto", "Filas", "SKUs", "Desde", "Hasta", "Demanda media"], filas,
             alinear=["<", ">", ">", "<", "<", ">"])
    total = sum(len(p) for p in conj.values())
    ui.p()
    ui.p("  Reparto: " + " · ".join("%s %.0f%%" % (k, 100 * len(v) / total) for k, v in conj.items()))

    ui.p()
    ui.paso(6, TOTAL, "Qué se guarda", "")
    ui.arbol("X de entrenamiento", f'{len(conj["entrenamiento"]):,} filas × 25 variables')
    ui.arbol("X de validación", f'{len(conj["validación"]):,} filas (para elegir hiperparámetros)', es_ultimo=False)
    ui.arbol("X de prueba", f'{len(conj["prueba"]):,} filas (se toca una sola vez, al final)')
    ui.p()
    ui.ok("Siguiente: 03_xgboost.py  →  ver el boosting aprendiendo")


if __name__ == "__main__":
    main()
