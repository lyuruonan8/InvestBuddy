# 部署说明

推荐 Streamlit Community Cloud，使用现有私有 GitHub 仓库和独立的公开演示应用。平台应用访问设置与仓库可见性分开管理。部署时选 Python 3.11、待提交的发布分支和入口 app.py。

## 安全边界

- 默认配置为 public-demo。平台可以保持默认值，不设置 INVESTBUDDY_PROFILE=local。该值只用于可信本机环境。
- 公开端仅接受预设研究目标和合成样例。应用层隐藏真实选项，任务存储和执行器也拒绝真实计划。公开审批用于演示同一工作流。
- 每个 Streamlit 连接由服务器创建独立临时目录和 SQLite，任务、线程、偏好及锁文件均位于该目录。连接状态只持有服务器创建的工作区对象。应用无账户登录和跨连接认领机制，同一连接内可恢复，刷新后可能重开连接，服务重启后也不承诺恢复。无公开入口指向原本机数据库。
- 连接内最多创建 12 个任务。公网资源消耗仍受平台配额约束，尚无跨连接限流。
- 东方财富法律声明限制未经许可复制、传播及展示内容，服务协议也对行情数据的提供和衍生用途提出限制。未取得针对本应用的公开展示许可，线上版只使用合成数据。[法律声明](https://about.eastmoney.com/home/disclaimer) · [服务协议](https://about.eastmoney.com/home/protocol)
- Community Cloud 本地文件无持久性保证。如果未来要求跨设备保存个人数据，应先引入身份认证、服务端所有权检查和有备份的持久数据库，再验证恢复。[平台存储说明](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)

## 上线步骤

1. 用户审阅本地变更并批准发布分支的提交和推送。仓库保持私有。
2. 用户登录 Streamlit Community Cloud，连接 GitHub，授权其读取 InvestBuddy 私有仓库，并确认自己有该仓库管理权限。[连接 GitHub](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account)
3. 创建应用并选择仓库、发布分支、app.py 和 Python 3.11。默认公开演示无需任何密钥。等 Linux 构建和应用启动通过后，再在应用 Sharing 中设置评审可访问。评审要求匿名访问时，设置应用公开，仓库仍可保持私有。[部署](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [应用共享](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
4. 用两个互不共享浏览器存储的窗口验证合成标识、任务审批、报告、异常提示及历史隔离。确认评审能访问 URL。按测评流程提供可读取的源码入口，私有仓库可能需要用户单独授予评审权限。
5. 最终提交附应用 URL、源码入口、README、AI 使用与验证记录和测试说明。演示视频为可选项。
