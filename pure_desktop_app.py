import sys
import time
import requests
import certifi
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, 
                               QLabel, QVBoxLayout, QDialog, QLineEdit, 
                               QGroupBox, QRadioButton, QDialogButtonBox)
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt

# Import detector logic
import spotify_detector
from desktop_assistant import get_current_netease_song

# --- Configuration ---
BASE_URL = "https://listeningtogether.onrender.com/"
UPDATE_URL = f"{BASE_URL}update_state"
GET_URL = f"{BASE_URL}get_state"

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
        self.user_label.setFont(self.font())
        self.user_label.setAlignment(Qt.AlignCenter)
        self.song_label = QLabel("...")
        self.song_label.setFont(self.font())
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

# --- NEW POLLING-BASED LOGIC COMPONENTS ---
class SongDetectorWorker(QObject):
    song_detected = Signal(str)
    # --- THE FIX IS HERE ---
    def __init__(self, platform): # Correctly takes one argument from the caller
        super().__init__()
        self.platform = platform
        self._is_running = True
    def run(self):
        if self.platform == 'spotify':
            if not spotify_detector.initialize_spotify(): return
            get_song_function = spotify_detector.get_current_spotify_song
        else:
            get_song_function = get_current_netease_song
        last_song_title = None
        while self._is_running:
            song_info = get_song_function()
            current_song_title = f"{song_info[0]} - {song_info[1]}" if song_info else ""
            if current_song_title != last_song_title:
                last_song_title = current_song_title
                self.song_detected.emit(last_song_title)
            time.sleep(5)
    def stop(self): self._is_running = False

class StateUpdaterWorker(QObject):
    def __init__(self, username, platform):
        super().__init__()
        self.username = username
        self.platform = platform
    @Slot(str)
    def update_song(self, song):
        try:
            payload = {"user": self.username, "song": song, "platform": self.platform}
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

# --- Main Window ---
class RoomWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.seats = []
        self.setWindowTitle("MusicFriend Room (Polling)")
        self.setGeometry(100, 100, 1000, 400)
        container = QWidget()
        self.grid_layout = QGridLayout(container)
        self.setCentralWidget(container)
        self._setup_seats()

    def _setup_seats(self, num_seats=12, cols=4):
        for i in range(num_seats):
            seat = SeatWidget()
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(seat, row, col)
            self.seats.append(seat)

    @Slot(dict)
    def on_state_update(self, room_state):
        occupied_seats = set()
        # Update occupied seats
        for user, data in room_state.items():
            found_seat = False
            for i, seat in enumerate(self.seats):
                if seat.property("occupied") and seat.user_label.text().endswith(user):
                    seat.update_seat(user, data.get('song'), data.get('platform'))
                    occupied_seats.add(i)
                    found_seat = True
                    break
            if not found_seat:
                for i, seat in enumerate(self.seats):
                    if i not in occupied_seats:
                        seat.update_seat(user, data.get('song'), data.get('platform'))
                        occupied_seats.add(i)
                        break
        # Clear unoccupied seats
        for i, seat in enumerate(self.seats):
            if i not in occupied_seats:
                seat.set_empty()
        QApplication.processEvents()

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

    main_window = RoomWindow()
    
    # Create workers
    # --- THE FIX IS HERE ---
    detector = SongDetectorWorker(settings_dialog.platform) # Now correctly passes only one argument
    updater = StateUpdaterWorker(settings_dialog.username, settings_dialog.platform)
    fetcher = StateFetcherWorker()

    # Create and manage threads
    detector_thread = QThread()
    updater_thread = QThread()
    fetcher_thread = QThread()
    detector.moveToThread(detector_thread)
    updater.moveToThread(updater_thread)
    fetcher.moveToThread(fetcher_thread)

    # Connect signals
    detector.song_detected.connect(updater.update_song)
    fetcher.state_updated.connect(main_window.on_state_update)
    detector_thread.started.connect(detector.run)
    fetcher_thread.started.connect(fetcher.run)

    # Graceful shutdown
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

    # Start threads
    detector_thread.start()
    updater_thread.start()
    fetcher_thread.start()
    
    main_window.show()
    sys.exit(app.exec())
