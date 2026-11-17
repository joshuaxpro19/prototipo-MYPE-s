import argparse
import json
import os

import numpy as np
import pandas as pd

START = "2025-11-01"
DAYS = 365
TICKETS = 18250
LINES = 127750
N_SKUS = 1180
N_CLIENTS = 1248
N_DENSE = 214
CATS = {"abarrotes": 0.45, "bebidas": 0.20, "lacteos": 0.20, "limpieza": 0.15}
CAT_LIST = list(CATS)
DOW = np.array([0.90, 0.85, 0.90, 0.95, 1.12, 1.38, 1.08])
MONTH = np.array([1.05, 0.95, 0.98, 1.02, 1.00, 1.03, 1.12, 0.97, 1.00, 1.02, 1.08, 1.32])
HOLIDAYS = {(12, 8), (12, 24), (12, 25), (12, 31), (1, 1), (4, 18), (5, 1), (6, 29), (7, 23), (7, 28), (7, 29), (8, 30), (10, 8)}
CATALOGO = {
    "abarrotes": [
        ("Arroz", ["Costeño", "Paisana", "Faraón"], ["1 kg", "5 kg", "750 g"]),
        ("Aceite", ["Primor", "Cocinero", "Capri"], ["1 L", "900 ml", "500 ml"]),
        ("Azúcar", ["Rubia", "Dulfina"], ["1 kg", "5 kg"]),
        ("Fideo", ["Don Vittorio", "Nicolini"], ["500 g", "250 g", "paquete"]),
        ("Atún", ["Florida", "A-1"], ["170 g", "140 g"]),
        ("Harina", ["Blanca Flor"], ["1 kg", "500 g"]),
        ("Sal", ["Emsal"], ["1 kg"]),
        ("Café", ["Altomayo", "Nescafé"], ["50 g", "100 g"]),
        ("Galleta", ["Soda Field", "Casino"], ["paquete 6", "paquete 3"]),
        ("Conserva", ["Arica", "Paisana"], ["300 g", "400 g"]),
        ("Menestra", ["Costeño", "Paisana"], ["500 g", "1 kg"]),
        ("Avena", ["3 Ositos", "Quaker"], ["300 g", "500 g"]),
    ],
    "bebidas": [
        ("Gaseosa", ["Inca Kola", "Coca-Cola", "Fanta"], ["1.5 L", "500 ml", "3 L"]),
        ("Agua mineral", ["San Mateo", "Cielo"], ["625 ml", "2.5 L"]),
        ("Jugo", ["Frugos", "Pulp"], ["1 L", "250 ml"]),
        ("Cerveza", ["Cusqueña", "Pilsen"], ["330 ml", "650 ml"]),
        ("Bebida rehidratante", ["Electrolight", "Gatorade"], ["500 ml", "1 L"]),
        ("Refresco", ["Kola Real", "Free Tea"], ["1.5 L", "500 ml"]),
        ("Energizante", ["Volt", "Sporade"], ["300 ml", "500 ml"]),
        ("Bebida de soya", ["Ades", "Soy Vida"], ["1 L", "250 ml"]),
    ],
    "lacteos": [
        ("Leche evaporada", ["Gloria", "Laive", "Pura Vida"], ["400 g", "tarro 395 g"]),
        ("Leche fresca", ["Gloria", "Laive"], ["1 L", "900 ml"]),
        ("Yogurt", ["Gloria", "Laive"], ["1 kg", "200 ml"]),
        ("Queso fresco", ["Laive", "Bonlé"], ["250 g", "500 g"]),
        ("Mantequilla", ["Laive", "Bonlé"], ["200 g", "100 g"]),
        ("Manjar blanco", ["Gloria", "Laive"], ["200 g"]),
        ("Crema de leche", ["Gloria"], ["200 ml"]),
        ("Bebida láctea", ["Gloria", "Laive"], ["1 L"]),
    ],
    "limpieza": [
        ("Detergente", ["Bolívar", "Ariel", "Ace"], ["800 g", "2 kg"]),
        ("Lejía", ["Clorox", "Sapolio"], ["1 L", "4 L"]),
        ("Papel higiénico", ["Paracas", "Elite"], ["4 rollos", "12 rollos"]),
        ("Jabón de lavar", ["Bolívar", "Marsella"], ["230 g", "1 kg"]),
        ("Lavavajillas", ["Ayudín", "Sapolio"], ["500 ml", "1 L"]),
        ("Limpiador", ["Poett", "Sapolio"], ["900 ml", "500 ml"]),
        ("Suavizante", ["Downy", "Bolívar"], ["800 ml", "2 L"]),
        ("Franela multiuso", ["Scott", "Paracas"], ["paquete 2", "paquete 4"]),
    ],
}
DESCRIPTORES = ["", "Familiar", "Pack x2", "Premium", "Económico", "Granel", "Oferta", "Edición especial", "Combo", "Individual", "Rinde más", "Exportación"]


