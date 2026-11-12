from investbuddy.data import query_demo


def calculate(evidence):
    by_date = {}
    for row in evidence:
        by_date.setdefault(row["date"], {})[row["field"]] = row

    metrics = []
    for date, fields in sorted(by_date.items()):
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


TOOLS = {"finance.query": query_demo, "finance.calculate": calculate}
