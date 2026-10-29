# 摸鱼哨开发交接

产品名：摸鱼哨 / Moyu Whistle；仓库 moyu-whistle；奶蛙角色呱搭 / Guada。
目标：本地优先、确定性、最小数据采集的多 coding agent 状态中心。
展示亲切，代码和安全边界严格。当前发布阶段 Beta，不能称生产稳定版。

## 分工与接口

后端拥有采集、SQLite、设置和四态契约；前端通过 HTTP 使用状态，不直读数据库。
网页、悬浮窗和桌宠共享接口，新增字段保持可选，参考 docs/architecture.md。
原生提醒由 floating/alerts.py 协调，不额外启动第二个采集器或重复通知器。
不注入模拟生产会话，不替用户批准命令，不更改用户的安全策略。

## 状态现状

可见 Working / Waiting / Error / Idle；旧 done 输入映射为 Idle。
不可靠采集独立提示，不能伪装成 Idle。
日志读取需明确同意；自动审核 reviewer 在当前轮上下文可用时过滤。
Hook 定义安装后需用户审核，安装不代表 Active。
Bash/apply_patch 请求匹配忽略审批专用 description，MCP 参数仍全部参与摘要。
Hook 数据只存摘要、标识和有界回执，不存命令正文。
异步问题的必要性和答复关联尚未实现。长命令获批后立即解除 Waiting 尚未完成。

## 发布边界

Windows 本地发现/关闭识别和原生 UI 尚需实机验证。
SSH 当前仅支持 POSIX 远端。详情见 README、Windows Remark 和已知问题。
不发布用户的日志、数据库、录屏或未经授权的素材。
源码目录移动后要核对本机已安装 Hook 的绝对路径。
完整验证包括 Python 测试、JS 测试、原生 UI、真实人工审批和 GitHub CI。
