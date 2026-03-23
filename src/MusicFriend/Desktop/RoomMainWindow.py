"""
主房间窗口：座位卡片、公共聊天、设置弹窗、歌曲检测线程。
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import deque
from typing import Any, Callable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from MusicFriend.Desktop.QtDesignTokens import (
    COLORS,
    album_art_label_stylesheet,
    chat_log_stylesheet,
    muted_label_stylesheet,
    seat_widget_stylesheet,
)
from MusicFriend.Domain.RoomId import isValidRoomId
from MusicFriend.Integrations.NetEaseWindowsProvider import NetEaseWindowsProvider
from MusicFriend.Integrations.SpotifyProvider import SpotifyProvider


class ImageDownloader(QObject):
    """在普通 Python 线程里拉取封面，避免 QThread + 阻塞式 urlopen 无法响应 quit 导致闪退。"""

    image_ready = Signal(QPixmap)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def startInBackground(self, seat: "SeatWidget", generation: int) -> None:
        """daemon 线程下载；generation 与座位上的计数对齐，避免旧请求晚到仍刷新封面。"""

        url = self.url

        def work() -> None:
            try:
                data = urlopen(url, timeout=10).read()
                image = QImage()
                image.loadFromData(data)
                pixmap = QPixmap.fromImage(image)
                if generation != seat._art_download_generation:
                    return
                self.image_ready.emit(pixmap)
            except Exception as e:
                print(f"ImageDownloader: 失败 {e}")

        threading.Thread(target=work, name="MusicFriendArt", daemon=True).start()


class SeatWidget(QWidget):
    def __init__(self, parent=None, *, play_style: bool = False) -> None:
        super().__init__(parent)
        self._play_style = play_style
        if play_style:
            w, h, self._art_px = 400, 118, 96
            self._empty_user_caption = "虚位以待"
        else:
            w, h, self._art_px = 220, 100, 80
            self._empty_user_caption = "空座位"
        self.setFixedSize(w, h)
        self.setStyleSheet(seat_widget_stylesheet())
        main_layout = QHBoxLayout(self)
        self.album_art_label = QLabel()
        self.album_art_label.setFixedSize(self._art_px, self._art_px)
        self.album_art_label.setStyleSheet(album_art_label_stylesheet())
        self.album_art_label.setAlignment(Qt.AlignCenter)
        text_layout = QVBoxLayout()
        self.user_label = QLabel(self._empty_user_caption)
        self.song_label = QLabel("...")
        self.song_label.setWordWrap(True)
        text_layout.addWidget(self.user_label)
        self.song_label.setStyleSheet(f"color: {COLORS['textMedium']}; font-size: 12px; background: transparent;")
        text_layout.addWidget(self.song_label)
        text_layout.addStretch()
        main_layout.addWidget(self.album_art_label)
        main_layout.addLayout(text_layout)
        self.setProperty("occupied", False)
        self.current_art_url: Optional[str] = None
        self.downloader: Optional[ImageDownloader] = None
        # 与房间快照对应的成员 id，用于稳定匹配座位
        self._bound_member_id: Optional[str] = None
        # 每次发起新封面或清理时递增，后台线程比对后可丢弃过期结果
        self._art_download_generation = 0

    def _cleanup_image_downloader(self) -> None:
        """断开封面回调并使进行中的下载结果失效。"""
        self._art_download_generation += 1
        dl = self.downloader
        self.downloader = None
        if dl is not None:
            dl.blockSignals(True)
            try:
                dl.image_ready.disconnect(self.set_album_art)
            except Exception:
                pass
            dl.deleteLater()

    def update_seat(
        self,
        user: str,
        song: str,
        platform: str,
        art_url: Optional[str],
        *,
        member_id: Optional[str] = None,
        is_host: bool = False,
    ) -> None:
        self.setProperty("occupied", True)
        self._bound_member_id = member_id
        icon = "🟢" if platform == "spotify" else "🎵"
        host_tag = " 【房主】" if is_host else ""
        self.user_label.setText(f"{icon} {user}{host_tag}")
        self.song_label.setText(song if song else "已暂停")
        self.style().polish(self)
        if art_url and art_url != self.current_art_url:
            self._cleanup_image_downloader()
            self.current_art_url = art_url
            self.album_art_label.setText("...")
            self.downloader = ImageDownloader(art_url)
            self.downloader.setParent(self)
            self.downloader.image_ready.connect(self.set_album_art, Qt.QueuedConnection)
            self.downloader.startInBackground(self, self._art_download_generation)
        elif not art_url:
            self._cleanup_image_downloader()
            self.set_default_art()

    @Slot(QPixmap)
    def set_album_art(self, pixmap: QPixmap) -> None:
        s = self._art_px
        self.album_art_label.setPixmap(pixmap.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        dl = self.downloader
        self.downloader = None
        if dl is not None:
            try:
                dl.image_ready.disconnect(self.set_album_art)
            except Exception:
                pass
            dl.deleteLater()

    def set_default_art(self) -> None:
        self.current_art_url = None
        self.album_art_label.setText("🎵")
        self.album_art_label.setFont(self.font())

    def set_empty(self) -> None:
        self._cleanup_image_downloader()
        self.setProperty("occupied", False)
        self._bound_member_id = None
        self.user_label.setText(self._empty_user_caption)
        self.song_label.setText("...")
        self.set_default_art()
        self.style().polish(self)


class PlaySeatPanel(QWidget):
    """公共播放位：展示已通过审批的成员曲目，并提供申请入口。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        title = QLabel("播放位")
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        row.addWidget(title)
        self.display = SeatWidget(play_style=True)
        row.addWidget(self.display, stretch=1)
        self.follow_btn = QPushButton("跟播")
        self.follow_btn.setFixedWidth(88)
        row.addWidget(self.follow_btn)
        self.apply_btn = QPushButton("申请")
        self.apply_btn.setFixedWidth(96)
        row.addWidget(self.apply_btn)


