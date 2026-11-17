import heapq
import math


def costs_for(sku):
    margin = max(float(sku["precio"]) - float(sku["costo"]), 0.5)
    return {
        "c_h": round(float(sku["costo"]) * 0.02, 3),
        "c_o": 8.0,
        "c_s": round(margin * 0.6, 3),
        "c_p": round(float(sku["costo"]) * 0.5, 3),
    }


def order_levels(demand):
    return [0.0, 0.25 * demand, 0.5 * demand, 0.75 * demand, float(demand)]


def step_cost(state_stock, order, demand, c):
    after = state_stock + order - demand
    hold = c["c_h"] * max(after, 0.0)
    short = c["c_s"] * max(-after, 0.0)
    fixed = c["c_o"] if order > 0 else 0.0
    merma = c["c_p"] * max(after - 2 * demand, 0.0) * 0.25
    return hold + short + fixed + merma, after


def plan_sku(demand_weeks, sku, beam=200, stock_inicial=0.0):
    c = costs_for(sku)
    levels = order_levels(max(demand_weeks) if demand_weeks else 1.0)
    max_stock = int(math.ceil(4 * max(demand_weeks) + 1 + stock_inicial)) if demand_weeks else 10
    start = (0, float(stock_inicial))
    frontier = [(0.0, 0, start, [])]
    best = {}
    explored = 0
    done = None
    while frontier:
        f, g, (week, stock), path = heapq.heappop(frontier)
        if week == len(demand_weeks):
            done = (g, path)
            break
        key = (week, round(stock, 1))
        if best.get(key, float("inf")) <= g:
            continue
        best[key] = g
        explored += 1
        if explored > beam * 200:
            break
        for q in [0.0] + levels:
            cost, nxt = step_cost(stock, q, demand_weeks[week], c)
            if nxt > max_stock or nxt < -max_stock:
                continue
            heapq.heappush(frontier, (g + cost, g + cost, (week + 1, nxt), path + [{"semana": week + 1, "pedido": round(q, 1), "stock_final": round(nxt, 1), "costo": round(cost, 2)}]))
        if len(frontier) > beam * 50:
            frontier = sorted(frontier)[: beam * 10]
            heapq.heapify(frontier)
    if done is None:
        return {"sku_id": sku["sku_id"], "costo": None, "plan": [], "explorados": explored}
    return {"sku_id": sku["sku_id"], "costo": round(done[0], 2), "plan": done[1], "explorados": explored}


def build_plan(forecast_by_sku, skus, top_n=20):
    sel = skus.sort_values("demanda_base", ascending=False).head(top_n)
    out = []
    for _, row in sel.iterrows():
        demand = [max(float(forecast_by_sku.get(row["sku_id"], row["demanda_base"])) * 1.0, 0.1)] * 4
        res = plan_sku(demand, row)
        res["nombre"] = row["nombre"]
        res["categoria"] = row["categoria"]
        res["lead_time_dias"] = int(row["lead_time_dias"])
        out.append(res)
    return out
