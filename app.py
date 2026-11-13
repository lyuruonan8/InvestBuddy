from datetime import date, timedelta
from pathlib import Path
import logging
import math
import re
from threading import Thread

import plotly.graph_objects as go
import streamlit as st

from investbuddy.agent import execute
from investbuddy.data import DEMO_STOCKS
from investbuddy.planning import make_plan
from investbuddy.research import PREFERENCES, resolve_followup, summarize, validate_goal_privacy
from investbuddy.store import Store
from investbuddy.runtime import DemoWorkspace, profile


st.set_page_config(page_title="InvestBuddy", layout="wide")
st.title("InvestBuddy 投资研究工作台")

public_demo = profile() == "public-demo"
if public_demo:
    st.warning("公开演示｜所有金融数值均为合成示例。此连接的任务和偏好为临时记录。")
    if "demo_workspace" not in st.session_state:
        st.session_state["demo_workspace"] = DemoWorkspace()
    workspace = st.session_state["demo_workspace"]
    store = workspace.store
else:
    workspace = None
    store = Store(Path(__file__).with_name("investbuddy.sqlite3"))

threads = {thread["id"]: thread for thread in store.threads()}
if "next_thread" in st.session_state:
    st.session_state["thread_selector"] = st.session_state.pop("next_thread")
thread_key = st.selectbox("研究线程", ["new", *threads] if public_demo else ["new", *threads, "legacy"],
                          format_func=lambda key: "新建线程" if key == "new" else
                          "早期独立任务" if key == "legacy" else f'{threads[key]["symbol"]} · {key[:8]}', key="thread_selector")
thread = threads.get(thread_key)
threshold = st.number_input("保留近期任务数（更早任务生成摘要）", min_value=1, max_value=30, value=3)
preferences = store.preferences()
with st.expander("跨线程长期偏好"):
    preference = st.selectbox("选择非敏感研究偏好", sorted(PREFERENCES))
    if st.button("保存此偏好"):
        store.save_preference(preference)
        st.rerun()
    for saved in preferences:
        st.text(saved)
        if st.button(f"删除「{saved}」", key=f"delete_{saved}"):
            store.delete_preference(saved)
            st.rerun()

with st.form("research"):
    mode = st.selectbox("数据模式", ["demo"] if public_demo else ["live", "demo", "fuyao"],
                        format_func=lambda value: {"live": "真实数据 · 东方财富", "demo": "演示 · 合成数据",
                                                   "fuyao": "真实数据 · 扶摇"}[value])
    if public_demo:
        symbol = st.selectbox("股票", [thread["symbol"]] if thread else list(DEMO_STOCKS),
                              format_func=lambda code: f"{DEMO_STOCKS[code]} · {code}",
                              disabled=bool(thread), key=f"symbol_{thread_key}")
    else:
        symbol = st.text_input("股票代码", thread["symbol"] if thread else "300750.SZ",
                               disabled=bool(thread), key=f"symbol_{thread_key}").strip().upper()
    if public_demo:
        options = ["分析财务、估值及风险", "财务表现", "估值变化", "主要风险"]
        if thread:
            options.append("继续")
        goal = st.selectbox("在本线程中追问" if thread else "研究目标", options, key=f"goal_{thread_key}")
    else:
        goal = st.text_area("在本线程中追问" if thread else "研究目标",
                        "" if thread else "研究宁德时代近期财务表现、估值变化及主要风险",
                        key=f"goal_{thread_key}",
                        help="研究目标会保存在本机，请勿输入持仓、账户或其他敏感信息。").strip()
    change_range = st.checkbox("明确指定新的研究区间") if thread else False
    left, right = st.columns(2)
    start_default = date.fromisoformat(thread["start"]) if thread else (date(2026, 1, 1) if public_demo else date.today() - timedelta(days=365))
    end_default = date.fromisoformat(thread["end"]) if thread else (date(2026, 6, 30) if public_demo else date.today())
    start = left.date_input("开始日期", start_default, key=f"start_{thread_key}")
    end = right.date_input("结束日期", end_default, key=f"end_{thread_key}")
    with st.expander("执行预算"):
        max_calls = st.number_input("最多工具调用次数", min_value=1, max_value=20, value=4)
        max_seconds = st.number_input("执行时延预算（秒）", min_value=1, max_value=300, value=45)
    submitted = st.form_submit_button("创建并运行研究", type="primary")

