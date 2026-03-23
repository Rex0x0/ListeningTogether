import sys
import time
import requests
import certifi
import socketio
import os # Import os

# --- THE FIX: Disable proxies for this script ---
# This forces requests and socketio to bypass any system proxies
# which often cause timeouts in Python scripts.
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, 
                               QLabel, QVBoxLayout, QDialog, QLineEdit, 
                               QGroupBox, QRadioButton, QDialogButtonBox, QHBoxLayout, 
                               QTextEdit, QPushButton, QSplitter)
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt, QMetaObject, Q_ARG
from PySide6.QtGui import QPixmap, QImage, QFont
from urllib.request import urlopen

# Import detector logic
import spotify_detector
import netease_api_utils
from desktop_assistant import get_current_netease_song

# --- Configuration ---
BASE_URL = "https://listeningtogether.onrender.com/"
UPDATE_URL = f"{BASE_URL}update_state"
GET_URL = f"{BASE_URL}get_state"

# --- Image Downloader (Unchanged) ---
class ImageDownloader(QObject):
    image_ready = Signal(QPixmap)
    def __init__(self, url):
        super().__init__()
        self.url = url
    @Slot()
    def run(self):
        try:
            data = urlopen(self.url).read()
            image = QImage()
            image.loadFromData(data)
            pixmap = QPixmap.fromImage(image)
            self.image_ready.emit(pixmap)
        except Exception as e:
            print(f"Image download failed: {e}")

# --- UI Components (Unchanged) ---
class SeatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 100)
        self.setStyleSheet("""
            SeatWidget { background-color: #40444b; border-radius: 10px; border: 2px solid #40444b; }
            SeatWidget[occupied="false"] { background-color: transparent; border: 2px dashed #5c6067; }
            SeatWidget[occupied="true"] { border-color: #7289da; }
        """)
        main_layout = QHBoxLayout(self)
        self.album_art_label = QLabel()
        self.album_art_label.setFixedSize(80, 80)
        self.album_art_label.setStyleSheet("background-color: #333; border-radius: 5px;")
        self.album_art_label.setAlignment(Qt.AlignCenter)
        text_layout = QVBoxLayout()
        self.user_label = QLabel("Empty Seat")
        self.song_label = QLabel("...")
        self.song_label.setWordWrap(True)
        text_layout.addWidget(self.user_label)
        text_layout.addWidget(self.song_label)
        text_layout.addStretch()
        main_layout.addWidget(self.album_art_label)
        main_layout.addLayout(text_layout)
        self.setProperty("occupied", False)
        self.current_art_url = None
        self.downloader_thread = None

    def update_seat(self, user, song, platform, art_url):
        self.setProperty("occupied", True)
        icon = '🟢' if platform == 'spotify' else '🎵'
        self.user_label.setText(f"{icon} {user}")
        self.song_label.setText(song if song else "Playback Paused")
        self.style().polish(self)
        if art_url and art_url != self.current_art_url:
            self.current_art_url = art_url
            self.album_art_label.setText("...")
            self.downloader = ImageDownloader(art_url)
            self.downloader_thread = QThread()
            self.downloader.moveToThread(self.downloader_thread)
            self.downloader.image_ready.connect(self.set_album_art)
            self.downloader_thread.started.connect(self.downloader.run)
            self.downloader_thread.start()
        elif not art_url:
            self.set_default_art()

    def set_album_art(self, pixmap):
        self.album_art_label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.downloader_thread:
            self.downloader_thread.quit()
            self.downloader_thread.wait()

    def set_default_art(self):
        self.current_art_url = None
        self.album_art_label.setText("🎵")
        self.album_art_label.setFont(self.font())

    def set_empty(self):
        self.setProperty("occupied", False)
        self.user_label.setText("Empty Seat")
        self.song_label.setText("...")
        self.set_default_art()
        self.style().polish(self)

# --- Logic Components ---
class SongDetectorWorker(QObject):
    song_detected = Signal(dict)
    def __init__(self, platform):
        super().__init__()
        self.platform = platform
        self._is_running = True
    def run(self):
        last_song_title = None
        current_art_url = None
        while self._is_running:
            song_data = {"song": "", "art_url": None}
            if self.platform == 'spotify':
                song_info = spotify_detector.get_current_spotify_song()
                if song_info:
                    song, artist, art_url = song_info
                    song_data = {"song": f"{song} - {artist}", "art_url": art_url}
            else: # netease
                song_info = get_current_netease_song()
                if song_info:
                    song, artist = song_info
                    current_song_title = f"{song} - {artist}"
                    if current_song_title != last_song_title:
                        last_song_title = current_song_title
                        current_art_url = netease_api_utils.get_netease_album_art_url(song, artist)
                    song_data = {"song": current_song_title, "art_url": current_art_url}
                else:
                    last_song_title = None
                    current_art_url = None
            
            self.song_detected.emit(song_data)
            time.sleep(5)
    def stop(self): self._is_running = False

