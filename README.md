# 摸鱼哨 · Moyu Whistle

让 agent 干活，需要你时再招呼你。奶蛙伙伴叫 **呱搭 · Guada**，也支持自备素材。

本地优先的多 agent 状态面板：网页、可选悬浮窗口、SSH 远程采集。
运行时不使用 AI 推断状态，不代替用户批准命令。

**跨平台 Beta，尚未完成 Windows 实机验收，不是生产稳定版。**

## 支持范围

| 能力 | 当前情况 |
| --- | --- |
| macOS 网页、API、悬浮窗口 | 本机运行验证 |
| Windows 网页与后端 | 跨平台代码、CI 配置；实机验收待完成 |
| Windows Codex 发现 | 需日志兼容模式，关闭识别尚不可靠 |
| SSH Linux/macOS 远端 | 已实现，真实服务器端到端验收待完成 |
| SSH Windows 远端 | 当前 POSIX 命令构造不支持 |
| Codex 审批 | 需审核 Hooks，长命令恢复等仍有限制 |
| Claude Code | 依赖版本提供会话状态文件，不保证所有版本 |

详见 [已知问题](docs/known-issues.md)。缺少状态证据不代表 agent 空闲。

## 安装与启动

需要 Python **3.11+**。下载 ZIP 解压或 clone 仓库。网页基础模式仅依赖标准库。

Windows（在项目目录运行）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe start.py --doctor
.\.venv\Scripts\python.exe start.py
```

macOS/Linux：

```sh
python3 -m venv .venv
.venv/bin/python start.py --doctor
.venv/bin/python start.py
```

打开 <http://127.0.0.1:17321/>。Ctrl+C 停止前台服务。
也可双击系统对应的 `Start Moyu Whistle` 文件，它优先使用 `.venv`。
后台启动用 `start.py --background`，日志和 PID 在 `work/`，不安装系统服务。

可选 FastAPI：用同一虚拟环境的 Python 执行 `-m pip install -r requirements.txt`。
复现本次 API/测试依赖版本可使用 `-m pip install -r requirements-lock.txt`（不含 Qt）。
可选悬浮窗口：执行 `-m pip install -r floating/requirements.txt`，再执行 `start.py --floating`。
没有 Qt 不影响网页；没有宠物素材仍能显示文字提醒。

## 首次配置

1. 在网页“设置 · 采集与 SSH”设置采集频率（默认 5 秒）和工作时段。
2. 默认最小元数据模式。Codex 详细状态需明确开启日志兼容；它解析本机日志，但只传输和保存状态摘要，不保存正文。
3. 运行 `start.py --install-hooks`，在 Codex `/hooks` 审核观察器，确认 Active。安装不等于启用。
4. 每个用户/运行环境配置一次；换环境或修改 Hook 定义需重新审核。
5. SSH 按 [接入说明](docs/real-agents.md) 部署脚本及密钥，不会因为打开 SSH 终端就自动发现远端。

可见四态：Working / Waiting / Error / Idle。旧输入 done 在界面映射为 Idle。
异步问题卡片的答复关联未完成；权限事件也不一定是人工阻塞，已知自动审核模式会被过滤。

## 数据与更新

- 运行数据在 `work/moyu-whistle.sqlite3` 和旁边的 `.settings.json`，不提交 Git。
- Hook 数据在 `CODEX_HOME/moyu-whistle-hooks.sqlite3`，默认用户的 `.codex`。
- 更新前停止服务并备份；自行修改源码的用户先提交自己的改动再合并。
- 旧安装迁移：`python scripts/migrate_data.py <旧数据库路径> <新数据库路径>`。
  目标必须不存在，使用 SQLite 一致性备份，原文件保留，旁边设置文件也会复制。
- 移动项目目录会改变 Hook 的绝对路径。检查并替换本工具的旧入口、审核新入口，不要并存两份观察器。

## 开发与发布

```sh
python -m unittest discover -s tests -v
node floating/check-whistle.cjs
python scripts/release_check.py
```

CI 配置了三个系统的测试，但配置存在不等于远端运行通过。
参见 [Windows Remark](docs/windows-remark.md)、[架构/API](docs/architecture.md)、
[安全边界](SECURITY.md)、[贡献指南](CONTRIBUTING.md)、[发布检查](docs/release-checklist.md)。

素材需有独立分发授权，原始照片、录屏和未授权动图不随发布包上传。
代码许可待仓库所有者确认；未附许可证时不要假定允许再分发。
