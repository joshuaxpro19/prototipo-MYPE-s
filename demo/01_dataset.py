import json
import os
import sqlite3
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))

import pandas as pd
import ui

WORK = ROOT / "demo_work"
RAW = WORK / "raw"
GEN = ROOT / "data" / "generate_demo.py"
TOTAL = 6


def generar():
    RAW.mkdir(parents=True, exist_ok=True)
    ui.info("Ejecutando data/generate_demo.py (semilla 20261116)…")
    t0 = ui.time.perf_counter()
    subprocess.run([sys.executable, str(GEN), "--out", str(RAW)], check=True, capture_output=True)
    ui.ok("Dataset generado en %.1f s" % (ui.time.perf_counter() - t0))


def main():
    ui.titulo("1. Del punto de venta al dataset", "Cómo se construye la materia prima del proyecto")
    ui.paso(1, TOTAL, "Generar el dataset", "data/generate_demo.py simula 12 meses de un minimarket")
    if not (RAW / "dataset.json").exists():
        generar()
    else:
        ui.ok("demo_work/raw ya existe (borra demo_work para regenerar)")

    meta = json.loads((RAW / "dataset.json").read_text(encoding="utf-8"))
    ui.p("  Naturaleza: " + ui.c(meta["naturaleza"], "yellow"))
    ui.p()
    ui.tabla(
        ["Elemento", "Valor", "De dónde sale"],
        [
            ["SKUs", f'{meta["skus"]:,}', "maestro de inventario"],
            ["Proveedores", meta["proveedores"], "maestro de inventario"],
            ["Clientes", f'{meta["clientes"]:,}', "módulo de clientes del POS"],
            ["Tickets", f'{meta["tickets"]:,}', "ventas diarias"],
            ["Líneas de venta", f'{meta["lineas_venta"]:,}', "detalle de cada ticket"],
            ["Tickets anónimos", f'{meta["tickets_anonimos_pct"]} %', "cliente no identificado"],
            ["Semanas", meta["semanas"], "nov-2025 a oct-2026"],
        ],
    )

    ui.p()
    ui.paso(2, TOTAL, "Ver la forma de los archivos", "Las tres tablas que alimentan el pipeline")
    skus = pd.read_csv(RAW / "skus.csv")
    tickets = pd.read_csv(RAW / "tickets.csv", parse_dates=["fecha"])
    lineas = pd.read_csv(RAW / "ticket_lineas.csv", parse_dates=["fecha"])

    ui.p("  skus.csv", "bold")
    ui.tabla(list(skus.columns[:6]), skus.head(3)[list(skus.columns[:6])].values.tolist())
    ui.p()
    ui.p("  tickets.csv", "bold")
    ui.tabla(["ticket_id", "fecha", "hora", "cliente_id", "metodo_pago"],
             tickets[["ticket_id", "fecha", "hora", "cliente_id", "metodo_pago"]].head(3).values.tolist())
    ui.p()
    ui.p("  ticket_lineas.csv", "bold")
    ui.tabla(["ticket_id", "sku_id", "cantidad", "precio_unitario", "importe"],
             lineas[["ticket_id", "sku_id", "cantidad", "precio_unitario", "importe"]].head(4).values.tolist())

    ui.p()
    ui.paso(3, TOTAL, "Guardar en la base de datos", "Copia en SQLite para poder consultarla con SQL")
    db = WORK / "demo.db"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    lineas["fecha"] = lineas["fecha"].dt.strftime("%Y-%m-%d")
    tickets["fecha"] = tickets["fecha"].dt.strftime("%Y-%m-%d")
    for nombre, df in (("skus", skus), ("tickets", tickets), ("lineas", lineas)):
        df.to_sql(nombre, con, index=False, if_exists="replace", chunksize=20000)
        filas = con.execute(f"select count(*) from {nombre}").fetchone()[0]
        ui.ok(f"tabla {nombre:<8} {filas:>7,} filas")

    con.execute("create index if not exists ix_lineas_sku on lineas(sku_id)")
    con.commit()
    ui.info("demo_work/demo.db  ·  %.1f MB" % (db.stat().st_size / 1e6))

    ui.p()
    ui.paso(4, TOTAL, "Consultar la base", "Tres preguntas típicas del negocio")
    ui.p("  ¿Qué productos mueven la caja?", "bold")
    q1 = """
        select l.sku_id, s.nombre, s.categoria,
               sum(l.cantidad) as unidades,
               round(sum(l.importe), 2) as soles
        from lineas l join skus s on s.sku_id = l.sku_id
        group by l.sku_id order by unidades desc limit 5
    """
    ui.tabla(["SKU", "Producto", "Categoría", "Unidades", "S/"], pd.read_sql_query(q1, con).values.tolist(),
             alinear=[">", "<", "<", ">", ">"])

    ui.p()
    ui.p("  ¿Cómo se mueve la venta por mes?", "bold")
    q2 = """
        select substr(fecha, 1, 7) as mes, count(*) as tickets,
               round(sum(importe), 2) as soles
        from lineas group by mes order by mes
    """
    meses = pd.read_sql_query(q2, con)
    tope = meses["soles"].max()
    for _, r in meses.iterrows():
        ui.p("   %s  %s  %8.0f S/  (%d líneas)" % (r["mes"], ui.barra(r["soles"], tope, 34, "cyan"), r["soles"], r["tickets"]))

    ui.p()
    ui.paso(5, TOTAL, "Dónde vive esto en la app", "Para que no haya confusión al explicar")
    ui.arbol("Dataset de ventas", "demo_work/raw/*.csv (lo consume el entrenamiento)")
    ui.arbol("Modelos y métricas", "artifacts/*.joblib + metricas.json", es_ultimo=False)
    ui.arbol("Alertas, usuarios, auditoría", "SQLite en la nube / Postgres en Docker")
    ui.p()
    ui.alerta("La API no consulta ventas en caliente: sirve los artefactos ya entrenados.")

    ui.p()
    ui.paso(6, TOTAL, "Resumen", "")
    ui.p("  Entrada : %s tickets, %s líneas, %s SKUs" % (f'{len(tickets):,}', f'{len(lineas):,}', f'{len(skus):,}'))
    ui.p("  Salida  : 6 CSV + una copia consultable en demo_work/demo.db")
    ui.ok("Siguiente: 02_split.py  →  cómo se parte en 9/2/1")


if __name__ == "__main__":
    main()
