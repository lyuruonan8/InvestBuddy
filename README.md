# InvestBuddy

面向个人投资研究者的本地 Streamlit 工作台。第一阶段提供规则规划、工具执行、证据追溯及 SQLite 任务历史。

## 启动

在项目目录运行以下 PowerShell 命令。已安装依赖时可直接运行最后一行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

浏览器打开 http://127.0.0.1:8501，保留默认输入并点击「创建并运行研究」。
默认范围含 2026-03-31 和 2026-06-30 两个构造样本。数据库文件为 investbuddy.sqlite3，保留最近任务的查询入口。

## 数据与执行边界

- 示例源仅支持 300750 或 300750.SZ。全部金额及估值由项目构造，证据表展示字段、单位、口径、时点和来源。
- 归母净利率 = 单季归母净利润 / 单季营业收入。估值变化 = 区间末个样本 PE TTM 减去首个样本 PE TTM。结论引用证据编号。
- 扶摇文档在本次核验中未能打开。iFinD MCP 公开主页可查，但当前未验证凭证、工具清单及返回字段。本阶段真实金融调用为零。
- 运行无需环境变量或模型密钥。用户目标用于识别预设主题，执行范围固定为样例覆盖的财务和估值。报告为模板，风险方向待真实资料核验。
- 每步执行前后持久化。失败时保留错误及已执行步骤，中断后暂需重建任务。恢复、长期记忆、审批和成本预算留待下一阶段。
- 用于研究流程演示，产物包含事实范围、计算分析和不确定性。

## 测试与 AI 使用

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

覆盖成功链路与证据回溯、取数异常、时间范围无数据和单时点估值边界。
Codex 用于读取题目、查阅数据入口、编写和运行代码与测试。候选人复核与修订记录待实际检查后补充。
