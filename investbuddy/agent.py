from investbuddy.tools import TOOLS


def plan(goal):
    focus = []
    for topic, keywords in {
        "财务表现": ("财务", "营收", "利润"),
        "估值变化": ("估值", "市盈率"),
        "主要风险": ("风险",),
    }.items():
        if any(keyword in goal for keyword in keywords):
            focus.append(topic)
    scope = "、".join(focus) or "财务、估值与风险概览"
    return [
        dict(name=f"查询证据 · {scope}", action="finance.query", status="pending"),
        dict(name="计算归母净利率及市盈率变化", action="finance.calculate", status="pending"),
        dict(name="整理研究结果及待核验风险", action="report", status="pending"),
    ]


def report(task, evidence, metrics):
    return dict(
        mode="合成示例",
        facts="当前证据来自本地合成数据。表中记录仅用于验证工作流。",
        inference=[
            f'{m["date"]} {m["metric"]}为 {m["value"]} {m["unit"]}（依据 {", ".join(m["evidence"])}）。'
            for m in metrics
        ],
        uncertainty="缺少真实财报、行情及公告。价格竞争、原材料成本与客户集中度为待核验方向，当前无法评估实际影响。"
        + (" 当前区间只有一个样本时点，无法计算估值变化。" if len({r["date"] for r in evidence}) < 2 else ""),
        scope="当前规划器基于关键词，研究覆盖范围限于预设财务与估值指标。",
    )


def execute(task, store, tools=None, on_update=None):
    tools = TOOLS if tools is None else tools

    def update(message):
        store.record(task, message)
        if on_update:
            on_update(task)

    task["status"] = "running"
    update("开始执行")
    evidence, metrics = [], []
    for step in task["steps"]:
        step["status"] = "running"
        update(step["name"] + " · 开始")
        try:
            action = step["action"]
            if action == "finance.query":
                evidence = tools[action](task)
                if not evidence:
                    raise ValueError("数据工具未返回任何证据。")
                step["result"] = evidence
            elif action == "finance.calculate":
                metrics = tools[action](evidence)
                step["result"] = metrics
            else:
                step["result"] = report(task, evidence, metrics)
                task["result"] = dict(report=step["result"], evidence=evidence, metrics=metrics)
        except Exception as exc:
            step["status"] = task["status"] = "failed"
            step["error"] = task["error"] = f"{type(exc).__name__}: {exc}"
            update(step["name"] + " · " + task["error"])
            return task
        step["status"] = "completed"
        update(step["name"] + " · 完成")
    task["status"] = "completed"
    update("任务完成")
    return task
