def query_demo(task):
    if task["symbol"] not in {"300750", "300750.SZ"}:
        raise ValueError("示例库仅覆盖宁德时代 300750.SZ。")
    rows = [
        ("E1", "2026-03-31", "revenue", 1000, "亿元", "单季度营业收入"),
        ("E2", "2026-03-31", "net_income", 120, "亿元", "单季度归母净利润"),
        ("E3", "2026-03-31", "pe_ttm", 24, "倍", "期末市盈率 TTM"),
        ("E4", "2026-06-30", "revenue", 1100, "亿元", "单季度营业收入"),
        ("E5", "2026-06-30", "net_income", 125, "亿元", "单季度归母净利润"),
        ("E6", "2026-06-30", "pe_ttm", 22, "倍", "期末市盈率 TTM"),
    ]
    evidence = [
        dict(zip(("id", "date", "field", "value", "unit", "basis"), row),
             source="本地合成示例 investbuddy/data.py")
        for row in rows if task["start"] <= row[1] <= task["end"]
    ]
    if not evidence:
        raise ValueError("所选时间范围内没有示例数据。")
    return evidence
