DEMO_STOCKS = {"300750.SZ": "宁德时代", "600519.SH": "贵州茅台", "002594.SZ": "比亚迪"}

# Each tuple contains quarterly revenue, parent net profit and period-end PE TTM.
DEMO_VALUES = {
    "300750.SZ": ((1000, 120, 24), (1100, 125, 22)),
    "600519.SH": ((510, 260, 26), (425, 205, 24.5)),
    "002594.SZ": ((1720, 85, 32), (1950, 111, 35)),
}


# Additional synthetic observations. Existing quarter-end evidence IDs stay stable.
DEMO_PE_DATES = ("2026-01-15", "2026-02-13", "2026-03-13",
                 "2026-04-15", "2026-05-15", "2026-06-15")
DEMO_PE_VALUES = {
    "300750.SZ": (24, 24.8, 24.4, 23.1, 22.8, 22.4),
    "600519.SH": (26, 25.4, 25.8, 25.2, 24.7, 24.9),
    "002594.SZ": (32, 31.2, 31.8, 33.4, 34.1, 34.7),
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
    rows.extend(
        (f"E{index}", day, "pe_ttm", value, "倍", "观测日市盈率 TTM")
        for index, (day, value) in enumerate(zip(DEMO_PE_DATES, DEMO_PE_VALUES[symbol]), start=7)
    )
    evidence = [
        dict(zip(("id", "date", "field", "value", "unit", "basis"), row),
             source="本地合成示例 investbuddy/data.py", symbol=symbol,
             company=DEMO_STOCKS[symbol])
        for row in rows if task["start"] <= row[1] <= task["end"]
    ]
    if not evidence:
        raise ValueError("所选时间范围内没有示例数据。")
    return evidence