def start_task(task, *, approve=False):
    def work(workspace=workspace):
        try:
            execute(task, store, approve=approve)
        except Exception:
            logging.getLogger(__name__).exception("Task execution interrupted: %s", task["id"])

    Thread(target=work, daemon=True).start()


if submitted:
    try:
        if public_demo and len(store.recent()) >= 12:
            raise ValueError("本次连接已达到 12 个演示任务。请重新打开页面开始新的演示。")
        if not re.fullmatch(r"[0-9]{6}(?:\.(?:SZ|SH|BJ))?", symbol) or not goal or start > end:
            raise ValueError("请输入有效股票代码、研究目标及起止日期。")
        if thread:
            symbol, inherited_start, inherited_end = resolve_followup(goal, thread, explicit_range=change_range)
            if not change_range:
                start, end = date.fromisoformat(inherited_start), date.fromisoformat(inherited_end)
        validate_goal_privacy(goal)
        active_thread = thread or store.create_thread(symbol, start.isoformat(), end.isoformat())
        context = summarize(active_thread, store.thread_tasks(active_thread["id"]), threshold)
        steps, planning = make_plan(goal, mode, {**context, "preferences": preferences})
        task = store.create(symbol, goal, start.isoformat(), end.isoformat(), steps,
                            mode=mode, max_calls=max_calls, max_seconds=max_seconds,
                            thread_id=active_thread["id"], planning=planning, context=context)
        if mode in {"live", "fuyao"} or public_demo:
            execute(task, store)
        else:
            start_task(task)
        st.session_state[f'selected_task_{active_thread["id"]}'] = task["id"]
        if not thread:
            st.session_state["next_thread"] = active_thread["id"]
            st.rerun()
    except ValueError as exc:
        st.error(str(exc))