class SongDetectorWorker(QObject):
    song_detected = Signal(dict)

    def __init__(self, platform: str) -> None:
        super().__init__()
        self._platform = platform
        self._running = True
        self._spotify: Optional[SpotifyProvider] = None
        self._netease: Optional[NetEaseWindowsProvider] = None
        if platform == "spotify":
            self._spotify = SpotifyProvider()
            if not self._spotify.initialize():
                print("SongDetectorWorker: Spotify 初始化失败，轮询将一直为空")
        else:
            self._netease = NetEaseWindowsProvider()

    @Slot()
    def run(self) -> None:
        while self._running:
            snap = None
            if self._spotify:
                snap = self._spotify.poll()
            elif self._netease:
                snap = self._netease.poll()
            if snap:
                self.song_detected.emit(
                    {
                        "title": snap.title,
                        "artUrl": snap.artUrl,
                        "platform": snap.platform,
                        "externalId": snap.externalId,
                    }
                )
            else:
                self.song_detected.emit(
                    {
                        "title": "",
                        "artUrl": None,
                        "platform": self._platform,
                        "externalId": None,
                    }
                )
            # 可中断等待，避免退出时 QThread.wait 超时后仍运行导致「QThread 仍运行时已被销毁」
            for _ in range(50):
                if not self._running:
                    return
                time.sleep(0.1)

    def stop(self) -> None:
        self._running = False


def _httpBaseToWsBase(http_base: str) -> str:
    """与 RoomWebSocketWorker 一致：HTTP 根地址转为 WebSocket 根（无路径）。"""
    u = http_base.strip().rstrip("/")
    parsed = urlparse(u)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


def _sanitizeRoomId(raw: str) -> str:
    """房间 ID 须为恰好 4 位数字。"""
    s = (raw or "").strip()
    return s if isValidRoomId(s) else ""


def _generateRandomRoomId() -> str:
    """生成 4 位数字房间 id（0000–9999）。"""
    return f"{secrets.randbelow(10000):04d}"


def _roomListHttpOriginForBase(http_base: str) -> str:
    """供 WebSocket Origin 与部分网关校验。"""
    raw = http_base.strip().rstrip("/")
    if "://" not in raw:
        raw = "http://" + raw
    p = urlparse(raw)
    if p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return raw


