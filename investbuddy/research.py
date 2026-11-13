"""Resolve thread follow-ups and compact history without altering original tasks."""
import re

from investbuddy.data import DEMO_STOCKS

PREFERENCES = {"默认关注财务", "默认关注估值", "默认关注风险", "优先展示数据限制"}
CONSTRAINTS = ["历史证据仅作上下文；新任务重新查询", "外部取数须按任务审批", "禁止直接买卖建议"]


def validate_goal_privacy(goal):
    if re.search(r"持仓|仓位|持股成本|账户余额|股东账号|证券账户|我的成本|我(?:目前)?持有", goal):
        raise ValueError("请移除个人持仓、仓位或账户信息，再提交公开研究问题。")


def resolve_followup(goal, thread, *, explicit_range=False):
    symbols = set(re.findall(r"(?<!\d)\d{6}(?:\.(?:SZ|SH|BJ))?(?!\d)", goal.upper()))
    inherited = thread["symbol"].upper()
    if any(symbol != inherited and symbol != inherited.split(".")[0] for symbol in symbols):
        raise ValueError("追问包含其他证券代码。请确认研究对象，并为其他证券另建线程。")
    time_terms = r"(?<!\d)(?:19|20)\d{2}(?!\d)|去年|今年|上季度|上季|近[一二三四五六七八九十\d]|最近|近期|昨天|今天"
    if not explicit_range and re.search(time_terms, goal):
        raise ValueError("追问包含新的时间表述。请使用页面上的起止日期明确研究区间。")
    stripped = re.sub(time_terms, "", goal.upper()) if explicit_range else goal.upper()
    for symbol in symbols:
        stripped = stripped.replace(symbol, "")
    company = next((name for code, name in DEMO_STOCKS.items()
                    if inherited in {code, code.split(".")[0]}), None)
    if company:
        stripped = stripped.replace(company, "")
    for word in ( "该公司", "这家公司", "这个", "继续", "请", "帮我", "分析", "比较",
                 "看看", "查看", "关注", "只看", "仅看", "补充", "核验", "解释", "怎样", "如何",
                 "有什么", "变化", "表现", "主要", "年", "财务", "营收", "利润", "收入", "净利",
                 "估值", "市盈率", "风险", "证据", "同比", "和", "及", "与", "呢", "的"):
        stripped = stripped.replace(word, "")
    if not goal.strip() or re.sub(r"[\s，。？！、,.?!]", "", stripped):
        raise ValueError("无法确认追问指代。请明确为当前证券的财务、估值或风险，其他证券请另建线程。")
    return inherited, thread["start"], thread["end"]


def summarize(thread, tasks, threshold):
    if threshold < 1:
        raise ValueError("摘要阈值至少为 1。")
    entries = []
    for task in tasks:
        result = task.get("result") or {}
        evidence = result.get("evidence") or next(
            (step.get("result", []) for step in task["steps"]
             if step["action"] in {"finance.query", "finance.query_live"}), [])
        by_date = {}
        for row in evidence:
            by_date.setdefault(row["date"], []).append(row["id"])
        report = result.get("report", {})
        entries.append(dict(
            task_id=task["id"], status=task["status"], start=task["start"], end=task["end"],
            topics=task["steps"][0].get("topics", []),
            completed=[step["action"] for step in task["steps"] if step["status"] == "completed"],
            evidence_by_date=by_date,
            confirmations=[entry["time"] for entry in task["logs"] if entry.get("event") == "approved"],
            unresolved=[value for value in [task.get("error"), task.get("stop_reason"),
                        *report.get("warnings", []), report.get("uncertainty")] if value],
        ))
    split = max(0, len(entries) - threshold)
    return dict(symbol=thread["symbol"], start=thread["start"], end=thread["end"],
                constraints=CONSTRAINTS, strategy="确定性结构化摘要",
                compressed=entries[:split], recent=entries[split:])
