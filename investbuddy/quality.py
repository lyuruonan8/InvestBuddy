"""Validate the evidence before computing any research conclusions."""
from collections import defaultdict
from datetime import date

from investbuddy.tools import calculate

FIELDS = {"revenue", "net_income", "pe_ttm"}


def analyze_live(evidence, end, today=None, topics=None):
    cutoff = min(date.fromisoformat(end), today or date.today())
    warnings = []
    grouped = defaultdict(list)
    blocked = set()
    for row in evidence:
        grouped[row["field"], row["date"]].append(row)
    usable = {}
    for (field, observed), rows in sorted(grouped.items()):
        valid = [row for row in rows if row["value"] is not None]
        if len(valid) != len(rows):
            warnings.append(f"{observed} {field} 缺失（{', '.join(row['id'] for row in rows)}）。")
            blocked.add(field)
        signatures = {(row["value"], row["unit"], row["basis"]) for row in valid}
        if len(signatures) > 1:
            detail = "；".join(f"{row['id']} {row['source']} {row['value']} {row['unit']}（{row['basis']}）"
                               for row in valid)
            warnings.append(f"{observed} {field} 来源冲突：{detail}。")
            blocked.add(field)
        if valid:
            usable[field, observed] = valid[0]
    expected = FIELDS if topics is None else (
        ({"revenue", "net_income"} if "financial" in topics else set())
        | ({"pe_ttm"} if "valuation" in topics else set()))
    for field in sorted(expected):
        dates = [date.fromisoformat(observed) for key, observed in usable if key == field]
        limit = 150 if field != "pe_ttm" else 10
        if not dates:
            warnings.append(f"{field} 缺少可用数据。")
            blocked.add(field)
        elif (cutoff - max(dates)).days > limit:
            warnings.append(f"{field} 数据过期：最近时点 {max(dates)}，距区间有效结束日超过 {limit} 天。")
            blocked.add(field)

    financial = []
    financial_fields = {"revenue", "net_income"}
    periods = sorted({observed for field, observed in grouped if field in financial_fields})
    for observed in periods:
        if not all((field, observed) in usable for field in financial_fields):
            warnings.append(f"{observed} 财务字段不齐，无法形成完整的财务分析。")
            blocked.update(financial_fields)
    if not blocked & financial_fields:
        financial = [row for (field, _), row in usable.items() if field in financial_fields]
        if any(row["value"] <= 0 for row in financial if row["field"] == "revenue"):
            warnings.append("营业总收入存在非正值，无法计算归母净利率。")
            financial = []

    pe = [row for (field, _), row in usable.items() if field == "pe_ttm"]
    if len(pe) == 1:
        warnings.append("只有一个有效估值时点，无法计算市盈率变化。")
    if any(row["value"] <= 0 for row in pe):
        warnings.append("市盈率存在非正值，暂停区间估值比较。")
        blocked.add("pe_ttm")
    valuation = [] if "pe_ttm" in blocked else pe
    metrics = calculate(financial) + calculate(valuation)
    latest = max((row["date"] for row in financial), default=None)
    facts = [row for row in financial if row["date"] == latest]
    if latest:
        current = date.fromisoformat(latest)
        previous = current.replace(year=current.year - 1).isoformat()
        for field, label in (("revenue", "累计营业总收入同比"), ("net_income", "累计归母净利润同比")):
            base = usable.get((field, previous))
            current_row = usable[field, latest]
            if base and base["value"] > 0:
                metrics.append(dict(date=latest, metric=label,
                                    value=round(100 * (current_row["value"] / base["value"] - 1), 2),
                                    unit="%", evidence=[current_row["id"], base["id"]]))
    return {"metrics": metrics, "warnings": warnings, "facts": facts}

def analyze_fuyao(evidence, today=None):
    """Analyze the latest annual report and independently dated snapshots."""
    from datetime import datetime
    from investbuddy.fuyao_data import MARKET_TZ

    today = today or datetime.now(MARKET_TZ).date()
    warnings = ["扶摇仅提供最新估值快照，无法计算区间市盈率变化。"]
    facts = []
    for row in evidence:
        age = (today - date.fromisoformat(row["date"])).days
        limit = 550 if row["report_period"] else 10
        if age < 0 or age > limit:
            warnings.append(f'{row["raw_field"]} 数据过期或日期超前（{row["date"]}，{row["id"]}）。')
        else:
            facts.append(row)
    fields = {row["field"]: row for row in facts}
    revenue, profit = fields.get("operating_income"), fields.get("net_income")
    metrics = []
    if revenue and profit:
        if revenue["value"] > 0:
            metrics.append(dict(date=revenue["date"], metric="年报归母净利润 / 营业收入",
                                value=round(100 * profit["value"] / revenue["value"], 2),
                                unit="%", evidence=[profit["id"], revenue["id"]]))
        else:
            warnings.append("营业收入非正，无法计算比率。")
    return {"metrics": metrics, "warnings": warnings, "facts": facts}