class StateUpdaterWorker(QObject):
    def __init__(self, username, platform):
        super().__init__()
        self.username = username
        self.platform = platform
    @Slot(dict)
    def update_song(self, song_data):
        try:
            payload = {
                "user": self.username,
                "song": song_data.get("song"),
                "platform": self.platform,
                "art_url": song_data.get("art_url")
            }
            requests.post(UPDATE_URL, json=payload, timeout=5, verify=certifi.where())
        except requests.RequestException as e:
            print(f"Update failed: {e}")

class StateFetcherWorker(QObject):
    state_updated = Signal(dict)
    def __init__(self):
        super().__init__()
        self._is_running = True
    def run(self):
        while self._is_running:
            try:
                response = requests.get(GET_URL, timeout=5, verify=certifi.where())
                if response.status_code == 200:
                    self.state_updated.emit(response.json())
            except requests.RequestException as e:
                print(f"Fetch failed: {e}")
            time.sleep(5)
    def stop(self): self._is_running = False

# --- Chat Manager with Reconnection Logic ---
class ChatManager(QObject):
    message_received = Signal(str, str)

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.sio = socketio.Client(logger=True, engineio_logger=True, reconnection=True, reconnection_attempts=5, reconnection_delay=1)
        self.sio.on('connect', self._handle_connect)
        self.sio.on('disconnect', self._handle_disconnect)
        self.sio.on('new_message', self._handle_new_message)

    def connect(self):
        print("ChatManager: Attempting to connect...")
        try:
            self.sio.connect(BASE_URL, transports=['websocket'], wait_timeout=10)
        except Exception as e:
            print(f"ChatManager: Connection failed: {e}")

    def disconnect(self):
        self.sio.disconnect()

    @Slot(str)
    def send_message(self, message):
        print(f"ChatManager: Sending message: {message}")
        if self.sio.connected:
            data = {'user': self.username, 'message': message}
            self.sio.emit('send_message', data)
        else:
            print("ChatManager: Cannot send, socket not connected. Trying to reconnect...")
            self.connect()

    def _handle_connect(self):
        print("ChatManager: Connected to server!")

    def _handle_disconnect(self):
        print("ChatManager: Disconnected from server.")

    def _handle_new_message(self, data):
        print(f"ChatManager: Received new_message event: {data}")
        user = data.get('user')
        message = data.get('message')
        if user and message:
            self.message_received.emit(user, message)

