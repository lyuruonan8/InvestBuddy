"""Read-only Eastmoney Data Center adapter for CATL."""
import json
import math
from datetime import date, datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SOURCE = "东方财富数据中心"
DATASETS = (
    ("RPT_DMSK_FN_INCOME", "REPORT_DATE", {
        "TOTAL_OPERATE_INCOME": ("revenue", "元", "合并利润表年初至报告期末累计营业总收入"),
        "PARENT_NETPROFIT": ("net_income", "元", "合并利润表年初至报告期末累计归母净利润"),
    }),
    ("RPT_VALUEANALYSIS_DET", "TRADE_DATE", {
        "PE_TTM": ("pe_ttm", "倍", "A 股交易日市盈率 TTM（供应商口径）"),
    }),
)


def fetch_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def query_eastmoney(task, fetch=fetch_json):
    if task["symbol"] not in {"300750", "300750.SZ"}:
        raise ValueError("真实模式当前仅支持宁德时代 300750.SZ。")
    start, end = (date.fromisoformat(task[key]) for key in ("start", "end"))
    if start > end or (end - start).days > 366:
        raise ValueError("真实模式支持最长 366 天的研究区间。")

    evidence = []
    topics = task.get("topics", ["financial", "valuation"])
    for report, date_field, fields in DATASETS:
        if ("financial" if date_field == "REPORT_DATE" else "valuation") not in topics:
            continue
        columns = ["SECUCODE", date_field, *fields]
        if date_field == "REPORT_DATE":
            columns.append("NOTICE_DATE")
        url = ENDPOINT + "?" + urlencode({
            "reportName": report, "columns": ",".join(columns),
            "filter": f'(SECURITY_CODE="300750")({date_field}>=\'{start}\')({date_field}<=\'{end}\')',
            "sortColumns": date_field, "sortTypes": "-1", "pageSize": 500,
        })
        payload = fetch(url)
        queried_at = datetime.now(timezone.utc).isoformat()
        if payload.get("success") is not True:
            raise ValueError(f"{SOURCE}查询失败（{report}）。")
        result = payload.get("result")
        if result is None:
            continue
        rows = result["data"]
        if not isinstance(rows, list) or result["pages"] > 1 or result["count"] != len(rows):
            raise ValueError(f"{SOURCE}返回的记录不完整（{report}）。")
        for row in rows:
            if row.get("SECUCODE") != "300750.SZ":
                raise ValueError("供应商返回了不匹配的证券代码。")
            observed = date.fromisoformat(row[date_field][:10])
            if not start <= observed <= end:
                raise ValueError("供应商返回了区间外的记录。")
            disclosed = row.get("NOTICE_DATE")
            for raw_field, (field, unit, basis) in fields.items():
                value = row.get(raw_field)
                if type(value) not in (int, float) or not math.isfinite(value):
                    value = None
                evidence.append(dict(
                    id=f"E{len(evidence) + 1}", date=observed.isoformat(),
                    field=field, value=value, unit=unit, basis=basis, source=SOURCE,
                    source_url=url, raw_field=raw_field, queried_at=queried_at,
                    report_period=observed.isoformat() if date_field == "REPORT_DATE" else None,
                    disclosed_at=disclosed[:10] if disclosed else None,
                    dataset=report, symbol=row["SECUCODE"],
                ))
    return evidence