def _fetchRoomListViaWebsocket(http_base: str, ws_path: str) -> list[dict]:
    """HTTP 不可达时通过 WebSocket 拉取列表；ws_path 如 /ws/room/_list。"""
    import websocket

    ws_root = _httpBaseToWsBase(http_base)
    url = f"{ws_root}{ws_path}"
    origin = _roomListHttpOriginForBase(http_base)
    hdr = ["User-Agent: MusicFriend-Desktop/1.0", f"Origin: {origin}"]
    try:
        ws = websocket.create_connection(url, timeout=10, origin=origin, header=["User-Agent: MusicFriend-Desktop/1.0"])
    except TypeError:
        ws = websocket.create_connection(url, timeout=10, header=hdr)
    try:
        raw = ws.recv()
    finally:
        try:
            ws.close()
        except Exception:
            pass
    data = json.loads(raw)
    rooms = data.get("rooms")
    return rooms if isinstance(rooms, list) else []


def fetchRoomListJsonFromHttpBase(http_base: str) -> list[dict]:
    """从房间服务拉取房间列表（与启动向导内逻辑一致，供桌面主流程与网页桥接复用）。"""
    base = http_base.strip().rstrip("/")
    http_headers = {
        "Accept": "application/json",
        "User-Agent": "MusicFriend-Desktop/1.0",
    }
    http_paths = ["/rooms", "/api/rooms"]
    last_err: Optional[BaseException] = None
    for path in http_paths:
        url = f"{base}{path}"
        req = Request(url, headers=http_headers)
        try:
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            rooms = data.get("rooms")
            if isinstance(rooms, list):
                return rooms
        except HTTPError as e:
            last_err = e
            continue
        except URLError as e:
            last_err = e
            continue
    ws_paths = ["/ws/room/_list", "/ws/directory"]
    parts: list[str] = []
    for wpath in ws_paths:
        try:
            return _fetchRoomListViaWebsocket(base, wpath)
        except Exception as e:
            parts.append(f"{wpath}: {e}")
            last_err = e
    detail = "；".join(parts) if parts else repr(last_err)
    raise RuntimeError(f"已尝试 HTTP {http_paths} 与 WebSocket {ws_paths}，均失败。{detail}") from last_err


