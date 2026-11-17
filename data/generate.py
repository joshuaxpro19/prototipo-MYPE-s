import argparse
import json
import os

import numpy as np
import pandas as pd

START = "2025-11-01"
DAYS = 365
CATS = {"abarrotes": 0.45, "bebidas": 0.20, "lacteos": 0.20, "limpieza": 0.15}
CAT_LIST = list(CATS)
DOW = np.array([0.90, 0.85, 0.90, 0.95, 1.12, 1.38, 1.08])
MONTH = np.array([1.05, 0.95, 0.98, 1.02, 1.00, 1.03, 1.12, 0.97, 1.00, 1.02, 1.08, 1.32])
HOLIDAYS = {(12, 8), (12, 24), (12, 25), (12, 31), (1, 1), (4, 18), (5, 1), (6, 29), (7, 23), (7, 28), (7, 29), (8, 30), (10, 8)}
AFFINITY = {
    "hogar": {"abarrotes": 1.35, "bebidas": 0.85, "lacteos": 1.30, "limpieza": 1.10},
    "mayorista": {"abarrotes": 1.30, "bebidas": 1.45, "lacteos": 0.70, "limpieza": 0.80},
    "fin_semana": {"abarrotes": 0.85, "bebidas": 1.70, "lacteos": 0.80, "limpieza": 0.70},
    "promo_sensible": {"abarrotes": 1.00, "bebidas": 1.00, "lacteos": 1.00, "limpieza": 1.00},
}


def make_skus(rng, n_skus, n_suppliers):
    cats = rng.choice(CAT_LIST, size=n_skus, p=list(CATS.values()))
    velocity = rng.choice(["A", "B", "C", "D"], size=n_skus, p=[0.05, 0.18, 0.42, 0.35])
    base = np.where(velocity == "A", rng.lognormal(np.log(7.0), 0.35, n_skus),
                    np.where(velocity == "B", rng.lognormal(np.log(2.2), 0.40, n_skus),
                             np.where(velocity == "C", rng.lognormal(np.log(0.7), 0.45, n_skus),
                                      rng.lognormal(np.log(0.25), 0.50, n_skus))))
    ref_price = {"abarrotes": 6.0, "bebidas": 5.0, "lacteos": 4.2, "limpieza": 9.0}
    price = np.array([rng.lognormal(np.log(ref_price[c]), 0.35) for c in cats]).round(2)
    shelf = np.array([int(rng.integers(*{"abarrotes": (90, 365), "bebidas": (120, 400),
                                          "lacteos": (5, 21), "limpieza": (365, 720)}[c])) for c in cats])
    return pd.DataFrame({
        "sku_id": ["SKU-%04d" % (i + 1) for i in range(n_skus)],
        "nombre": ["%s %04d" % (c[:3].upper(), i + 1) for i, c in enumerate(cats)],
        "categoria": cats,
        "clase_rotacion": velocity,
        "demanda_base": base.round(4),
        "precio": price,
        "costo": (price * rng.uniform(0.68, 0.82, n_skus)).round(2),
        "vida_util_dias": shelf,
        "lead_time_dias": rng.integers(2, 8, n_skus),
        "proveedor_id": ["PRV-%02d" % (i + 1) for i in rng.integers(1, n_suppliers + 1, n_skus)],
    })


def make_clients(rng, n_clients):
    seg = rng.choice(["hogar", "mayorista", "fin_semana", "promo_sensible"], size=n_clients, p=[0.38, 0.12, 0.31, 0.19])
    activity = np.where(seg == "hogar", rng.lognormal(0.0, 0.4, n_clients),
                        np.where(seg == "mayorista", rng.lognormal(0.3, 0.35, n_clients),
                                 np.where(seg == "fin_semana", rng.lognormal(-0.1, 0.4, n_clients),
                                          rng.lognormal(0.4, 0.5, n_clients))))
    basket = np.where(seg == "mayorista", 9.0, np.where(seg == "fin_semana", 8.0,
                                                         np.where(seg == "promo_sensible", 4.0, 6.0)))
    pay = rng.choice(["efectivo", "yape", "tarjeta", "plin"], size=n_clients, p=[0.42, 0.28, 0.22, 0.08])
    return pd.DataFrame({
        "cliente_id": ["CLI-%04d" % (i + 1) for i in range(n_clients)],
        "segmento_latente": seg,
        "actividad": activity.round(4),
        "tamano_canasta": basket,
        "pago_preferido": pay,
        "antiguedad_dias": rng.integers(60, 2000, n_clients),
    })


