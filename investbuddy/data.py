DEMO_STOCKS = {"300750.SZ": "宁德时代", "600519.SH": "贵州茅台", "002594.SZ": "比亚迪"}

# Each tuple contains quarterly revenue, parent net profit and period-end PE TTM.
DEMO_VALUES = {
    "300750.SZ": ((1000, 120, 24), (1100, 125, 22)),
    "600519.SH": ((510, 260, 26), (425, 205, 24.5)),
    "002594.SZ": ((1720, 85, 32), (1950, 111, 35)),
}


def query_demo(task):
    symbol = next((code for code in DEMO_STOCKS
                   if task["symbol"] in {code, code.split(".")[0]}), None)
    if symbol is None:
        raise ValueError("不支持该证券的合成示例。")
    first, second = DEMO_VALUES[symbol]
    rows = [
        ("E1", "2026-03-31", "revenue", first[0], "亿元", "单季度营业收入"),
        ("E2", "2026-03-31", "net_income", first[1], "亿元", "单季度归母净利润"),
        ("E3", "2026-03-31", "pe_ttm", first[2], "倍", "期末市盈率 TTM"),
        ("E4", "2026-06-30", "revenue", second[0], "亿元", "单季度营业收入"),
        ("E5", "2026-06-30", "net_income", second[1], "亿元", "单季度归母净利润"),
        ("E6", "2026-06-30", "pe_ttm", second[2], "倍", "期末市盈率 TTM"),
    ]
    evidence = [
        dict(zip(("id", "date", "field", "value", "unit", "basis"), row),
             source="本地合成示例 investbuddy/data.py", symbol=symbol,
             company=DEMO_STOCKS[symbol])
        for row in rows if task["start"] <= row[1] <= task["end"]
    ]
    if not evidence:
        raise ValueError("所选时间范围内没有示例数据。")
    return evidence
