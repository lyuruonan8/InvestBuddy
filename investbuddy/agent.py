from time import monotonic

from investbuddy.tools import TOOLS
from investbuddy.quality import analyze_fuyao, analyze_live

LIVE_QUERIES = {"finance.query_live", "finance.query_fuyao"}
QUERIES = LIVE_QUERIES | {"finance.query"}


def plan(goal, mode="demo"):
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
        dict(name=f"查询证据 · {scope}", action={"live": "finance.query_live", "fuyao": "finance.query_fuyao"}.get(mode, "finance.query"), status="pending"),
        dict(name="计算归母净利率及市盈率变化", action="finance.calculate", status="pending"),
        dict(name="整理研究结果及待核验风险", action="report", status="pending"),
    ]


def live_report(metrics, warnings, facts):
    return dict(
        mode="真实数据",
        facts="证据表列出供应商返回的原始字段。财务数据为累计值，估值时点为交易日。",
        observations=[
            f'{row["date"]} {row["basis"]}为 {row["value"]:,} {row["unit"]}（依据 {row["id"]}）。'
            for row in facts
        ],
        inference=[
            f'{m["date"]} {m["metric"]}为 {m["value"]} {m["unit"]}（依据 {", ".join(m["evidence"])}）。'
            for m in metrics
        ],
        uncertainty="待核验方向包括价格竞争、原材料成本和客户集中度。当前未检索公告或管理层说明，无法确认具体风险及其影响。",
        scope="结果仅用于研究。市盈率变化无法单独判断价格或盈利变化的驱动因素。",
        warnings=warnings,
    )


def report(task, evidence, metrics):
    return dict(
        mode="合成示例",
        symbol=task["symbol"],
        facts="当前证据来自本地合成数据。表中记录仅用于验证工作流。",
        inference=[
            f'{m["date"]} {m["metric"]}为 {m["value"]} {m["unit"]}（依据 {", ".join(m["evidence"])}）。'
            for m in metrics
        ],
        uncertainty="缺少真实财报、行情及公告。价格竞争、原材料成本与客户集中度为待核验方向，当前无法评估实际影响。"
        + (" 当前区间只有一个样本时点，无法计算估值变化。" if sum(row["field"] == "pe_ttm" for row in evidence) == 1 else ""),
        scope="当前规划器基于关键词，研究覆盖范围限于预设财务与估值指标。",
    )


def execute(task, store, tools=None, on_update=None, *, approve=False):
    with store.claim(task["id"]) as claimed:
        current = store.get(task["id"])
        if not claimed or current["status"] in {"completed", "cancelled", "stopped"}:
            return current
        if store.demo_only and (current.get("mode") != "demo" or any(
            step["action"] not in {"finance.query", "finance.calculate", "research.risk", "report"}
            for step in current["steps"]
        )):
            raise PermissionError("公开演示禁止执行此计划。")
        task.update(current)
        return run(task, store, TOOLS if tools is None else tools, on_update, approve)