def make_promotions(rng, skus, dates):
    cat = skus["categoria"].to_numpy()
    p_promo = np.where(cat == "lacteos", 0.09, np.where(cat == "bebidas", 0.08, 0.05))
    mask = rng.random((len(skus), DAYS)) < p_promo[:, None]
    rows = np.argwhere(mask)
    desc = rng.choice([0.10, 0.15, 0.20, 0.25, 0.30], size=len(rows), p=[0.30, 0.25, 0.20, 0.15, 0.10])
    desc_matrix = np.zeros_like(mask, dtype=float)
    desc_matrix[mask] = desc
    return pd.DataFrame({
        "sku_id": skus["sku_id"].to_numpy()[rows[:, 0]],
        "fecha": dates[rows[:, 1]],
        "descuento": desc,
        "tipo": rng.choice(["2x1", "descuento", "exhibicion"], size=len(rows), p=[0.25, 0.55, 0.20]),
    }), mask, desc_matrix


def expected_demand(rng, skus, dates, promo_mask, promo_desc):
    dow = DOW[np.asarray(dates.dayofweek)]
    month = MONTH[dates.month.to_numpy() - 1]
    holiday = np.array([1.55 if (d.month, d.day) in HOLIDAYS else 1.0 for d in dates])
    quincena = np.isin(dates.day.to_numpy(), [1, 2, 15, 16, 28, 29, 30, 31])
    cal = dow * month * holiday * np.where(quincena, 1.12, 1.0)
    lift = np.where(promo_mask, 1.0 + 2.4 * promo_desc, 1.0)
    noise = rng.lognormal(0.0, 0.22, (len(skus), DAYS))
    return skus["demanda_base"].to_numpy()[:, None] * cal[None, :] * lift * noise


def build_tickets(rng, lam, clientes, dates, n_tickets, promo_mask, skus):
    day_w = DOW[np.asarray(dates.dayofweek)] ** 1.2
    tix_per_day = rng.multinomial(n_tickets, day_w / day_w.sum())
    is_weekend = np.isin(np.asarray(dates.dayofweek), [5, 6])
    seg = clientes["segmento_latente"].to_numpy()
    activity = clientes["actividad"].to_numpy()
    basket = clientes["tamano_canasta"].to_numpy()
    pay = clientes["pago_preferido"].to_numpy()
    cat_codes = pd.Categorical(skus["categoria"], categories=CAT_LIST).codes
    aff = np.zeros((len(clientes), len(CAT_LIST)))
    for i, s in enumerate(seg):
        aff[i] = [AFFINITY[s][c] for c in CAT_LIST]
    sku_aff = aff[:, cat_codes]
    promo_aff = np.where(seg == "promo_sensible", 2.5, np.where(seg == "mayorista", 0.7, 1.0))

    ticket_rows, line_rows = [], []
    t_id = 0
    for d in range(len(dates)):
        n = int(tix_per_day[d])
        if n == 0:
            continue
        promo_share = float(promo_mask[:, d].mean())
        w = activity * np.where(seg == "fin_semana", 1.0 if is_weekend[d] else 0.02, 1.0) * (1.0 + promo_aff * promo_share)
        cli = rng.choice(len(clientes), size=n, p=w / w.sum())
        lines = np.clip(1 + rng.poisson(basket[cli] - 1.0), 1, 18)
        base_w = lam[:, d] / lam[:, d].sum()
        for j, c in enumerate(cli):
            p = base_w * sku_aff[c] * (1.0 + (promo_aff[c] - 1.0) * promo_mask[:, d] * 1.2)
            p = p / p.sum()
            sku_idx = rng.choice(len(skus), size=lines[j], p=p)
            line_rows.append(pd.DataFrame({
                "ticket_id": "TK-%06d" % (t_id + j + 1),
                "sku_id": skus["sku_id"].to_numpy()[sku_idx],
                "cantidad": rng.choice([1, 2, 3, 4], size=lines[j], p=[0.50, 0.30, 0.15, 0.05]),
                "fecha": dates[d],
            }))
        ticket_rows.append(pd.DataFrame({
            "ticket_id": ["TK-%06d" % (i + 1) for i in range(t_id, t_id + n)],
            "fecha": dates[d],
            "hora": rng.integers(7, 22, n),
            "cliente_id": clientes["cliente_id"].to_numpy()[cli],
            "metodo_pago": pay[cli],
            "n_lineas": lines,
        }))
        t_id += n

    tickets = pd.concat(ticket_rows, ignore_index=True)
    anon = rng.random(len(tickets)) >= 0.776
    tickets.loc[anon, "cliente_id"] = "ANON"
    tickets["identificado"] = ~anon
    lineas = pd.concat(line_rows, ignore_index=True)
    return tickets, lineas


def unit_prices(skus, promos, lineas):
    price = skus.set_index("sku_id")["precio"]
    disc = promos.set_index(["fecha", "sku_id"])["descuento"]
    keys = list(zip(lineas["fecha"], lineas["sku_id"]))
    d = np.array([disc.get(k, 0.0) for k in keys], dtype=float)
    lineas["descuento"] = d
    pu = lineas["sku_id"].map(price).to_numpy() * (1.0 - d)
    lineas["precio_unitario"] = pu.round(2)
    lineas["importe"] = (pu * lineas["cantidad"]).round(2)
    return lineas


