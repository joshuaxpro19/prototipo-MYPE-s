import json
import os

import numpy as np
import pandas as pd

MIN_WEEKS = 4
LAGS = (1, 2, 4)
ROLLS = (4, 8)
HOLIDAYS = {(12, 8), (12, 24), (12, 25), (12, 31), (1, 1), (4, 18), (5, 1), (6, 29), (7, 23), (7, 28), (7, 29), (8, 30), (10, 8)}


def load_raw(raw_dir):
    read = lambda n: pd.read_csv(os.path.join(raw_dir, n), parse_dates=["fecha"]) if n in ("tickets.csv", "ticket_lineas.csv", "promociones.csv") else pd.read_csv(os.path.join(raw_dir, n))
    return {
        "skus": read("skus.csv"),
        "clientes": read("clientes.csv"),
        "tickets": read("tickets.csv"),
        "lineas": read("ticket_lineas.csv"),
        "promos": read("promociones.csv"),
        "inventario": read("inventario_semanal.csv"),
        "quiebres": read("quiebres.csv"),
        "meta": json.load(open(os.path.join(raw_dir, "dataset.json"), encoding="utf-8")),
    }


def _shift(arr, k):
    out = np.full(arr.shape, np.nan)
    if k == 0:
        return arr.astype(float)
    out[:, k:] = arr[:, :-k]
    return out