class StartupDialog(QDialog):
    """启动向导：基础信息 → 创建房间 / 加入房间。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Music Together — 进入房间")
        self.setModal(True)
        self.setFixedSize(440, 460)
        self.username = ""
        self.platform = ""
        self.server_url = ""
        self.room_id = ""
        self._random_room_id = _generateRandomRoomId()

        root = QVBoxLayout(self)
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # —— 第 0 页：基础信息 + 创建/加入入口 ——
        page0 = QWidget()
        p0 = QVBoxLayout(page0)
        p0.addWidget(QLabel("服务器地址（HTTP）："))
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("http://127.0.0.1:8765")
        p0.addWidget(self.server_input)
        p0.addWidget(QLabel("昵称："))
        self.username_input = QLineEdit()
        p0.addWidget(self.username_input)
        platform_group = QGroupBox("音乐平台")
        platform_layout = QVBoxLayout()
        self.netease_radio = QRadioButton("网易云音乐（仅 Windows）")
        self.spotify_radio = QRadioButton("Spotify")
        self.spotify_radio.setChecked(True)
        platform_layout.addWidget(self.spotify_radio)
        platform_layout.addWidget(self.netease_radio)
        platform_group.setLayout(platform_layout)
        p0.addWidget(platform_group)
        p0.addWidget(QLabel("请选择："))
        row0 = QHBoxLayout()
        btn_create = QPushButton("创建房间")
        btn_join = QPushButton("加入房间")
        row0.addWidget(btn_create)
        row0.addWidget(btn_join)
        p0.addLayout(row0)
        p0.addStretch()
        self._stack.addWidget(page0)
        btn_create.clicked.connect(self._onChooseCreate)
        btn_join.clicked.connect(self._onChooseJoin)

        # —— 第 1 页：创建房间 ——
        page1 = QWidget()
        p1 = QVBoxLayout(page1)
        p1.addWidget(QLabel("创建房间：选择房间 ID 方式"))
        self.create_manual_radio = QRadioButton("手动输入房间 ID")
        self.create_random_radio = QRadioButton("随机生成房间 ID")
        self.create_manual_radio.setChecked(True)
        p1.addWidget(self.create_manual_radio)
        p1.addWidget(self.create_random_radio)
        self.create_room_id_edit = QLineEdit()
        self.create_room_id_edit.setPlaceholderText("例如：1024")
        self.create_room_id_edit.setMaxLength(4)
        p1.addWidget(self.create_room_id_edit)
        self.create_random_label = QLabel()
        self.create_random_label.setStyleSheet(muted_label_stylesheet())
        p1.addWidget(self.create_random_label)
        regen_row = QHBoxLayout()
        self.regen_btn = QPushButton("换一个")
        regen_row.addWidget(self.regen_btn)
        regen_row.addStretch()
        p1.addLayout(regen_row)
        row1 = QHBoxLayout()
        back1 = QPushButton("返回")
        ok1 = QPushButton("进入房间")
        row1.addWidget(back1)
        row1.addWidget(ok1)
        p1.addLayout(row1)
        self._stack.addWidget(page1)
        back1.clicked.connect(self._backToHome)
        ok1.clicked.connect(self._finalizeCreate)
        self.regen_btn.clicked.connect(self._regenerateRandomRoomId)
        self.create_manual_radio.toggled.connect(self._syncCreateIdMode)
        self.create_random_radio.toggled.connect(self._syncCreateIdMode)
        self._syncCreateIdMode()

        # —— 第 2 页：加入房间 ——
        page2 = QWidget()
        p2 = QVBoxLayout(page2)
        p2.addWidget(QLabel("当前服务器上的房间（仅显示有成员在线的）："))
        refresh_row = QHBoxLayout()
        self.refresh_rooms_btn = QPushButton("刷新列表")
        refresh_row.addWidget(self.refresh_rooms_btn)
        refresh_row.addStretch()
        p2.addLayout(refresh_row)
        self.room_list = QListWidget()
        self.room_list.setMinimumHeight(160)
        self.room_list.setSelectionMode(QAbstractItemView.SingleSelection)
        p2.addWidget(self.room_list)
        p2.addWidget(QLabel("或输入房间 ID 定向加入："))
        self.join_room_id_edit = QLineEdit()
        self.join_room_id_edit.setPlaceholderText("4 位数字，例如 1024")
        self.join_room_id_edit.setMaxLength(4)
        p2.addWidget(self.join_room_id_edit)
        row2 = QHBoxLayout()
        back2 = QPushButton("返回")
        ok2 = QPushButton("加入房间")
        row2.addWidget(back2)
        row2.addWidget(ok2)
        p2.addLayout(row2)
        self._stack.addWidget(page2)
        back2.clicked.connect(self._backToHome)
        ok2.clicked.connect(self._finalizeJoin)
        self.refresh_rooms_btn.clicked.connect(self._refreshRoomList)
        self.room_list.itemDoubleClicked.connect(self._onRoomListDoubleClick)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

    def _validateBasics(self) -> bool:
        import sys

        self.username = self.username_input.text().strip()
        self.server_url = self.server_input.text().strip() or "http://127.0.0.1:8765"
        if not self.username:
            self.username_input.setStyleSheet(f"border: 1px solid {COLORS['danger']};")
            return False
        self.username_input.setStyleSheet("")
        if self.netease_radio.isChecked() and sys.platform != "win32":
            self.netease_radio.setStyleSheet(f"color: {COLORS['danger']};")
            return False
        self.netease_radio.setStyleSheet("")
        self.platform = "spotify" if self.spotify_radio.isChecked() else "netease"
        return True

    def _onChooseCreate(self) -> None:
        if not self._validateBasics():
            return
        self._stack.setCurrentIndex(1)

    def _onChooseJoin(self) -> None:
        if not self._validateBasics():
            return
        self._stack.setCurrentIndex(2)
        self._refreshRoomList()

    def _backToHome(self) -> None:
        self._stack.setCurrentIndex(0)

    def _syncCreateIdMode(self) -> None:
        manual = self.create_manual_radio.isChecked()
        self.create_room_id_edit.setEnabled(manual)
        self.create_random_label.setVisible(not manual)
        self.regen_btn.setVisible(not manual)
        if not manual:
            self.create_random_label.setText(f"将使用房间 ID：{self._random_room_id}")

    def _regenerateRandomRoomId(self) -> None:
        self._random_room_id = _generateRandomRoomId()
        self._syncCreateIdMode()

    def _finalizeCreate(self) -> None:
        if self.create_manual_radio.isChecked():
            rid = _sanitizeRoomId(self.create_room_id_edit.text())
            if not rid:
                QMessageBox.warning(self, "创建房间", "房间 ID 必须为恰好 4 位数字（0000–9999）。")
                return
            self.room_id = rid
        else:
            self.room_id = self._random_room_id
        super().accept()

    def _fetchRoomListJson(self) -> list[dict]:
        return fetchRoomListJsonFromHttpBase(self.server_url)

    def _refreshRoomList(self) -> None:
        self.room_list.clear()
        try:
            rooms = self._fetchRoomListJson()
        except Exception as e:
            QMessageBox.warning(self, "房间列表", f"无法获取房间列表：{e}")
            return
        for item in rooms:
            if not isinstance(item, dict):
                continue
            rid = item.get("roomId")
            if not rid:
                continue
            n = item.get("memberCount", 0)
            lw = QListWidgetItem(f"{rid}  （{n} 人在线）")
            lw.setData(Qt.UserRole, str(rid))
            self.room_list.addItem(lw)

    def _onRoomListDoubleClick(self, item: QListWidgetItem) -> None:
        rid = item.data(Qt.UserRole)
        if rid:
            self.join_room_id_edit.setText(str(rid))

    def _finalizeJoin(self) -> None:
        manual = _sanitizeRoomId(self.join_room_id_edit.text())
        if manual:
            self.room_id = manual
            super().accept()
            return
        cur = self.room_list.currentItem()
        if cur is None:
            QMessageBox.information(self, "加入房间", "请从列表选择房间，或在下方输入 4 位数字房间 ID。")
            return
        rid = cur.data(Qt.UserRole)
        if not rid:
            QMessageBox.information(self, "加入房间", "请从列表选择房间，或在下方输入 4 位数字房间 ID。")
            return
        rid_str = str(rid)
        if not isValidRoomId(rid_str):
            QMessageBox.warning(self, "加入房间", "所选房间 ID 无效，请输入 4 位数字。")
            return
        self.room_id = rid_str
        super().accept()


# 兼容旧代码中的类名
SettingsDialog = StartupDialog


class RoomMainWindow(QMainWindow):
    def __init__(
        self,
        display_name: str,
        platform: str,
        http_base: str,
        room_id: str,
        on_send_chat: Optional[Callable[[str], Any]] = None,
        on_request_play_seat: Optional[Callable[[], Any]] = None,
        on_approve_play_seat: Optional[Callable[[str], Any]] = None,
        on_reject_play_seat: Optional[Callable[[str], Any]] = None,
        on_follow_play: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ) -> None:
        super().__init__()
        self._display_name = display_name
        self._platform = platform
        self._http_base = http_base
        self._room_id = room_id
        self._on_send_chat = on_send_chat
        self._on_request_play_seat = on_request_play_seat
        self._on_approve_play_seat = on_approve_play_seat
        self._on_reject_play_seat = on_reject_play_seat
        self._on_follow_play = on_follow_play
        self._follow_play_seat = False
        self._last_applied_follow_external_id: Optional[str] = None
        self._play_seat_track_platform: Optional[str] = None
        self._play_seat_track_external_id: Optional[str] = None
        self._follow_last_error: Optional[str] = None
        # 与服务端回显去重：本地已显示过的「本人消息」不再从 event 追加一行
        self._pending_self_messages: deque[str] = deque(maxlen=32)
        self._self_member_id: Optional[str] = None
        self._last_host_id: Optional[str] = None
        self._last_play_seat_id: Optional[str] = None
        self._play_seat_pending = False
        self.seats: List[SeatWidget] = []
        self.setWindowTitle("Music Together — 共听房间")
        self.setGeometry(100, 80, 1280, 720)
        self.setMinimumSize(960, 560)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        self.hint = QLabel(f"房间: {room_id}  |  用户: {display_name}")
        main_layout.addWidget(self.hint)

        self._play_panel = PlaySeatPanel()
        self._play_panel.apply_btn.clicked.connect(self._try_request_play_seat)
        self._play_panel.follow_btn.clicked.connect(self._on_follow_toggle)
        main_layout.addWidget(self._play_panel)

        body_row = QHBoxLayout()
        seats_container = QWidget()
        self.grid_layout = QGridLayout(seats_container)
        self._setup_seats()
        body_row.addWidget(seats_container, stretch=1)

        # 右侧公共聊天（纯文本，避免 HTML 注入）
        chat_panel = QWidget()
        chat_panel.setFixedWidth(300)
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.addWidget(QLabel("公共聊天"))
        self._chat_log = QPlainTextEdit()
        self._chat_log.setReadOnly(True)
        self._chat_log.setMaximumBlockCount(400)
        self._chat_log.setPlaceholderText("群内消息将显示在这里…")
        self._chat_log.setStyleSheet(chat_log_stylesheet())
        chat_layout.addWidget(self._chat_log)
        input_row = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入消息，回车发送…")
        send_btn = QPushButton("发送")
        input_row.addWidget(self._chat_input)
        input_row.addWidget(send_btn)
        chat_layout.addLayout(input_row)
        send_btn.clicked.connect(self._try_send_chat)
        self._chat_input.returnPressed.connect(self._try_send_chat)
        body_row.addWidget(chat_panel)

        main_layout.addLayout(body_row)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 关闭窗口时先断开封面任务，避免子 QObject 与后台线程竞态
        for seat in self.seats:
            seat._cleanup_image_downloader()
        self._play_panel.display._cleanup_image_downloader()
        super().closeEvent(event)

    def _append_chat_line(self, user_label: str, body: str) -> None:
        """单条展示：用户名：消息（全角冒号）。"""
        self._chat_log.appendPlainText(f"{user_label}：{body}")
        bar = self._chat_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _try_send_chat(self) -> None:
        if not self._on_send_chat:
            return
        text = self._chat_input.text().strip()
        if not text:
            return
        result = self._on_send_chat(text)
        if result is False:
            return
        self._pending_self_messages.append(text)
        self._append_chat_line(self._display_name, text)
        self._chat_input.clear()

    def _setup_seats(self, num_seats: int = 12, cols: int = 3) -> None:
        for i in range(num_seats):
            seat = SeatWidget()
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(seat, row, col)
            self.seats.append(seat)

    @Slot(str)
    def set_self_member_id(self, member_id: str) -> None:
        """服务端分配的 memberId，用于识别房主、播放位与申请状态。"""
        self._self_member_id = member_id or None
        self._update_hint_bar()
        self._sync_follow_button()

    def _update_hint_bar(self) -> None:
        extra = ""
        if self._self_member_id and self._last_host_id and self._self_member_id == self._last_host_id:
            extra = "  |  你是房主"
        self.hint.setText(f"房间: {self._room_id}  |  用户: {self._display_name}{extra}")

    def _try_request_play_seat(self) -> None:
        if not self._on_request_play_seat:
            return
        is_host = (
            self._self_member_id is not None
            and self._last_host_id is not None
            and self._self_member_id == self._last_host_id
        )
        if not is_host:
            self._play_seat_pending = True
            self._sync_play_seat_apply_button()
        ok = self._on_request_play_seat()
        if ok is False and not is_host:
            self._play_seat_pending = False
            self._sync_play_seat_apply_button()

    def _sync_play_seat_apply_button(self) -> None:
        btn = self._play_panel.apply_btn
        if not self._on_request_play_seat:
            btn.setVisible(True)
            btn.setEnabled(False)
            btn.setText("申请")
            return
        self_mid = self._self_member_id
        if not self_mid:
            btn.setVisible(True)
            btn.setEnabled(False)
            btn.setText("申请")
            return
        ps = self._last_play_seat_id
        is_host = self._last_host_id is not None and self_mid == self._last_host_id
        if ps is not None and ps == self_mid:
            btn.setVisible(True)
            btn.setEnabled(False)
            btn.setText("当前在播放位")
            return
        btn.setVisible(True)
        if self._play_seat_pending and not is_host:
            btn.setEnabled(False)
            btn.setText("等待房主确认…")
            return
        btn.setEnabled(True)
        btn.setText("使用播放位" if is_host else "申请")

    def _maybe_follow_play_seat(self, *, show_errors: bool) -> None:
        """在已开启跟播时，尝试将本地播放器切到播放位当前 externalId。"""
        if not self._follow_play_seat or not self._on_follow_play:
            return
        ps = self._last_play_seat_id
        if not ps:
            return
        self_mid = self._self_member_id
        if self_mid and ps == self_mid:
            return
        plat = self._play_seat_track_platform or ""
        if not plat or plat == "unknown" or plat != self._platform:
            return
        ext = (self._play_seat_track_external_id or "").strip()
        if not ext:
            self._last_applied_follow_external_id = None
            return
        if ext == self._last_applied_follow_external_id:
            return
        ok, err = self._on_follow_play(ext)
        if ok:
            self._last_applied_follow_external_id = ext
            self._follow_last_error = None
        else:
            self._follow_last_error = err or "跟播失败"
            if show_errors and err:
                QMessageBox.warning(self, "跟播", err)

    def _sync_follow_button(self) -> None:
        btn = self._play_panel.follow_btn
        if not self._on_follow_play:
            btn.setVisible(False)
            return
        btn.setVisible(True)
        self_mid = self._self_member_id
        ps = self._last_play_seat_id
        if not ps:
            if self._follow_play_seat:
                self._follow_play_seat = False
                self._last_applied_follow_external_id = None
            btn.setEnabled(False)
            btn.setText("跟播")
            btn.setToolTip("当前无人占用播放位。")
            return
        if self_mid and ps == self_mid:
            if self._follow_play_seat:
                self._follow_play_seat = False
                self._last_applied_follow_external_id = None
            btn.setVisible(False)
            return
        btn.setVisible(True)
        seat_plat = self._play_seat_track_platform
        if not seat_plat or seat_plat == "unknown":
            btn.setEnabled(False)
            btn.setText("跟播" if not self._follow_play_seat else "取消跟播")
            btn.setToolTip("暂无法确认播放位的音乐软件，请稍候。")
            return
        if seat_plat != self._platform:
            if self._follow_play_seat:
                self._follow_play_seat = False
                self._last_applied_follow_external_id = None
            btn.setEnabled(False)
            btn.setText("跟播")
            btn.setToolTip("仅支持与播放位相同的音乐软件跟播（无法跨软件）。")
            return
        btn.setEnabled(True)
        if self._follow_play_seat:
            btn.setText("取消跟播")
            tip = "已开启：将随播放位切歌。"
            if self._follow_last_error:
                tip += f" 提示：{self._follow_last_error}"
            btn.setToolTip(tip)
        else:
            btn.setText("跟播")
            btn.setToolTip("在本地播放器中打开播放位当前歌曲，并随其切歌。")

    def _on_follow_toggle(self) -> None:
        if not self._on_follow_play:
            return
        if self._follow_play_seat:
            self._follow_play_seat = False
            self._last_applied_follow_external_id = None
            self._follow_last_error = None
            self._sync_follow_button()
            return
        ps = self._last_play_seat_id
        if not ps:
            QMessageBox.information(self, "跟播", "当前无人占用播放位。")
            return
        if self._self_member_id and ps == self._self_member_id:
            return
        seat_plat = self._play_seat_track_platform
        if not seat_plat or seat_plat == "unknown":
            QMessageBox.information(self, "跟播", "暂无法确认播放位的音乐软件，请稍候再试。")
            return
        if seat_plat != self._platform:
            QMessageBox.information(
                self,
                "跟播",
                "仅支持与播放位使用相同音乐软件时才能跟播，无法跨软件跟播。",
            )
            return
        self._follow_play_seat = True
        self._last_applied_follow_external_id = None
        self._maybe_follow_play_seat(show_errors=True)
        self._sync_follow_button()

    @Slot(dict)
    def on_snapshot(self, payload: dict) -> None:
        members = payload.get("members") or []
        host_raw = payload.get("hostMemberId")
        play_raw = payload.get("playSeatMemberId")
        self._last_host_id = str(host_raw) if host_raw else None
        self._last_play_seat_id = str(play_raw) if play_raw else None
        self._update_hint_bar()

        by_id: dict[str, dict] = {}
        for m in members:
            mid = m.get("memberId")
            if mid:
                by_id[str(mid)] = m

        n = len(self.seats)
        intended: List[Optional[str]] = [None] * n
        for i, seat in enumerate(self.seats):
            bid = seat._bound_member_id
            if bid and bid in by_id:
                intended[i] = bid

        assigned = {mid for mid in intended if mid}
        remaining = [mid for mid in sorted(by_id.keys()) if mid not in assigned]

        ri = 0
        for mid in remaining:
            while ri < n and intended[ri] is not None:
                ri += 1
            if ri < n:
                intended[ri] = mid
                ri += 1

        for i, seat in enumerate(self.seats):
            mid = intended[i]
            if mid and mid in by_id:
                m = by_id[mid]
                track = m.get("track") or {}
                name = (m.get("displayName") or mid).strip()
                is_host = bool(self._last_host_id and self._last_host_id == mid)
                seat.update_seat(
                    name,
                    track.get("title") or "",
                    track.get("platform") or "unknown",
                    track.get("artUrl"),
                    member_id=mid,
                    is_host=is_host,
                )
            else:
                seat.set_empty()

        if self._last_play_seat_id and self._last_play_seat_id in by_id:
            m = by_id[self._last_play_seat_id]
            track = m.get("track") or {}
            name = (m.get("displayName") or self._last_play_seat_id).strip()
            is_host = bool(self._last_host_id and self._last_host_id == self._last_play_seat_id)
            self._play_seat_track_platform = (track.get("platform") or "unknown").strip() or "unknown"
            ex = track.get("externalId")
            self._play_seat_track_external_id = str(ex).strip() if ex else None
            self._play_panel.display.update_seat(
                name,
                track.get("title") or "",
                track.get("platform") or "unknown",
                track.get("artUrl"),
                member_id=self._last_play_seat_id,
                is_host=is_host,
            )
        else:
            self._play_seat_track_platform = None
            self._play_seat_track_external_id = None
            if self._follow_play_seat:
                self._follow_play_seat = False
                self._last_applied_follow_external_id = None
            self._play_panel.display.set_empty()

        if self._follow_play_seat and self._play_seat_track_platform not in (None, "unknown") and self._play_seat_track_platform != self._platform:
            self._follow_play_seat = False
            self._last_applied_follow_external_id = None

        self._sync_play_seat_apply_button()
        self._maybe_follow_play_seat(show_errors=False)
        self._sync_follow_button()

    @Slot(str)
    def on_event(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        evt = payload.get("type")
        if evt == "chatMessageSent":
            inner = payload.get("payload") or {}
            msg = (inner.get("message") or "").strip()
            if not msg:
                return
            name = (inner.get("senderDisplayName") or "").strip() or "未知用户"
            if name == self._display_name and msg in self._pending_self_messages:
                try:
                    self._pending_self_messages.remove(msg)
                except ValueError:
                    pass
                return
            self._append_chat_line(name, msg)
            return
        if evt == "playSeatRequested":
            inner = payload.get("payload") or {}
            req_id = (inner.get("requestId") or "").strip()
            applicant_name = (inner.get("applicantDisplayName") or "").strip() or "某位成员"
            if not req_id:
                return
            answer = QMessageBox.question(
                self,
                "播放位申请",
                f"{applicant_name} 申请占用公共播放位，是否同意？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes and self._on_approve_play_seat:
                self._on_approve_play_seat(req_id)
            elif answer == QMessageBox.No and self._on_reject_play_seat:
                self._on_reject_play_seat(req_id)
            return
        if evt == "playSeatRejected":
            inner = payload.get("payload") or {}
            applicant = inner.get("applicantMemberId")
            if applicant and self._self_member_id and str(applicant) == self._self_member_id:
                self._play_seat_pending = False
                self._sync_play_seat_apply_button()
                QMessageBox.information(self, "播放位", "房主已拒绝你的申请。")
            return
        if evt == "playSeatApproved":
            inner = payload.get("payload") or {}
            target = inner.get("targetMemberId")
            if target and self._self_member_id and str(target) == self._self_member_id:
                self._play_seat_pending = False
                self._sync_play_seat_apply_button()
            return
        if evt == "trackUpdated":
            um = payload.get("memberId")
            ps = self._last_play_seat_id
            if um and ps and str(um) == str(ps):
                inner = payload.get("payload") or {}
                p = inner.get("platform")
                if p is not None:
                    self._play_seat_track_platform = str(p).strip() or "unknown"
                ex = inner.get("externalId")
                if ex is not None:
                    self._play_seat_track_external_id = str(ex).strip() if ex else None
                if self._follow_play_seat and self._play_seat_track_platform not in (None, "unknown") and self._play_seat_track_platform != self._platform:
                    self._follow_play_seat = False
                    self._last_applied_follow_external_id = None
                self._maybe_follow_play_seat(show_errors=False)
                self._sync_follow_button()
            return

