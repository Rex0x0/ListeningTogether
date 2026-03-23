# 旧代码盘点与迁移说明

本文档对应重构计划中的「旧入口 / 旧协议 / 可复用逻辑 / 淘汰名单」梳理结果。

## 旧入口（启动即主路径）

| 文件 | 说明 | 处置 |
|------|------|------|
| `MusicFriend.py` | Tk + 网易云单曲展示，无房间 | **淘汰** |
| `desktop_app.py` | 历史桌面入口 | **淘汰** |
| `desktop_assistant.py` | CLI 上报歌曲；内含 `get_current_netease_song`（Win 窗口标题） | **淘汰入口**；检测逻辑迁至 `src/MusicFriend/Integrations` |
| `pure_desktop_app.py` | Win Qt：HTTP 轮询 + Flask-SocketIO 聊天 | **淘汰**；由 `apps/DesktopApp/Main.py` 替代 |
| `pure_desktop_app_mac.py` | Mac Qt：仅 Spotify + HTTP 轮询 | **淘汰**；统一桌面入口 |
| `app.py` | Flask + SocketIO 全局 `room_state` | **淘汰**；由 `apps/RoomServer/Main.py` + FastAPI 替代 |

## 旧协议（客户端 ↔ 服务端）

| 协议 | 说明 | 处置 |
|------|------|------|
| `POST /update_state` JSON：`user`, `song`, `platform`, `art_url` | 无房间、键为用户昵称 | **淘汰** |
| `GET /get_state` → 全局 dict | 轮询全量状态 | **淘汰** |
| SocketIO：`send_message` / `new_message` | 与歌曲状态服务耦合在同一 Flask 进程 | **淘汰**（首迭代不实现聊天；新协议预留 `chatMessageSent`） |

## 可复用逻辑（思路与实现参考）

| 来源 | 可复用内容 |
|------|------------|
| `spotify_detector.py` | SpotifyOAuth、当前播放 API、封面 URL | 迁移为 `SpotifyProvider`（凭证改环境变量） |
| `netease_api_utils.py` | pyncm 搜封面 | 迁入 `NetEaseWindowsProvider` / 共享工具模块 |
| `desktop_assistant.get_current_netease_song` | Win32 窗口类名 `OrpheusBrowserHost` | 迁入 `NetEaseWindowsProvider` |
| `pure_desktop_app.py` | `SeatWidget` 布局与样式、`SongDetectorWorker` 节奏 | 迁入 `src/MusicFriend/Desktop/` 并改为 WebSocket |

## 淘汰名单（首迭代完成后可归档或删除）

- `MusicFriend.py`, `desktop_app.py`, `desktop_assistant.py`（入口）
- `pure_desktop_app.py`, `pure_desktop_app_mac.py`
- `app.py`, `templates/`, `static/`（若仍存在）
- `spotify_client.py`, `netease_client.py`（若与旧 Tk 链路绑定且无人使用）

**保留**：本 `legacy/` 说明与根目录旧文件在闭环验证前可暂不物理删除，与计划「旁路重构」一致。

## 新正式发布路径

- 桌面：`apps/DesktopApp/Main.py`（PySide6，Win/Mac 同入口）
- 房间服务：`apps/RoomServer/Main.py`（FastAPI + WebSocket）

## Spotify 凭证（新桌面路径）

新实现从环境变量读取：`SPOTIFY_CLIENT_ID`、`SPOTIFY_CLIENT_SECRET`，可选 `SPOTIFY_REDIRECT_URI`。请勿再把密钥写进仓库源码。
