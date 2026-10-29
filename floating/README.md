# Moyu Whistle 悬浮窗口原型

复用现有 loopback 服务与 API，不读取数据库，不启动或重启后端。

先确保现有服务 `http://127.0.0.1:17321/` 正常运行。需要后端时，由后端任务按交接说明启动。

浏览器预览：`http://127.0.0.1:17321/assets/whistle.html`。

开发启动（项目根目录）：

```sh
python3 -m venv .venv-floating
.venv-floating/bin/python -m pip install -r floating/requirements.txt
.venv-floating/bin/python floating/main.py
```

Windows 使用 `.venv-floating\Scripts\python.exe` 替代上述 Python 路径。

短按胶囊或内容空白区展开/收起；Esc 收起；在悬浮窗口任意位置按住约 350 毫秒后移动鼠标可拖动窗口。长按拖动松手不会触发点击；筛选、控制台、× 等按钮短按保留原功能。× 隐藏到菜单栏/托盘；菜单栏摸鱼哨 图标的“显示悬浮窗口”恢复窗口，“退出摸鱼哨”才退出程序。“控制台”在浏览器打开现有设置页面。无系统托盘时 × 回退为最小化。

macOS 完全退出后，可双击本目录的 `Open Moyu Whistle.command` 再次启动（当前机器已安装依赖）。目前控制台不能直接启动原生程序，也没有安装系统 URL 协议。

展示与控制台保持 Working / Waiting / Error / Idle 四态；旧 done 映射为 idle，未知任务状态用采集提示代替任务徽标。Codex 客户端区分桌面窗口和 Terminal。

原生 WaitingMonitor 每 2 秒只读读取现有 API，独立于网页定时器，主窗隐藏后仍工作。可靠 Waiting 弹出带奶蛙挥手动图的醒目提示，不抢焦点、不自动超时消失，点击可显示悬浮窗并筛选等待会话。持续等待不重复弹；解除后再次等待会提醒。首次连接/重连若发现尚未提醒过的可靠 Waiting，也提醒一次，避免遗漏；不可信状态不制造新提醒，断线保留已知等待并标注需核实，不当作已解决。关闭提示仅确认已看到，不代替原会话审批。胶囊同步显示金色等待数量。真正退出程序后不再监测。

奶蛙素材按 `pet/assets/guada/manifest.json` 加载；缺图仍显示文字提醒。隐藏时暂停动图。普通网页预览保留页内提醒；原生模式由唯一原生监测器负责弹窗，网页不重复触发或清除。

四态常驻奶蛙位于悬浮窗旁边，使用同一原生监测快照，优先级 Waiting > Error > Working > Idle。点击展开现有悬浮窗并选择对应筛选，长按约350ms可独立拖动；主窗展开/收起不改变奶蛙坐标，拖动主窗时奶蛙随行。主窗隐藏后奶蛙保留；菜单栏“显示呱搭”可单独隐藏/恢复，“暂停呱搭动画”减少动态效果。状态不可信或服务断开时冻结原形象并显示采集提示，不伪装成空闲。无会话使用休息图，但不增加 Idle 会话数。

Working 是透明 PNG，其他三态保留用户原图背景。Waiting/Error 使用 GIF；同态刷新不重载，隐藏和断线时暂停。素材限定 manifest 目录、10MB文件、400万解码像素，GIF不缓存全部帧；缺失或损坏素材回退文字。此版本未实现自定义导入、缩放和跨重启位置保存。

重要：Codex 后端可靠 Waiting/Error 采集仍未完成，前端弹窗通过隔离测试不代表真实 Codex 审批等待已经端到端接通。不可用日志沉默或 CPU 占用猜测 Waiting。

此版本为开发原型，尚非免环境安装包。原生窗口置顶、拖动、透明度、多屏及全屏行为需要分别在 macOS/Windows 验证。不保证显示在系统全屏窗口之上。后端未启动时显示连接提示并每 5 秒重试；Cmd+Q（macOS）可退出。

隔离展示逻辑检查：`node floating/check-whistle.cjs`。
原生窗口渲染检查：`.venv-floating/bin/python floating/verify_window.py`，连接真实只读 API，验证展开/收起并将窗口截图写入 `系统临时目录下的 moyu-whistle-preview.png` 后退出。
提醒策略检查：`.venv-floating/bin/python -m unittest discover -s floating -p 'test_*.py' -v`。
隔离 HTTP→原生提醒验证：`.venv-floating/bin/python floating/verify_alerts.py`，使用临时 loopback 端口，不修改真实数据库；截图 `系统临时目录下的 moyu-whistle-waiting-guada.png`。
四态桌宠渲染与交互验证：`.venv-floating/bin/python floating/verify_companion.py`；使用隔离界面数据，截图 `系统临时目录下的 moyu-whistle-pet-{state}.png`。