def _rolling(arr, w):
    df = pd.DataFrame(arr).T.rolling(w, min_periods=max(2, w // 2)).mean().T
    return df.to_numpy()


def week_matrix(df, value, index="sku_id", week="semana", fillna=0.0, aggfunc="sum"):
    wide = df.pivot_table(index=index, columns=week, values=value, aggfunc=aggfunc)
    return wide.fillna(fillna)


def sku_week_sales(lineas, tickets, promos):
    s = lineas.drop(columns=["fecha"], errors="ignore").merge(tickets[["ticket_id", "fecha"]], on="ticket_id", how="left")
    s["semana"] = s["fecha"].dt.to_period("W-MON").astype(str)
    agg = s.groupby(["sku_id", "semana"]).agg(
        unidades=("cantidad", "sum"),
        ingresos=("importe", "sum"),
        lineas=("cantidad", "size"),
        tickets=("ticket_id", "nunique"),
        descuento=("descuento", "mean"),
    ).reset_index()
    p = promos.copy()
    p["semana"] = p["fecha"].dt.to_period("W-MON").astype(str)
    pa = p.groupby(["sku_id", "semana"]).agg(promo_share=("descuento", "size"), descuento_prom=("descuento", "mean")).reset_index()
    pa["promo_share"] = 1.0
    agg = agg.merge(pa, on=["sku_id", "semana"], how="left")
    agg["promo_share"] = agg["promo_share"].fillna(0.0)
    agg["descuento_prom"] = agg["descuento_prom"].fillna(0.0)
    return agg


def build_model_table(raw):
    skus = raw["skus"]
    tickets = raw["tickets"]
    lineas = raw["lineas"]
    promos = raw["promos"]
    inv = raw["inventario"].copy()

    agg = sku_week_sales(lineas, tickets, promos)
    weeks = sorted(agg["semana"].unique())
    wk_idx = {w: i for i, w in enumerate(weeks)}
    skus = skus.set_index("sku_id")
    idx = skus.index

    uni = week_matrix(agg, "unidades").reindex(index=idx, columns=weeks).fillna(0.0)
    desc = week_matrix(agg, "descuento_prom").reindex(index=idx, columns=weeks).fillna(0.0)
    pshare = week_matrix(agg, "promo_share").reindex(index=idx, columns=weeks).fillna(0.0)
    stock = week_matrix(inv, "stock_fin_semana").reindex(index=idx, columns=weeks).ffill(axis=1).fillna(0.0)
    quiebre = week_matrix(inv, "quiebre", aggfunc="max").reindex(index=idx, columns=weeks).fillna(0.0)
    perdidas = week_matrix(inv, "unidades_perdidas").reindex(index=idx, columns=weeks).fillna(0.0)

    M = uni.to_numpy()
    n_sku, n_week = M.shape

    feats = {}
    for k in LAGS:
        feats["lag_%d" % k] = _shift(M, k)
    for w in ROLLS:
        feats["ma_%d" % w] = _rolling(_shift(M, 1), w)
        feats["sd_%d" % w] = pd.DataFrame(_shift(M, 1)).T.rolling(w, min_periods=max(2, w // 2)).std().T.to_numpy()
    feats["media_hist"] = pd.DataFrame(_shift(M, 1)).T.expanding(min_periods=4).mean().T.to_numpy()
    feats["promo_share"] = pshare.to_numpy()
    pn = np.full(pshare.shape, np.nan)
    pn[:, :-1] = pshare.to_numpy()[:, 1:]
    feats["promo_share_next"] = pn
    dn = np.full(desc.shape, np.nan)
    dn[:, :-1] = desc.to_numpy()[:, 1:]
    feats["desc_next"] = dn
    dm = desc.to_numpy()
    pr = (dm > 0).astype(float)
    prn = np.full(pr.shape, np.nan)
    prn[:, :-1] = pr[:, 1:]
    feats["promo_sku_next"] = prn
    dsn = np.full(dm.shape, np.nan)
    dsn[:, :-1] = dm[:, 1:]
    feats["desc_sku_next"] = dsn
    wstart = np.array([pd.Period(w, freq="W-MON").start_time for w in weeks])
    hol = np.array([1.0 if any(((wstart[i] + pd.Timedelta(days=k)).month, (wstart[i] + pd.Timedelta(days=k)).day) in HOLIDAYS for k in range(7)) else 0.0 for i in range(len(weeks))])
    hn = np.full((n_sku, n_week), np.nan)
    hn[:, :-1] = hol[None, 1:]
    feats["feriado_next"] = hn
    feats["descuento_prom"] = desc.to_numpy()
    feats["stock"] = stock.to_numpy()
    feats["quiebre_prev"] = quiebre.to_numpy()
    feats["cobertura"] = np.where(_rolling(_shift(M, 1), 4) > 0,
                                  stock.to_numpy() / np.maximum(_rolling(_shift(M, 1), 4), 1e-6), np.nan)
    feats["precio"] = np.repeat(skus["precio"].to_numpy()[:, None], n_week, axis=1)
    feats["lead_time"] = np.repeat(skus["lead_time_dias"].to_numpy()[:, None], n_week, axis=1)
    feats["vida_util"] = np.repeat(skus["vida_util_dias"].to_numpy()[:, None], n_week, axis=1)
    feats["categoria"] = np.repeat(pd.Categorical(skus["categoria"]).codes[:, None], n_week, axis=1)
    feats["mes"] = np.tile(np.array([pd.Period(w, freq="W-MON").start_time.month for w in weeks]), (n_sku, 1))
    feats["semana_anio"] = np.tile(np.arange(n_week), (n_sku, 1))
    feats["tendencia"] = np.tile(np.arange(n_week) / max(n_week - 1, 1), (n_sku, 1))

    target = _shift(M, 0)
    target = np.full_like(M, np.nan)
    target[:, :-1] = M[:, 1:]
    y_cls = np.full_like(M, np.nan)
    y_cls[:, :-1] = (quiebre.to_numpy()[:, 1:] > 0).astype(float)

    idx_sku, idx_week = np.meshgrid(np.arange(n_sku), np.arange(n_week), indexing="ij")
    first_valid = np.min(np.argwhere(~np.isnan(feats["ma_%d" % ROLLS[-1]]))[:, 1])
    mask = (idx_week >= max(MIN_WEEKS, first_valid)) & (idx_week < n_week - 1)

    df = pd.DataFrame({"sku_id": uni.index.to_numpy()[idx_sku[mask]], "semana": np.array(weeks)[idx_week[mask]]})
    for name, arr in feats.items():
        df[name] = arr[idx_sku[mask], idx_week[mask]]
    df["y_demanda"] = target[idx_sku[mask], idx_week[mask]]
    df["y_quiebre"] = y_cls[idx_sku[mask], idx_week[mask]]
    semanas_venta = (M > 0).sum(axis=1)
    df["semanas_con_venta"] = semanas_venta[idx_sku[mask]]
    df = df.dropna(subset=["y_demanda", "y_quiebre"]).reset_index(drop=True)
    return df, uni, quiebre, perdidas, weeks, skus


CLIENT_NUM = ["recencia", "frecuencia", "monetario", "ticket_promedio", "share_finde",
              "share_promo", "n_categorias", "antiguedad", "compras_promedio_mes"]


def client_features(raw):
    tickets = raw["tickets"]
    lineas = raw["lineas"]
    clientes = raw["clientes"]
    promos = raw["promos"].copy()
    promos["semana"] = promos["fecha"].dt.to_period("W-MON").astype(str)
    promo_keys = set(zip(promos["sku_id"], promos["semana"]))

    known = tickets[tickets["identificado"]].copy()
    t = known.merge(clientes[["cliente_id", "antiguedad_dias"]], on="cliente_id", how="left")
    t["semana"] = t["fecha"].dt.to_period("W-MON").astype(str)
    end = tickets["fecha"].max()
    base = t.groupby("cliente_id").agg(
        ultima=("fecha", "max"),
        frecuencia=("ticket_id", "nunique"),
        monetario=("ticket_id", "size"),
        antiguedad=("antiguedad_dias", "max"),
    )
    basket = lineas.merge(t[["ticket_id", "cliente_id", "fecha", "semana"]], on="ticket_id", how="inner")
    ticket_total = basket.groupby("ticket_id")["importe"].sum()
    basket["ticket_total"] = basket["ticket_id"].map(ticket_total)
    per = basket.groupby("cliente_id").agg(ticket_promedio=("ticket_total", "mean"))
    cats = basket.merge(raw["skus"][["sku_id", "categoria"]], on="sku_id", how="left")
    ncat = cats.groupby("cliente_id")["categoria"].nunique().rename("n_categorias")
    out = base.join(per[["ticket_promedio"]]).join(ncat)
    out["recencia"] = (end - out["ultima"]).dt.days
    out["frecuencia"] = out["frecuencia"].astype(float)
    out["monetario"] = basket.groupby("cliente_id")["importe"].sum()
    out["ticket_promedio"] = out["ticket_promedio"].fillna(0.0)
    out["n_categorias"] = out["n_categorias"].fillna(0.0)

    wk = t.groupby(["cliente_id", "semana"]).size().reset_index(name="n")
    out["compras_promedio_mes"] = out.index.map(wk.groupby("cliente_id")["n"].mean())
    finde = t[["cliente_id", "fecha"]].copy()
    finde["finde"] = np.isin(np.asarray(finde["fecha"].dt.dayofweek), [5, 6])
    out["share_finde"] = out.index.map(finde.groupby("cliente_id")["finde"].mean())

    basket["es_promo"] = [k in promo_keys for k in zip(basket["sku_id"], basket["semana"])]
    out["share_promo"] = out.index.map(basket.groupby("cliente_id")["es_promo"].mean())
    out = out.fillna(0.0)
    return out[["recencia", "frecuencia", "monetario", "ticket_promedio", "share_finde",
                "share_promo", "n_categorias", "antiguedad", "compras_promedio_mes"]]


def winsorize(df, p=0.01):
    out = df.copy()
    for c in out.columns:
        lo, hi = out[c].quantile(p), out[c].quantile(1 - p)
        out[c] = out[c].clip(lo, hi)
    return out


if __name__ == "__main__":
    raw = load_raw(os.path.join(os.path.dirname(__file__), "raw"))
    df, _, _, _, weeks, _ = build_model_table(raw)
    print(df.shape, df["semana"].nunique(), df["sku_id"].nunique())
    print(df["y_demanda"].describe())
    print("tasa quiebre:", df["y_quiebre"].mean())
    cf = client_features(raw)
    print(cf.shape)





