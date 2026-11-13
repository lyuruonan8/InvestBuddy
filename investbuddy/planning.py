"""Validated, structured planning with a deterministic fallback."""
from dataclasses import dataclass
import json


@dataclass
class MockProvider:
    """Test double. Never used as a live model."""
    response: str
    name = "Mock Provider（测试）"

    def generate(self, context):
        return self.response


TOPICS = {
    "financial": ("财务", "营收", "利润", "收入", "净利", "financial", "revenue", "profit"),
    "valuation": ("估值", "市盈率", "valuation"),
    "risk": ("风险", "risk"),
}
LABELS = {"financial": "财务", "valuation": "估值", "risk": "风险"}


def validate(output):
    def object_pairs(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("重复 JSON 字段")
        return result

    if not isinstance(output, str) or len(output) > 4096:
        raise ValueError("无效规划响应")
    value = json.loads(output, object_pairs_hook=object_pairs)
    if not isinstance(value, dict) or set(value) != {"tools"}:
        raise ValueError("规划只接受工具清单")
    calls = value["tools"]
    if not isinstance(calls, list) or not 1 <= len(calls) <= 3:
        raise ValueError("无效工具数量")
    topics = []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"tool", "arguments"}:
            raise ValueError("无效工具结构")
        if call["tool"] != "research.scope":
            raise ValueError("工具未经授权")
        args = call["arguments"]
        if not isinstance(args, dict) or set(args) != {"topic"}:
            raise ValueError("工具参数无效")
        topic = args["topic"]
        if not isinstance(topic, str) or topic not in TOPICS or topic in topics:
            raise ValueError("研究范围无效")
        topics.append(topic)
    return topics


def make_plan(goal, mode, context=None, provider=None):
    from investbuddy.tools import TOOLS

    topics = [topic for topic, words in TOPICS.items() if any(word in goal.lower() for word in words)]
    strategy = "规则规划（未配置真实 LLM）"
    if provider is not None:
        try:
            topics = TOOLS["research.scope"](provider.generate({"goal": goal, **(context or {})}))
            strategy = provider.name
        except Exception:
            strategy = "模型规划失败，已降级为规则规划"
    if not topics and context:
        recent = context.get("recent", [])
        if recent and "继续" in goal:
            topics = recent[-1]["topics"]
        if not topics:
            preferences = context.get("preferences", [])
            topics = [topic for topic, label in LABELS.items() if f"默认关注{label}" in preferences]
    topics = topics or list(TOPICS)
    query = "finance.query_live" if mode == "live" else "finance.query"
    steps = []
    if {"financial", "valuation"}.intersection(topics):
        steps.extend([
            dict(name="查询" + "与".join(LABELS[t] for t in topics if t != "risk") + "证据",
                 action=query, status="pending", topics=topics),
            dict(name="校验并计算指标", action="finance.calculate", status="pending", topics=topics),
        ])
    if "risk" in topics:
        steps.append(dict(name="整理待核验风险", action="research.risk", status="pending", topics=topics))
    steps.append(dict(name="生成研究报告", action="report", status="pending", topics=topics))
    return steps, strategy