# --- Main Window (Unchanged) ---
class RoomWindow(QMainWindow):
    def __init__(self, username, platform):
        super().__init__()
        self.username = username
        self.platform = platform
        self.seats = []
        self.setWindowTitle("MusicFriend Room (Polling + Chat)")
        self.setGeometry(100, 100, 1200, 600)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        seats_container = QWidget()
        self.grid_layout = QGridLayout(seats_container)
        self._setup_seats()
        
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("background-color: #202225; border: none; padding: 10px;")
        
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        self.chat_input.setStyleSheet("background-color: #40444b; border: none; padding: 8px; border-radius: 5px;")
        self.chat_input.returnPressed.connect(self.send_chat_message)
        
        send_button = QPushButton("Send")
        send_button.setStyleSheet("background-color: #7289da; border-radius: 5px; padding: 8px;")
        send_button.clicked.connect(self.send_chat_message)
        
        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(send_button)
        
        chat_layout.addWidget(QLabel("Room Chat"))
        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(input_layout)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(seats_container)
        splitter.addWidget(chat_container)
        splitter.setStretchFactor(0, 2) 
        splitter.setStretchFactor(1, 1) 
        
        main_layout.addWidget(splitter)

        self.chat_manager = ChatManager(self.username)
        self.chat_thread = QThread()
        self.chat_manager.moveToThread(self.chat_thread)
        self.chat_manager.message_received.connect(self.on_chat_message_received, Qt.QueuedConnection)
        self.chat_thread.started.connect(self.chat_manager.connect)
        self.chat_thread.start()

    def _setup_seats(self, num_seats=12, cols=3):
        for i in range(num_seats):
            seat = SeatWidget()
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(seat, row, col)
            self.seats.append(seat)

    @Slot()
    def send_chat_message(self):
        message = self.chat_input.text().strip()
        if message:
            print(f"RoomWindow: User typed message: {message}")
            QMetaObject.invokeMethod(self.chat_manager, "send_message", Qt.QueuedConnection, Q_ARG(str, message))
            self.chat_input.clear()

    @Slot(str, str)
    def on_chat_message_received(self, user, message):
        print(f"RoomWindow: Updating UI with message from {user}")
        timestamp = time.strftime("%H:%M")
        formatted_msg = f"<span style='color: #aaa;'>[{timestamp}]</span> <b>{user}:</b> {message}"
        self.chat_display.append(formatted_msg)

    @Slot(dict)
    def on_state_update(self, room_state):
        occupied_seats = set()
        user_to_seat_map = {}
        for user, data in room_state.items():
            found_seat = False
            for i, seat in enumerate(self.seats):
                if seat.property("occupied") and seat.user_label.text().endswith(user):
                    seat.update_seat(user, data.get('song'), data.get('platform'), data.get('art_url'))
                    occupied_seats.add(i)
                    user_to_seat_map[user] = i
                    found_seat = True
                    break
            if not found_seat: pass
        for user, data in room_state.items():
            if user not in user_to_seat_map:
                for i, seat in enumerate(self.seats):
                    if i not in occupied_seats:
                        seat.update_seat(user, data.get('song'), data.get('platform'), data.get('art_url'))
                        occupied_seats.add(i)
                        user_to_seat_map[user] = i
                        break
        for i, seat in enumerate(self.seats):
            if i not in occupied_seats:
                seat.set_empty()
        QApplication.processEvents()
    
    def closeEvent(self, event):
        self.chat_manager.disconnect()
        self.chat_thread.quit()
        self.chat_thread.wait()
        event.accept()

# --- Settings Dialog (Unchanged) ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MusicFriend Setup")
        self.setModal(True)
        self.setFixedSize(300, 200)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter your nickname:"))
        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)
        platform_group = QGroupBox("Select Music Platform")
        platform_layout = QVBoxLayout()
        self.netease_radio = QRadioButton("NetEase Cloud Music")
        self.spotify_radio = QRadioButton("Spotify")
        self.netease_radio.setChecked(True)
        platform_layout.addWidget(self.netease_radio)
        platform_layout.addWidget(self.spotify_radio)
        platform_group.setLayout(platform_layout)
        layout.addWidget(platform_group)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.username = ""
        self.platform = ""
    def accept(self):
        self.username = self.username_input.text().strip()
        if not self.username:
            self.username_input.setStyleSheet("border: 1px solid red;")
            return
        self.platform = 'spotify' if self.spotify_radio.isChecked() else 'netease'
        super().accept()

# --- Main Application Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget { background-color: #2c2f33; color: #ffffff; } QLabel { background-color: transparent; }")
    settings_dialog = SettingsDialog()
    if settings_dialog.exec() != QDialog.Accepted:
        sys.exit(0)
    
    main_window = RoomWindow(settings_dialog.username, settings_dialog.platform)
    
    detector = SongDetectorWorker(settings_dialog.platform)
    updater = StateUpdaterWorker(settings_dialog.username, settings_dialog.platform)
    fetcher = StateFetcherWorker()
    detector_thread = QThread()
    updater_thread = QThread()
    fetcher_thread = QThread()
    detector.moveToThread(detector_thread)
    updater.moveToThread(updater_thread)
    fetcher.moveToThread(fetcher_thread)
    detector.song_detected.connect(updater.update_song)
    fetcher.state_updated.connect(main_window.on_state_update)
    detector_thread.started.connect(detector.run)
    fetcher_thread.started.connect(fetcher.run)
    def on_about_to_quit():
        detector.stop()
        fetcher.stop()
        detector_thread.quit()
        updater_thread.quit()
        fetcher_thread.quit()
        detector_thread.wait()
        updater_thread.wait()
        fetcher_thread.wait()
    app.aboutToQuit.connect(on_about_to_quit)
    detector_thread.start()
    updater_thread.start()
    fetcher_thread.start()
    main_window.show()
    sys.exit(app.exec())
