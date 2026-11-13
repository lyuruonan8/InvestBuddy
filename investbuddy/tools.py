from investbuddy.planning import validate
from investbuddy.data import query_demo
from investbuddy.market_data import query_eastmoney


def calculate(evidence):
    by_date = {}
    for row in evidence:
        by_date.setdefault(row["date"], {})[row["field"]] = row

    metrics = []
    for date, fields in sorted(by_date.items()):
        if not {"revenue", "net_income"} <= fields.keys():
            continue
        revenue = fields["revenue"]
        profit = fields["net_income"]
        if revenue["value"]:
            metrics.append(dict(date=date, metric="归母净利率",
                                value=round(100 * profit["value"] / revenue["value"], 2),
                                unit="%", evidence=[profit["id"], revenue["id"]]))
    pe = sorted((r for r in evidence if r["field"] == "pe_ttm"), key=lambda r: r["date"])
    if len(pe) >= 2:
        metrics.append(dict(date=pe[-1]["date"], metric="区间市盈率变化",
                            value=round(pe[-1]["value"] - pe[0]["value"], 2),
                            unit="倍", evidence=[pe[0]["id"], pe[-1]["id"]]))
    return metrics


TOOLS = {"finance.query": query_demo, "finance.calculate": calculate,
         "finance.query_live": query_eastmoney, "research.scope": validate,
         "research.risk": lambda: "价格竞争、原材料成本和客户集中度待核验；未查询公告。"}
