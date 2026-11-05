# Windows Remark

Windows 是后续适配目标，当前发布版仅完成 macOS 验证，尚未完成 Windows
实机 agent/桌面验收。平台入口和检查清单见 `platforms/windows/`。先运行
`.venv\Scripts\python.exe start.py --doctor`，只显示版本与依赖，不输出私密路径。

| 现象 | 检查 |
| --- | --- |
| py 找不到 | 安装 Python 3.11+ 并重开终端，也可用 python.exe 完整路径 |
| PowerShell 不允许激活 | 不必修改执行策略，直接使用 .venv\Scripts\python.exe |
| PySide6 安装失败 | 检查 Python/CPU 架构是否有对应 wheel；先用网页模式 |
| 网页无法连接 | 检查启动终端或 work/backend.log，netstat -ano 查看 17321 占用；不要杀未知 PID |
| 防火墙提示 | 只绑定 127.0.0.1，不需公网入站；不要关闭安全软件 |
| Codex 列表为空 | 已加入 Win32 writer-lock 探测但尚待实机验证；检查 CODEX_HOME，明确同意后启用日志兼容 |
| 关闭会话仍显示 | 近期日志回退不证明进程仍在运行，关闭识别待完善 |
| 人工审批漏报 | 同一环境 /hooks 检查 Active、Python 和脚本路径是否存在 |
| 移动目录后失效 | 更新 Hook 绝对路径并重新审核；不要保留两份观察器 |
| 批准后仍 Waiting | 长命令的完成回调可能尚未到达；不要清库或超时伪造解除 |
| 自动审核误报 | reviewer 过滤依赖当前轮日志上下文，缺少上下文的路径仍有限制 |
| SSH 失败 | 安装 OpenSSH Client，先验证密钥与主机信任；界面不保存密码 |
| SSH 到 Windows 失败 | 远端目前要求 POSIX shell + python3，不支持 PowerShell/CMD |
| 中文素材读取失败 | manifest.json 使用 UTF-8，状态键为 working/waiting/error/idle |
| 呱搭未出现 | 发布不附未经授权素材，按 pet/assets/guada/README.md 配置 |

反馈提供系统/Python/agent 版本、doctor 输出、复现步骤和预期/实际状态。
不要上传完整日志、数据库、.codex、.claude、SSH 目录或密钥。
日志片段先去除用户名、路径、地址、会话 ID、命令和聊天正文。