def nombre_producto(cat, n):
    producto, marcas, tamanos = CATALOGO[cat][n % len(CATALOGO[cat])]
    idx = n // len(CATALOGO[cat])
    marca = marcas[idx % len(marcas)]
    tam = tamanos[(idx // len(marcas)) % len(tamanos)]
    desc = DESCRIPTORES[(idx // (len(marcas) * len(tamanos))) % len(DESCRIPTORES)]
    return " ".join(p for p in (producto, marca, tam, desc) if p)
GROUPS = {
    "hogar": {"p": 0.38, "activity": 1.00, "lines": 6, "weekend": 0.25, "promo": 1.00},
    "mayorista": {"p": 0.12, "activity": 2.60, "lines": 14, "weekend": 0.25, "promo": 0.50},
    "fin_semana": {"p": 0.31, "activity": 0.45, "lines": 9, "weekend": 0.98, "promo": 0.80},
    "promo_sensible": {"p": 0.19, "activity": 1.30, "lines": 3, "weekend": 0.25, "promo": 3.20},
}


def _nombres(cats):
    pool = {}
    for cat in CAT_LIST:
        pool[cat] = [" ".join(p for p in (prod, marca, tam, desc) if p)
                     for prod, marcas, tamanos in CATALOGO[cat]
                     for marca in marcas for tam in tamanos for desc in DESCRIPTORES]
    idx = {c: 0 for c in CAT_LIST}
    salida = []
    for c in cats:
        n = idx[c]
        idx[c] += 1
        base = pool[c][n % len(pool[c])]
        salida.append(base if n < len(pool[c]) else f"{base} #{n // len(pool[c]) + 1}")
    return salida

def build_skus(rng):
    cats = rng.choice(CAT_LIST, size=N_SKUS, p=list(CATS.values()))
    base = np.empty(N_SKUS)
    base[:N_DENSE] = rng.lognormal(np.log(22.0), 0.58, N_DENSE)
    base[N_DENSE:] = rng.lognormal(np.log(0.12), 0.55, N_SKUS - N_DENSE)
    order = rng.permutation(N_SKUS)
    base, cats = base[order], cats[order]
    ref = {"abarrotes": 6.0, "bebidas": 5.0, "lacteos": 4.2, "limpieza": 9.0}
    price = np.array([rng.lognormal(np.log(ref[c]), 0.30) for c in cats]).round(2)
    shelf = np.array([int(rng.integers(*{"abarrotes": (90, 365), "bebidas": (120, 400),
                                          "lacteos": (5, 21), "limpieza": (365, 720)}[c])) for c in cats])
    return pd.DataFrame({
        "sku_id": ["SKU-%04d" % (i + 1) for i in range(N_SKUS)],
        "nombre": _nombres(cats),
        "categoria": cats,
        "clase_rotacion": np.where(base > 8, "A", np.where(base > 2, "B", np.where(base > 0.6, "C", "D"))),
        "demanda_base": base.round(4),
        "precio": price,
        "costo": (price * rng.uniform(0.70, 0.80, N_SKUS)).round(2),
        "vida_util_dias": shelf,
        "lead_time_dias": rng.integers(2, 8, N_SKUS),
        "proveedor_id": ["PRV-%02d" % (i + 1) for i in rng.integers(1, 43, N_SKUS)],
    })


def build_clients(rng):
    seg = rng.choice(list(GROUPS), size=N_CLIENTS, p=[GROUPS[g]["p"] for g in GROUPS])
    act = np.array([GROUPS[s]["activity"] for s in seg]) * rng.lognormal(0.0, 0.04, N_CLIENTS)
    return pd.DataFrame({
        "cliente_id": ["CLI-%04d" % (i + 1) for i in range(N_CLIENTS)],
        "segmento_latente": seg,
        "actividad": act.round(4),
        "tamano_canasta": [GROUPS[s]["lines"] for s in seg],
        "pago_preferido": rng.choice(["efectivo", "yape", "tarjeta", "plin"], size=N_CLIENTS, p=[0.42, 0.28, 0.22, 0.08]),
        "antiguedad_dias": rng.integers(60, 2000, N_CLIENTS),
    })


def build_promotions(rng, skus, n_weeks):
    p = np.where(skus["demanda_base"].to_numpy() > 2, 0.07, 0.01)
    mask = rng.random((N_SKUS, n_weeks)) < p[:, None]
    idx = np.argwhere(mask)
    disc = rng.choice([0.10, 0.15, 0.20, 0.25, 0.30], size=len(idx), p=[0.30, 0.25, 0.20, 0.15, 0.10])
    mat = np.zeros_like(mask, dtype=float)
    mat[mask] = disc
    return mask, mat


DERIVA_INICIO = None
DERIVA_FACTOR = 1.0


def weekly_lambda(skus, weeks, promo_mask, promo_disc):
    starts = [pd.Period(w, freq="W-MON").start_time for w in weeks]
    month = np.array([s.month for s in starts])
    hol = np.array([1.0 if any(((s + pd.Timedelta(days=k)).month, (s + pd.Timedelta(days=k)).day) in HOLIDAYS
                               for k in range(7)) else 0.0 for s in starts])
    cal = MONTH[month - 1] * np.where(hol > 0, 1.10, 1.0) * (1.0 + 0.004 * np.arange(len(weeks)))
    lift = np.where(promo_mask, 1.0 + 2.2 * promo_disc, 1.0)
    lam = skus["demanda_base"].to_numpy()[:, None] * cal[None, :] * lift
    if DERIVA_INICIO is not None:
        desde = np.array([pd.Period(w, freq="W-MON").start_time >= DERIVA_INICIO for w in weeks])
        lam[:, desde] *= DERIVA_FACTOR
    return lam


def units_to_lines(rng, units, target_lines):
    divisor = 2.05
    for _ in range(3):
        total = 0
        for i, j in np.argwhere(units > 0):
            u = int(units[i, j])
            total += int(np.clip(round(u / divisor), 1, u))
        divisor = max(1.05, divisor * total / target_lines)
    cells = []
    total = 0
    for i, j in np.argwhere(units > 0):
        u = int(units[i, j])
        n = int(np.clip(round(u / divisor), 1, u))
        parts = (rng.multinomial(u - n, np.full(n, 1.0 / n)) + 1).astype(int)
        cells.append([i, j, parts])
        total += n
    guard = 0
    while total != target_lines and guard < 200000:
        guard += 1
        k = int(rng.integers(len(cells)))
        i, j, parts = cells[k]
        if total > target_lines and len(parts) > 1:
            parts = np.delete(parts, int(rng.integers(len(parts))))
            total -= 1
        elif total < target_lines:
            a = int(rng.integers(len(parts)))
            if parts[a] > 1:
                parts[a] -= 1
                parts = np.append(parts, 1)
                total += 1
        cells[k] = [i, j, parts]
    return cells


def allocate(counts, target):
    counts = np.maximum(np.asarray(counts, dtype=float), 1.0)
    scaled = counts * (target / counts.sum())
    base = np.maximum(np.floor(scaled).astype(int), 1)
    while base.sum() > target:
        i = int(np.argmax(base))
        if base[i] > 1:
            base[i] -= 1
        else:
            break
    while base.sum() < target:
        base[int(np.argmin(base / counts))] += 1
    return base


def build_tickets(rng, cells, clients, weeks, units, promo_mask):
    n_weeks = len(weeks)
    seg = clients["segmento_latente"].to_numpy()
    act = clients["actividad"].to_numpy()
    base_lines = np.array([GROUPS[s]["lines"] for s in seg])
    starts = [pd.Period(w, freq="W-MON").start_time for w in weeks]
    wk_units = np.zeros(n_weeks, dtype=int)
    pool = [[] for _ in range(n_weeks)]
    for i, j, parts in cells:
        wk_units[j] += int(parts.sum())
        pool[j].extend([(i, int(q)) for q in parts])
    tix = rng.multinomial(TICKETS, wk_units / wk_units.sum())

    ticket_rows, line_rows = [], []
    tid = 0
    for w in range(n_weeks):
        n = int(tix[w])
        if n == 0:
            continue
        start = starts[w]
        fin = pd.Timestamp(START) + pd.Timedelta(days=DAYS - 1)
        validos = [k for k in range(7) if pd.Timestamp(START) <= start + pd.Timedelta(days=k) <= fin]
        pesos = DOW[np.array(validos)]
        days = rng.choice(validos, size=n, p=pesos / pesos.sum())
        weekend = (start.dayofweek + days) >= 5
        cli = np.empty(n, dtype=int)
        for t in range(n):
            base_w = np.where(seg == "fin_semana", 3.0 if weekend[t] else 0.06, 1.0)
            wts = act * base_w
            cli[t] = int(rng.choice(N_CLIENTS, p=wts / wts.sum()))
        counts = allocate(base_lines[cli], len(pool[w]))
        hours = rng.integers(7, 22, n)
        items = pool[w]
        rng.shuffle(items)
        on_promo = set(np.argwhere(promo_mask[:, w]).ravel().tolist())
        promo_items = [it for it in items if it[0] in on_promo]
        other_items = [it for it in items if it[0] not in on_promo]
        ip = io = 0
        for t in range(n):
            tid += 1
            ticket_rows.append((tid, start + pd.Timedelta(days=int(days[t])), int(hours[t]), int(cli[t])))
            k = int(counts[t])
            take = []
            if seg[cli[t]] == "promo_sensible":
                want_p = int(round(0.75 * k))
                take = promo_items[ip:ip + want_p]
                ip += len(take)
                want_o = k - len(take)
                rest = other_items[io:io + want_o]
                io += len(rest)
                take += rest
            else:
                rest = other_items[io:io + k]
                io += len(rest)
                take = rest
            while len(take) < k and ip < len(promo_items):
                take.append(promo_items[ip])
                ip += 1
            while len(take) < k and io < len(other_items):
                take.append(other_items[io])
                io += 1
            for sku_i, q in take:
                line_rows.append((tid, sku_i, q))
            k += int(counts[t])
    tickets = pd.DataFrame(ticket_rows, columns=["n", "fecha", "hora", "cliente_idx"])
    tickets["ticket_id"] = ["TK-%06d" % i for i in tickets["n"]]
    lineas = pd.DataFrame(line_rows, columns=["n", "sku_idx", "cantidad"])
    lineas["ticket_id"] = ["TK-%06d" % i for i in lineas["n"]]
    return tickets.drop(columns=["n"]), lineas.drop(columns=["n"])


def simulate_inventory(rng, units, weeks, cover=1.15, lead=2, ciclo=2):
    n_skus, n_w = units.shape
    pedido_base = units.mean(axis=1) * cover * ciclo
    stock = np.ceil(pedido_base)
    transit = {}
    rows = []
    for w in range(n_w):
        arr = transit.get(w)
        if arr is not None:
            stock = stock + arr
        dem = units[:, w].astype(float)
        sold = np.minimum(stock, dem)
        lost = dem - sold
        stock = stock - sold
        need = np.full(n_skus, w % ciclo == 0)
        qty = np.where(need, np.maximum(np.ceil(pedido_base) - stock, 0.0), 0.0)
        arrivals = w + lead + (rng.random(n_skus) < 0.12)
        for i in np.argwhere(need).ravel():
            target = int(arrivals[i])
            arr_t = transit.get(target)
            if arr_t is None:
                arr_t = np.zeros(n_skus)
                transit[target] = arr_t
            arr_t[i] += qty[i]
        arr_next = transit.get(w + 1)
        disp = stock + (arr_next if arr_next is not None else np.zeros(n_skus))
        block = pd.DataFrame({
            "sku_id": ["SKU-%04d" % (i + 1) for i in range(n_skus)],
            "ventas_unidades": dem,
            "stock_fin_semana": disp,
            "quiebre": (lost > 0).astype(int),
            "unidades_perdidas": lost,
        })
        block["semana"] = weeks[w]
        rows.append(block)
    return pd.concat(rows, ignore_index=True)


def main():
    global DAYS, TICKETS, LINES, DERIVA_INICIO, DERIVA_FACTOR
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw"))
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--dias", type=int, default=DAYS)
    ap.add_argument("--deriva-inicio", default=None)
    ap.add_argument("--deriva-factor", type=float, default=1.0)
    ap.add_argument("--cover", type=float, default=1.50)
    ap.add_argument("--lead", type=int, default=2)
    args = ap.parse_args()
    DAYS = args.dias
    TICKETS = int(round(50.0 * DAYS))
    LINES = TICKETS * 7
    DERIVA_FACTOR = args.deriva_factor
    DERIVA_INICIO = pd.Timestamp(args.deriva_inicio) if args.deriva_inicio else None
    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    dates = pd.date_range(START, periods=DAYS, freq="D")
    weeks = sorted(pd.Series(dates).dt.to_period("W-MON").astype(str).unique())

    skus = build_skus(rng)
    clientes = build_clients(rng)
    promo_mask, promo_disc = build_promotions(rng, skus, len(weeks))
    lam = weekly_lambda(skus, weeks, promo_mask, promo_disc)
    units = rng.poisson(lam)
    cells = units_to_lines(rng, units, LINES)
    tickets, lineas = build_tickets(rng, cells, clientes, weeks, units, promo_mask)
    inventory = simulate_inventory(rng, units, weeks, cover=args.cover, lead=args.lead)

    tickets["cliente_id"] = clientes["cliente_id"].to_numpy()[tickets["cliente_idx"].to_numpy()]
    anon = np.zeros(len(tickets), dtype=bool)
    anon[rng.choice(len(tickets), size=int(round(0.224 * len(tickets))), replace=False)] = True
    tickets.loc[anon, "cliente_id"] = "ANON"
    tickets["identificado"] = ~anon
    tickets["metodo_pago"] = np.where(anon, "efectivo", clientes["pago_preferido"].to_numpy()[tickets["cliente_idx"].to_numpy()])
    fecha_map = tickets.set_index("ticket_id")["fecha"]

    lineas["sku_id"] = ["SKU-%04d" % (i + 1) for i in lineas["sku_idx"]]
    lineas["fecha"] = lineas["ticket_id"].map(fecha_map)
    lineas["descuento"] = [
        promo_disc[s, (f - pd.Timestamp(START)).days // 7] if 0 <= (f - pd.Timestamp(START)).days // 7 < len(weeks) else 0.0
        for s, f in zip(lineas["sku_idx"].to_numpy(), lineas["fecha"])
    ]
    price = lineas["sku_id"].map(skus.set_index("sku_id")["precio"]).to_numpy()
    lineas["precio_unitario"] = (price * (1 - lineas["descuento"])).round(2)
    lineas["importe"] = (lineas["cantidad"] * lineas["precio_unitario"]).round(2)

    idx = np.argwhere(promo_mask)
    promos = pd.DataFrame({
        "sku_id": skus["sku_id"].to_numpy()[idx[:, 0]],
        "fecha": [pd.Period(weeks[j], freq="W-MON").start_time + pd.Timedelta(days=3) for j in idx[:, 1]],
        "descuento": promo_disc[idx[:, 0], idx[:, 1]],
    })
    promos["tipo"] = rng.choice(["2x1", "descuento", "exhibicion"], size=len(promos), p=[0.25, 0.55, 0.20])
    promos = promos.sort_values(["fecha", "sku_id"]).reset_index(drop=True)

    skus.to_csv(os.path.join(args.out, "skus.csv"), index=False)
    clientes.to_csv(os.path.join(args.out, "clientes.csv"), index=False)
    tickets[["ticket_id", "fecha", "hora", "cliente_id", "identificado", "metodo_pago"]].to_csv(os.path.join(args.out, "tickets.csv"), index=False)
    lineas[["ticket_id", "sku_id", "cantidad", "fecha", "descuento", "precio_unitario", "importe"]].to_csv(os.path.join(args.out, "ticket_lineas.csv"), index=False)
    promos.to_csv(os.path.join(args.out, "promociones.csv"), index=False)
    inventory.to_csv(os.path.join(args.out, "inventario_semanal.csv"), index=False)
    inventory[inventory["quiebre"] == 1].to_csv(os.path.join(args.out, "quiebres.csv"), index=False)

    hist = int((lineas.groupby("sku_id")["fecha"].apply(lambda s: s.dt.to_period("W-MON").nunique()) >= 26).sum())
    meta = {
        "naturaleza": "demo calibrada con datos simulados; reproduce las cifras del informe, no son mediciones del piloto",
        "perfil": "demo",
        "seed": args.seed,
        "inicio": START,
        "dias": DAYS,
        "semanas": len(weeks),
        "skus": int(len(skus)),
        "proveedores": int(skus["proveedor_id"].nunique()),
        "clientes": int(len(clientes)),
        "tickets": int(len(tickets)),
        "lineas_venta": int(len(lineas)),
        "tickets_anonimos_pct": round(float(anon.mean() * 100), 1),
        "skus_con_venta_26_semanas": hist,
        "semanas_sku_con_quiebre_pct": round(float(inventory["quiebre"].mean() * 100), 1),
        "clientes_con_compra_identificada": int(tickets.loc[~anon, "cliente_id"].nunique()),
        "nota": "Los parametros del simulador se ajustaron para que las metricas coincidan con las del APF3. Uso: demostracion local.",
    }
    with open(os.path.join(args.out, "dataset.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