def run(task, store, tools, on_update, approve):
    def update(message, event, **details):
        store.record(task, message, event=event, **details)
        if on_update:
            on_update(task)

    def stop(status, message):
        task["status"] = status
        task["stop_reason"] = message
        task["result"] = None
        update(message, status)
        return task

    fuyao = task.get("mode") == "fuyao"
    live = task.get("mode") in {"live", "fuyao"}
    vendor = "同花顺扶摇" if fuyao else "东方财富"
    control = task.setdefault("control", dict(max_calls=4, max_seconds=45, calls=0))
    if task.get("cancel_requested"):
        return stop("cancelled", "任务已取消。")
    needs_query = any(step["action"] in LIVE_QUERIES and step["status"] != "completed"
                      for step in task["steps"])
    if (needs_query or control.get("demo_approval")) and not control.get("approved"):
        if not approve:
            if task["status"] != "awaiting_approval":
                task["status"] = "awaiting_approval"
                message = "等待批准运行合成演示。" if store.demo_only else f"等待批准向{vendor}查询数据。"
                update(message, "approval_required")
            return task
        control["approved"] = True
        message = "用户批准运行合成演示。" if store.demo_only else f"用户批准此任务调用{vendor}。"
        update(message, "approved")
        if task.get("cancel_requested"):
            return stop("cancelled", "任务已取消。")

    elapsed_before = control.get("elapsed_seconds", 0)
    started = monotonic()
    task.update(status="running", error=None)
    update("开始或恢复执行", "run_started")
    evidence, metrics, warnings, facts = [], [], [], []
    risk = None
    for step in task["steps"]:
        action = step["action"]
        topics = step.get("topics")
        if step["status"] == "completed":
            if action in QUERIES:
                evidence = step["result"]
            elif action == "finance.calculate":
                metrics = step["result"]
                warnings = step.get("warnings", [])
                facts = step.get("facts", [])
                if live and "warnings" not in step:
                    analysis = (analyze_fuyao(evidence) if fuyao else
                                analyze_live(evidence, task["end"], topics=topics))
                    metrics, warnings, facts = analysis["metrics"], analysis["warnings"], analysis["facts"]
            elif action == "research.risk":
                risk = step["result"]
            elif action == "report":
                task["result"] = dict(report=step["result"], evidence=evidence, metrics=metrics)
            continue
        if store.get(task["id"]).get("cancel_requested"):
            return stop("cancelled", "任务已取消。")
        if elapsed_before + monotonic() - started >= control["max_seconds"]:
            return stop("stopped", "任务达到时延预算。")
        is_tool = action in QUERIES | {"finance.calculate", "research.risk"}
        if is_tool and control["calls"] >= control["max_calls"]:
            return stop("stopped", "任务达到工具调用预算。")
        if is_tool:
            control["calls"] += 1
        step["status"] = "running"
        step.pop("error", None)
        step["attempts"] = step.get("attempts", 0) + 1
        step_started = monotonic()
        update(step["name"] + " · 开始", "step_started", action=action, attempt=step["attempts"])
        if task.get("cancel_requested"):
            step["status"] = "pending"
            return stop("cancelled", "任务已取消。")
        try:
            if action in QUERIES:
                evidence = tools[action]({**task, "topics": topics} if topics else task)
                if topics and not fuyao:
                    evidence = [row for row in evidence if
                                ("valuation" if row["field"] == "pe_ttm" else "financial") in topics]
                if not evidence:
                    raise ValueError("数据工具未返回任何证据。")
                step["result"] = evidence
            elif action == "finance.calculate":
                if live:
                    analysis = (analyze_fuyao(evidence) if fuyao else
                                analyze_live(evidence, task["end"], topics=topics))
                    metrics, warnings, facts = analysis["metrics"], analysis["warnings"], analysis["facts"]
                    step.update(warnings=warnings, facts=facts)
                else:
                    metrics = tools[action](evidence)
                step["result"] = metrics
            elif action == "research.risk":
                risk = step["result"] = tools[action]()
            elif action == "report":
                step["result"] = live_report(metrics, warnings, facts) if live else report(task, evidence, metrics)
                if topics:
                    step["result"]["uncertainty"] = risk or "当前任务未执行风险梳理。"
                    if not evidence:
                        step["result"]["facts"] = "本任务整理待核验方向，未查询金融数据。"
                if fuyao and evidence:
                    step["result"]["facts"] = "同花顺扶摇提供最新行情与估值快照及最近可用年报。证据保留原始字段。"
                    step["result"]["scope"] = "快照和年报不按研究日期区间筛选。当前估值为单点。"
                task["result"] = dict(report=step["result"], evidence=evidence, metrics=metrics)
            else:
                raise ValueError(f"未知步骤 {action}")
        except Exception as exc:
            step["status"] = task["status"] = "failed"
            message = f"{type(exc).__name__}: {exc}"
            if store.demo_only:
                message = "示例区间没有可用数据，请核对日期。" if (
                    isinstance(exc, ValueError) and action == "finance.query"
                ) else "执行失败，可从检查点继续。"
            step["error"] = task["error"] = message
        else:
            step["status"] = "completed"
        step["duration_ms"] = round((monotonic() - step_started) * 1000, 2)
        control["elapsed_seconds"] = elapsed_before + monotonic() - started
        update(step["name"] + " · " + (step.get("error") or "完成"),
               "step_failed" if step.get("error") else "step_completed",
               action=action, duration_ms=step["duration_ms"], calls=control["calls"])
        if task.get("cancel_requested"):
            return stop("cancelled", "任务已取消。")
        if control["elapsed_seconds"] >= control["max_seconds"]:
            return stop("stopped", "任务达到时延预算。")
        if task["status"] == "failed":
            return task
    task["status"] = "completed"
    update("任务完成", "completed")
    return task
