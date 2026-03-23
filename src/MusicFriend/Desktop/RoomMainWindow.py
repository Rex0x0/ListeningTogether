"""
主房间窗口：座位卡片、设置弹窗、歌曲检测线程。
首迭代不含公共聊天 UI（协议层已预留）。
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from urllib.request import urlopen

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
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(220, 100)
        self.setStyleSheet(
            """
            SeatWidget { background-color: #40444b; border-radius: 10px; border: 2px solid #40444b; }
            SeatWidget[occupied="false"] { background-color: transparent; border: 2px dashed #5c6067; }
            SeatWidget[occupied="true"] { border-color: #7289da; }
        """
        )
        main_layout = QHBoxLayout(self)
        self.album_art_label = QLabel()
        self.album_art_label.setFixedSize(80, 80)
        self.album_art_label.setStyleSheet("background-color: #333; border-radius: 5px;")
        self.album_art_label.setAlignment(Qt.AlignCenter)
        text_layout = QVBoxLayout()
        self.user_label = QLabel("空座位")
        self.song_label = QLabel("...")
        self.song_label.setWordWrap(True)
        text_layout.addWidget(self.user_label)
        text_layout.addWidget(self.song_label)
        text_layout.addStretch()
        main_layout.addWidget(self.album_art_label)
        main_layout.addLayout(text_layout)
        self.setProperty("occupied", False)
        self.current_art_url: Optional[str] = None
        self.downloader: Optional[ImageDownloader] = None
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

    def update_seat(self, user: str, song: str, platform: str, art_url: Optional[str]) -> None:
        self.setProperty("occupied", True)
        icon = "🟢" if platform == "spotify" else "🎵"
        self.user_label.setText(f"{icon} {user}")
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
        self.album_art_label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
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
        self.user_label.setText("空座位")
        self.song_label.setText("...")
        self.set_default_art()
        self.style().polish(self)


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
                    {"title": snap.title, "artUrl": snap.artUrl, "platform": snap.platform}
                )
            else:
                self.song_detected.emit({"title": "", "artUrl": None, "platform": self._platform})
            # 可中断等待，避免退出时 QThread.wait 超时后仍运行导致「QThread 仍运行时已被销毁」
            for _ in range(50):
                if not self._running:
                    return
                time.sleep(0.1)

    def stop(self) -> None:
        self._running = False


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MusicFriend 设置")
        self.setModal(True)
        self.setFixedSize(360, 260)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("服务器地址（HTTP）："))
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("http://127.0.0.1:8765")
        layout.addWidget(self.server_input)
        layout.addWidget(QLabel("昵称："))
        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)
        platform_group = QGroupBox("音乐平台")
        platform_layout = QVBoxLayout()
        self.netease_radio = QRadioButton("网易云音乐（仅 Windows）")
        self.spotify_radio = QRadioButton("Spotify")
        self.spotify_radio.setChecked(True)
        platform_layout.addWidget(self.spotify_radio)
        platform_layout.addWidget(self.netease_radio)
        platform_group.setLayout(platform_layout)
        layout.addWidget(platform_group)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.username = ""
        self.platform = ""
        self.server_url = ""

    def accept(self) -> None:
        import sys

        self.username = self.username_input.text().strip()
        self.server_url = self.server_input.text().strip() or "http://127.0.0.1:8765"
        if not self.username:
            self.username_input.setStyleSheet("border: 1px solid red;")
            return
        if self.netease_radio.isChecked() and sys.platform != "win32":
            self.netease_radio.setStyleSheet("color: red;")
            return
        self.platform = "spotify" if self.spotify_radio.isChecked() else "netease"
        super().accept()


class RoomMainWindow(QMainWindow):
    def __init__(
        self,
        display_name: str,
        platform: str,
        http_base: str,
        room_id: str,
    ) -> None:
        super().__init__()
        self._display_name = display_name
        self._platform = platform
        self._http_base = http_base
        self._room_id = room_id
        self.seats: List[SeatWidget] = []
        self.setWindowTitle("MusicFriend 房间（WebSocket）")
        self.setGeometry(100, 100, 900, 520)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        self.hint = QLabel(f"房间: {room_id}  |  用户: {display_name}")
        main_layout.addWidget(self.hint)
        seats_container = QWidget()
        self.grid_layout = QGridLayout(seats_container)
        self._setup_seats()
        main_layout.addWidget(seats_container)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 关闭窗口时先断开封面任务，避免子 QObject 与后台线程竞态
        for seat in self.seats:
            seat._cleanup_image_downloader()
        super().closeEvent(event)

    def _setup_seats(self, num_seats: int = 12, cols: int = 3) -> None:
        for i in range(num_seats):
            seat = SeatWidget()
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(seat, row, col)
            self.seats.append(seat)

    @Slot(dict)
    def on_snapshot(self, payload: dict) -> None:
        members = payload.get("members") or []
        by_name: dict[str, dict] = {}
        for m in members:
            name = (m.get("displayName") or m.get("memberId") or "").strip()
            if name:
                by_name[name] = m
        occupied: set[int] = set()
        user_to_seat: dict[str, int] = {}
        for i, seat in enumerate(self.seats):
            if not seat.property("occupied"):
                continue
            text = seat.user_label.text()
            for name in by_name:
                if text.endswith(name):
                    track = by_name[name].get("track") or {}
                    seat.update_seat(
                        name,
                        track.get("title") or "",
                        track.get("platform") or "unknown",
                        track.get("artUrl"),
                    )
                    occupied.add(i)
                    user_to_seat[name] = i
                    break
        for name, data in by_name.items():
            if name in user_to_seat:
                continue
            track = data.get("track") or {}
            for i, seat in enumerate(self.seats):
                if i not in occupied:
                    seat.update_seat(
                        name,
                        track.get("title") or "",
                        track.get("platform") or "unknown",
                        track.get("artUrl"),
                    )
                    occupied.add(i)
                    user_to_seat[name] = i
                    break
        for i, seat in enumerate(self.seats):
            if i not in occupied:
                seat.set_empty()

    @Slot(dict)
    def on_event(self, payload: dict) -> None:
        # 首迭代以 snapshot 为主；事件可用于后续增量 UI
        _ = payload

