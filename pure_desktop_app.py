import sys
import time
import socketio
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, 
                               QLabel, QVBoxLayout, QDialog, QLineEdit, 
                               QGroupBox, QRadioButton, QDialogButtonBox)
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt
from PySide6.QtGui import QFont

# Import detector logic
import spotify_detector
from desktop_assistant import get_current_netease_song

# --- Configuration ---
SERVER_URL = "https://listeningtogether.onrender.com/"

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
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.user_label = QLabel("Empty Seat")
        self.user_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.user_label.setAlignment(Qt.AlignCenter)
        self.song_label = QLabel("...")
        self.song_label.setFont(QFont("Segoe UI", 9))
        self.song_label.setAlignment(Qt.AlignCenter)
        self.song_label.setWordWrap(True)
        layout.addWidget(self.user_label)
        layout.addWidget(self.song_label)
        self.setProperty("occupied", False)

    def update_seat(self, user, song, platform):
        self.setProperty("occupied", True)
        icon = '🟢' if platform == 'spotify' else '🎵'
        self.user_label.setText(f"{icon} {user}")
        self.song_label.setText(song)
        self.style().polish(self)

    def set_empty(self):
        self.setProperty("occupied", False)
        self.user_label.setText("Empty Seat")
        self.song_label.setText("...")
        self.style().polish(self)

# --- Logic Components with Diagnostics ---
class SocketIOManager(QObject):
    connected = Signal()
    disconnected = Signal()
    song_update_received = Signal(dict)

    def __init__(self):
        super().__init__()
        self.sio = socketio.Client(logger=True, engineio_logger=True) # Enable detailed logging
        self.sio.on('connect', self._handle_connect)
        self.sio.on('disconnect', self._handle_disconnect)
        self.sio.on('song_update', self._handle_song_update)

    def connect(self):
        print("DEBUG: SocketIOManager attempting to connect...")
        try:
            self.sio.connect(SERVER_URL)
        except Exception as e:
            print(f"FATAL: Socket.IO connection failed on initial connect: {e}")

    def disconnect(self):
        self.sio.disconnect()

    def send_song_update(self, data):
        print(f"DEBUG: SocketIOManager sending song_update event: {data}")
        self.sio.emit('song_update', data)

    def _handle_connect(self):
        print("DEBUG: Socket.IO 'connect' event received by manager!")
        self.connected.emit()

    def _handle_disconnect(self):
        print("DEBUG: Socket.IO 'disconnect' event received.")
        self.disconnected.emit()

    def _handle_song_update(self, data):
        self.song_update_received.emit(data)

class SongDetectorWorker(QObject):
    status_updated = Signal(str)
    song_detected = Signal(str)

    def __init__(self, platform):
        super().__init__()
        self.platform = platform
        self._is_running = True
        self.get_song_function = None

    def run(self):
        print("DEBUG: SongDetectorWorker.run() method has been called!")
        if self.platform == 'spotify':
            if not spotify_detector.initialize_spotify():
                self.status_updated.emit("Spotify init failed.")
                return
            self.get_song_function = spotify_detector.get_current_spotify_song
        else:
            self.get_song_function = get_current_netease_song
        
        self.status_updated.emit(f"Monitoring {self.platform}...")
        last_song_title = None
        
        print("DEBUG: SongDetectorWorker starting its loop.")
        while self._is_running:
            print(f"DEBUG: Worker loop running... Checking for {self.platform} song.")
            song_info = self.get_song_function()
            if song_info:
                song, artist = song_info
                current_song_title = f"{song} - {artist}"
                if current_song_title != last_song_title:
                    last_song_title = current_song_title
                    self.song_detected.emit(current_song_title)
            time.sleep(5)
        print("DEBUG: SongDetectorWorker loop has finished.")

    def stop(self):
        self._is_running = False

# --- Main Window with Diagnostics ---
class RoomWindow(QMainWindow):
    def __init__(self, username, platform):
        super().__init__()
        self.username = username
        self.platform = platform
        self.seats = []
        self.user_to_seat_map = {}

        self.setWindowTitle("MusicFriend Room (Pure Desktop)")
        self.setGeometry(100, 100, 1000, 400)
        
        container = QWidget()
        self.grid_layout = QGridLayout(container)
        self.setCentralWidget(container)

        self._setup_seats()
        self._setup_logic()

    def _setup_seats(self, num_seats=12, cols=4):
        for i in range(num_seats):
            seat = SeatWidget()
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(seat, row, col)
            self.seats.append(seat)

    def _setup_logic(self):
        self.socket_manager = SocketIOManager()
        self.socket_thread = QThread()
        self.socket_manager.moveToThread(self.socket_thread)
        self.socket_thread.started.connect(self.socket_manager.connect)
        self.socket_manager.song_update_received.connect(self.on_song_update)
        self.socket_thread.start()

        self.detector_worker = SongDetectorWorker(self.platform)
        self.detector_thread = QThread()
        self.detector_worker.moveToThread(self.detector_thread)
        self.detector_worker.song_detected.connect(self.on_local_song_detected)
        self.detector_thread.start()
        
        # Connect the socket manager's success signal to a handler in this window
        self.socket_manager.connected.connect(self.on_socket_connected)

    @Slot()
    def on_socket_connected(self):
        """This slot is called when the socket manager successfully connects."""
        print("DEBUG: RoomWindow received 'connected' signal from SocketIOManager.")
        # Now that we are connected, we can start the song detector worker.
        self.detector_worker.run()

    @Slot(str)
    def on_local_song_detected(self, song_title):
        print(f"DEBUG: RoomWindow received 'song_detected' signal: '{song_title}'. Sending to server.")
        data = {"user": self.username, "song": song_title, "platform": self.platform}
        self.socket_manager.send_song_update(data)

    @Slot(dict)
    def on_song_update(self, data):
        user = data.get('user')
        if user in self.user_to_seat_map:
            seat_index = self.user_to_seat_map[user]
            self.seats[seat_index].update_seat(user, data.get('song'), data.get('platform'))
        else:
            for i, seat in enumerate(self.seats):
                if not seat.property("occupied"):
                    self.user_to_seat_map[user] = i
                    seat.update_seat(user, data.get('song'), data.get('platform'))
                    break
    
    def closeEvent(self, event):
        self.detector_worker.stop()
        self.detector_thread.quit()
        self.detector_thread.wait()
        self.socket_manager.disconnect()
        self.socket_thread.quit()
        self.socket_thread.wait()
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget { background-color: #2c2f33; color: #ffffff; }
        QLabel { background-color: transparent; }
    """)
    
    settings_dialog = SettingsDialog()
    if settings_dialog.exec() == QDialog.Accepted:
        main_window = RoomWindow(settings_dialog.username, settings_dialog.platform)
        main_window.show()
        sys.exit(app.exec())
    else:
        sys.exit(0)
