# 桌面内嵌网页 UI：运行时职责与数据流

本文档说明「正式桌面壳」「房间服务（8765）」「本地网页服务」三者的边界，供维护与排错参考。

## 三者分别做什么

| 组件 | 职责 |
|------|------|
| **房间服务**（FastAPI + WebSocket，默认 `8765`） | 房间真相来源：成员列表、座位、曲目、公共聊天、播放位申请与审批。客户端只通过 WebSocket 协议收发 `snapshot` / `event` / `assigned` 等消息。 |
| **本地网页服务**（Flask + Socket.IO，本机随机或指定端口） | 只服务「嵌在桌面窗口里的那一页」：提供 `index.html` 与静态资源；用 Socket.IO **向该页推送**由桌面端整理好的展示数据（与房间协议解耦后的视图模型）。不替代房间服务，也不对外网暴露业务逻辑。 |
| **桌面壳**（PySide6 + QWebEngineView） | 启动/停止本地网页服务线程；弹出连接向导；维护 `RoomWebSocketWorker`、歌曲检测、`FollowPlaybackController`；把房间快照与事件 **适配** 后交给本地服务广播；通过 **QWebChannel** 让网页调用「发聊天、申请播放位、跟播」等需要回连房间 WebSocket 的操作。 |

## 数据流（简化）

1. 用户填写服务器地址、房间号、昵称 → 桌面连接 `ws://…/ws/room/{roomId}`。
2. 房间服务推送 `snapshot` / `event` → `RoomWebSocketWorker` → 主线程将载荷转为网页用的 `room_snapshot` / `room_event` → Socket.IO 广播给内嵌页。
3. 歌曲检测线程发现曲目变化 → `sendTrackFromDetector` → 仍只发往房间服务；房间内其他成员与本人界面由后续 `snapshot`/`event` 更新。
4. 网页里发聊天、播放位操作 → QWebChannel → 桌面桥接 → `RoomWebSocketWorker` 发送对应 JSON 帧。

## 为何要有本地服务，而不是网页直连房间 WebSocket

- 新版页面最初按 Flask + Socket.IO 演示编写；桌面内嵌后，由 **单一适配层** 把正式房间协议转成页面事件，避免在浏览器里维护两套长连接与鉴权。
- 静态资源与模板路径在开发/打包下可统一由本地服务解析（见 `MF_PROJECT_ROOT` / PyInstaller 资源目录约定）。

## 环境变量（与路径、端口）

- `MF_PROJECT_ROOT`：项目根目录；打包或特殊工作目录下由启动脚本设置，便于找到 `templates/`、`static/`。
- `MF_LOCAL_WEB_UI_PORT`：固定本地网页端口；未设置则自动选可用端口。
- `MF_SERVER_URL` / `MF_AUTO_START_ROOM_SERVER`：仍由 `RunDesktopApp.ps1` 与连接向导使用，行为与原先一致。

## 打包（PyInstaller）注意

- 冻结运行时 `resolve_project_root()` 会优先使用 `sys._MEIPASS`，请在 spec 的 `datas` 中把仓库根下的 `templates/` 与 `static/` 打进包内，并在启动时设置 `MF_PROJECT_ROOT` 指向解压根（与现有 `apps/DesktopApp/Main.py` 对 `_ROOT` 的处理对齐即可）。
- 桌面依赖 `PySide6` 的 **WebEngine** 组件；若精简安装导致 `QtWebEngineWidgets` 缺失，需在目标环境安装完整 WebEngine 支持。