def simulate_inventory(rng, weekly_demand, weeks, skus):
    n_sku = weekly_demand.shape[0]
    in_transit = {}
    stock = np.ceil(weekly_demand[:, :2].mean(axis=1) * 2).astype(float)
    rows = []
    late = 0.10
    for w in range(len(weeks)):
        arrive = in_transit.get(w)
        if arrive is not None:
            stock += arrive
        dem = weekly_demand[:, w].astype(float)
        sold = np.minimum(stock, dem)
        lost = dem - sold
        quiebre = (lost > 0).astype(int)
        stock = stock - sold
        hist = weekly_demand[:, max(0, w - 2):w + 1].mean(axis=1) if w > 0 else weekly_demand[:, :1].mean(axis=1)
        reorder = stock < np.maximum(hist * 1.0, 1.0)
        if reorder.any():
            qty = np.maximum(np.ceil(hist * 3.0 + 1.0) - stock, 0) * reorder
            lead = np.where(rng.random(n_sku) < late, 3, 2)
            for i in np.argwhere(reorder).ravel():
                in_transit[w + int(lead[i])] = in_transit.get(w + int(lead[i]), np.zeros(n_sku)) + np.eye(n_sku, dtype=float)[i] * qty[i]
        block = pd.DataFrame({
            "sku_id": skus["sku_id"].to_numpy(),
            "ventas_unidades": dem,
            "stock_fin_semana": stock,
            "quiebre": quiebre,
            "unidades_perdidas": lost,
        })
        block["semana"] = weeks[w]
        rows.append(block)
    weekly = pd.concat(rows, ignore_index=True)
    events = weekly[weekly["quiebre"] == 1].reset_index(drop=True)
    return weekly, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw"))
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--skus", type=int, default=1180)
    ap.add_argument("--clientes", type=int, default=1248)
    ap.add_argument("--tickets", type=int, default=18250)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    dates = pd.date_range(START, periods=DAYS, freq="D")

    skus = make_skus(rng, args.skus, 42)
    clientes = make_clients(rng, args.clientes)
    promos, mask, desc = make_promotions(rng, skus, dates)
    lam = expected_demand(rng, skus, dates, mask, desc)
    tickets, lineas = build_tickets(rng, lam, clientes, dates, args.tickets, mask, skus)
    lineas = unit_prices(skus, promos, lineas)

    lineas["semana"] = lineas["fecha"].dt.to_period("W-MON").astype(str)
    weeks = sorted(lineas["semana"].unique())
    wd = lineas.pivot_table(index="sku_id", columns="semana", values="cantidad", aggfunc="sum").reindex(index=skus["sku_id"], columns=weeks).fillna(0.0)
    weekly, events = simulate_inventory(rng, wd.to_numpy(), weeks, skus)

    skus.to_csv(os.path.join(args.out, "skus.csv"), index=False)
    clientes.to_csv(os.path.join(args.out, "clientes.csv"), index=False)
    tickets.drop(columns=["n_lineas"]).to_csv(os.path.join(args.out, "tickets.csv"), index=False)
    lineas.drop(columns=["semana"]).to_csv(os.path.join(args.out, "ticket_lineas.csv"), index=False)
    promos.to_csv(os.path.join(args.out, "promociones.csv"), index=False)
    weekly.to_csv(os.path.join(args.out, "inventario_semanal.csv"), index=False)
    events.to_csv(os.path.join(args.out, "quiebres.csv"), index=False)

    meta = {
        "naturaleza": "dataset sintetico simulado, no observaciones reales",
        "seed": args.seed,
        "inicio": START,
        "dias": DAYS,
        "semanas": int(len(weeks)),
        "skus": int(len(skus)),
        "proveedores": int(skus["proveedor_id"].nunique()),
        "clientes": int(len(clientes)),
        "tickets": int(len(tickets)),
        "lineas_venta": int(len(lineas)),
        "tickets_anonimos_pct": round(float((~tickets["identificado"]).mean() * 100), 1),
        "skus_con_venta_26_semanas": int((wd > 0).sum(axis=1).ge(26).sum()),
        "semanas_sku_con_quiebre_pct": round(float(weekly["quiebre"].mean() * 100), 1),
        "politica_inventario": "pedido semanal si stock < media movil 3 semanas; llegar a 3x esa media; lead time 2-3 semanas con 10% de demora",
        "nota": "INEI y SUNAT no publican ventas por SKU de un minimarket; esta simulacion reemplaza esa fuente y debe declararse como tal.",
    }
    with open(os.path.join(args.out, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



