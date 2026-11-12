from datetime import date
from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from investbuddy.agent import execute, plan
from investbuddy.store import Store


st.set_page_config(page_title="InvestBuddy", layout="wide")
st.title("InvestBuddy 投资研究工作台")
st.warning("演示模式｜全部金融数值为合成示例。规则规划，无模型调用。")
store = Store(Path(__file__).with_name("investbuddy.sqlite3"))

with st.form("research"):
    symbol = st.text_input("股票代码", "300750.SZ").strip().upper()
    goal = st.text_area("研究目标", "研究宁德时代近期财务表现、估值变化及主要风险").strip()
    left, right = st.columns(2)
    start = left.date_input("开始日期", date(2026, 1, 1))
    end = right.date_input("结束日期", date(2026, 6, 30))
    submitted = st.form_submit_button("创建并运行研究", type="primary")

st.subheader("任务执行计划")
progress = st.empty()


def show_progress(task):
    labels = {"pending": "待执行", "running": "执行中", "completed": "已完成", "failed": "失败"}
    progress.table(pd.DataFrame([
        {"步骤": step["name"], "状态": labels[step["status"]]} for step in task["steps"]
    ]))


if submitted:
    if not re.fullmatch(r"[0-9]{6}(?:\.(?:SZ|SH|BJ))?", symbol) or not goal or start > end:
        st.error("请输入有效股票代码、研究目标及起止日期。")
    else:
        task = store.create(symbol, goal, start.isoformat(), end.isoformat(), plan(goal))
        show_progress(task)
        execute(task, store, on_update=show_progress)
        st.session_state["selected_task"] = task["id"]

tasks = {task["id"]: task for task in store.recent()}
if not tasks:
    st.stop()

selected = st.selectbox("研究任务", list(tasks), key="selected_task",
                        format_func=lambda key: f'{tasks[key]["symbol"]} · {key[:8]}')
task = tasks[selected]
show_progress(task)
st.caption(f'任务 ID {selected} | {task["start"]} 至 {task["end"]}')
st.text(task["goal"])
if task["error"]:
    st.error(task["error"])
if task["status"] == "running":
    st.warning("任务尚未结束。若进程已中断，可用相同条件创建新任务。")

if task["result"]:
    result = task["result"]
    st.subheader("数据与证据")
    frame = pd.DataFrame(result["evidence"])
    st.dataframe(frame, hide_index=True)
    pe = frame.loc[frame["field"] == "pe_ttm"].sort_values("date")
    st.plotly_chart(px.line(pe, x="date", y="value", markers=True,
                            title="示例期末市盈率 TTM", labels={"date": "时点", "value": "倍"}))
    st.subheader("研究结果与风险")
    report = result["report"]
    st.write("**事实与证据范围**", report["facts"])
    st.write("**基于示例的计算与分析**")
    for finding in report["inference"]:
        st.write(finding)
    st.write("**不确定信息**", report["uncertainty"])
    st.caption(report["scope"])

with st.expander("执行日志", expanded=bool(task["error"])):
    st.dataframe(pd.DataFrame(task["logs"]), hide_index=True)
