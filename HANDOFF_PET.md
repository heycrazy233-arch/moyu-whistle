# 呱搭 · Guada 交接

摸鱼哨的可选陪伴形象，不替代悬浮窗或网页。用户可自行换图。
四态素材由 pet/assets/guada/manifest.json 映射，固定尺寸显示。
公开包只含模板，用户本机素材保留，不代表获得分发授权。

按 waiting > error > working > idle 聚合显示一只伙伴；点击打开已有状态列表。
状态必须来自共享 API。断线、暂停和未知不能推断为 Idle/Error，应冻结动画并显示采集提示。
隐藏或减少动态效果时停止动画；重复快照不得重新加载 GIF。
素材缺失仍保留文字状态和提醒。限制文件路径、体积和像素尺寸，不执行素材代码。
提醒由唯一原生协调器负责，桌宠不另弹第二次通知。

核心实现 floating/companion.py、waiting_notice.py、alerts.py。
验证脚本 verify_companion.py、verify_alerts.py 使用隔离数据，不写真实服务。
Guada 不局限于奶蛙，DIY 仅替换合法素材，不修改后端的确定性状态逻辑。