@st.fragment(run_every=1)
def task_panel():
    history = store.thread_tasks(thread_key) if thread else [
        task for task in store.recent() if not task.get("thread_id")] if thread_key == "legacy" else []
    tasks = {task["id"]: task for task in reversed(history)}
    if not tasks:
        return

    selected = st.selectbox("研究任务", list(tasks), key=f"selected_task_{thread_key}",
                            format_func=lambda key: f'{tasks[key]["symbol"]} · {key[:8]}')
    task = tasks[selected]
    st.subheader("任务执行计划")
    labels = {"pending": "待执行", "running": "执行中", "completed": "已完成", "failed": "失败"}
    for step in task["steps"]:
        timing = f' · {step["duration_ms"]:.0f} ms' if "duration_ms" in step else ""
        st.markdown(f'- {labels[step["status"]]} · {step["name"]}{timing}')
    control = task.get("control", {})
    if control:
        st.caption(f'工具调用 {control["calls"]}/{control["max_calls"]} · '
                   f'已记录执行时间 {control.get("elapsed_seconds", 0):.2f}/{control["max_seconds"]} 秒')
    status = task["status"]
    with store.claim(task["id"]) as available:
        pass
    if status == "awaiting_approval" or (status == "pending" and task.get("mode") in {"live", "fuyao"}):
        if public_demo:
            st.info("批准后运行本地合成样例。")
        elif task.get("mode") == "fuyao":
            st.info("批准后向扶摇查询证券代码对应的最新快照和年报。")
        else:
            st.info("批准后将向东方财富发送证券代码和日期区间。研究目标留在本机。")
        if st.button("批准运行演示" if public_demo else "批准真实取数", key=f'approve_{selected}'):
            start_task(task, approve=True)
    elif available and status in {"failed", "running", "pending"}:
        if st.button("从检查点继续", key=f'resume_{selected}'):
            start_task(task)
    if status in {"running", "awaiting_approval", "pending", "failed"}:
        if st.button("取消任务", key=f'cancel_{selected}', disabled=bool(task.get("cancel_requested"))):
            store.request_cancel(selected)
            st.rerun()
    if task.get("stop_reason"):
        st.warning(task["stop_reason"])
    elif status == "cancelled":
        st.warning("任务已取消。")
    elif task.get("cancel_requested"):
        st.info("已请求取消。当前调用结束后停止。")
    elif status == "running" and available:
        st.warning("上次执行已中断，可以从检查点继续。")
    st.caption(f'任务 ID {selected} | {task["start"]} 至 {task["end"]}')
    st.text(task["goal"])
    if task.get("planning"):
        st.caption(task["planning"])
    if thread:
        context = task.get("context") or {}
        with st.expander("此任务使用的线程上下文"):
            st.json(context, expanded=1)
    live = task.get("mode") in {"live", "fuyao"}
    if not live:
        st.warning("演示模式｜全部金融数值为合成示例。")
    if task["error"]:
        st.error(task["error"])
        if live:
            st.info("如需查看合成样例，请在数据模式中选择演示，再创建独立任务。样例区间可设为 2026-01-01 至 2026-06-30。")

    if task["result"]:
        result = task["result"]
        code = task["symbol"]
        label = f"{DEMO_STOCKS[code]} · {code}" if code in DEMO_STOCKS else code
        st.subheader(f"数据与证据 · {label}")
        evidence = result["evidence"]
        with st.expander(f"原始证据 · {len(evidence)} 条"):
            selected_ids = st.multiselect("按证据编号筛选", [row["id"] for row in evidence])
            st.json([row for row in evidence if not selected_ids or row["id"] in selected_ids], expanded=1)
            for url in dict.fromkeys(row["source_url"] for row in evidence if "source_url" in row):
                st.markdown(f"[查看供应商原始响应]({url})")
        pe = sorted((row for row in evidence if row["field"] == "pe_ttm"), key=lambda row: row["date"])
        fuyao = task.get("mode") == "fuyao"
        if fuyao:
            pe = [row for row in pe if type(row["value"]) in (int, float) and math.isfinite(row["value"])]
        timepoints = {row.get("data_at") or row["date"] for row in pe} if fuyao else set()
        if fuyao and len(timepoints) == 1:
            latest = pe[-1]
            st.metric(f"{label} · 当前 PE TTM", f'{latest["value"]} 倍')
            st.caption(f'数据时点 {latest.get("data_at") or latest["date"]} · 证据 {latest["id"]}')
            st.info("仅有最新估值快照，暂不能计算历史估值变化")
        elif pe:
            chart = go.Figure()
            for source in sorted({row["source"] for row in pe}):
                rows = [row for row in pe if row["source"] == source]
                chart.add_scatter(x=[(row.get("data_at") or row["date"]) if fuyao else row["date"] for row in rows], y=[row["value"] for row in rows],
                                  mode="markers" if live or len(rows) == 1 else "lines+markers",
                                  name=source,
                                  hovertemplate="%{x}<br>市盈率 TTM %{y} 倍<extra></extra>")
            chart_title = "原始市盈率 TTM 记录" if live else "合成示例市盈率 TTM"
            if fuyao:
                chart_title = "扶摇估值观测 · PE TTM"
            chart.update_layout(title=f"{label} · {chart_title}",
                                xaxis_title="时点" if live else f"观测日期 · {label} · 合成示例",
                                yaxis_title="倍" if live else f"市盈率 TTM（倍） · {label} · 合成示例")
            st.plotly_chart(chart)
            if not live:
                st.caption(f"{label} · 合成示例。点为构造观测值，连线用于展示区间走势。")
                if len(pe) == 1:
                    st.info("区间内只有一个估值观测点，数据不足，无法计算区间市盈率变化。")
        st.subheader(f"研究结果与风险 · {label}")
        report = result["report"]
        st.write("**事实与证据范围**", report["facts"])
        for fact in report.get("observations", []):
            st.write(fact)
        for warning in report.get("warnings", []):
            st.warning(warning)
        st.write("**确定性计算与分析**" if live else "**基于示例的计算与分析**")
        if not report["inference"]:
            st.info("可用证据不足，未生成分析结论。")
        for finding in report["inference"]:
            st.write(finding)
        st.write("**不确定信息**", report["uncertainty"])
        st.caption(report["scope"])

    with st.expander("执行日志", expanded=bool(task["error"])):
        for entry in task["logs"]:
            st.text(f'{entry["time"]} · {entry["message"]}')


task_panel()
