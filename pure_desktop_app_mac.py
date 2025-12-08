import sys
import time
import requests
import certifi
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout, 
                               QLabel, QVBoxLayout, QDialog, QLineEdit, 
                               QDialogButtonBox, QHBoxLayout)
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt
from PySide6.QtGui import QPixmap, QImage
from urllib.request import urlopen

# Only import the cross-platform detector
import spotify_detector

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
        # In this Mac version, the icon will always be for Spotify
        icon = '🟢' 
        self.user_label.setText(f"{icon} {user}")
        self.song_label.setText(song if song else "Playback Paused")
        self.style().polish(self)
        if art_url and art_url != self.current_art_url:
            self.current_art_url = art_url
            self.album_art_label.setText("...")
            self.downloader = ImageDownloader(art_url)
            self.downloader_thread = QThread()
            self.downloader.moveToThread(self.downloader_thread)
            self.downloader.image_ready.connect(self.set_album_art, Qt.QueuedConnection)
            self.downloader_thread.started.connect(self.downloader.run)
            self.downloader_thread.start()
        elif not art_url:
            self.set_default_art()

    @Slot(QPixmap)
    def set_album_art(self, pixmap):
        if not pixmap.isNull():
            self.album_art_label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.downloader_thread:
            self.downloader_thread.quit()
            self.downloader_thread.wait()

    def set_default_art(self):
        self.current_art_url = None
        self.album_art_label.setText("🟢") # Default icon is Spotify
        self.album_art_label.setFont(self.font())

    def set_empty(self):
        self.setProperty("occupied", False)
        self.user_label.setText("Empty Seat")
        self.song_label.setText("...")
        self.set_default_art()
        self.style().polish(self)

# --- Logic Components (macOS - Spotify Only) ---
class SongDetectorWorker(QObject):
    song_detected = Signal(dict)
    def __init__(self):
        super().__init__()
        self._is_running = True
    def run(self):
        if not spotify_detector.initialize_spotify(): return
        get_song_function = spotify_detector.get_current_spotify_song
        
        while self._is_running:
            song_data = {"song": "", "art_url": None}
            song_info = get_song_function()
            if song_info:
                song, artist, art_url = song_info
                song_data = {"song": f"{song} - {artist}", "art_url": art_url}
            
            self.song_detected.emit(song_data)
            time.sleep(5)
    def stop(self): self._is_running = False

class StateUpdaterWorker(QObject):
    def __init__(self, username):
        super().__init__()
        self.username = username
    @Slot(dict)
    def update_song(self, song_data):
        try:
            payload = {
                "user": self.username,
                "song": song_data.get("song"),
                "platform": "spotify", # Always Spotify for Mac version
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

# --- Main Window (Unchanged) ---
class RoomWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.seats = []
        self.setWindowTitle("MusicFriend Room (macOS)")
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

# --- Settings Dialog (macOS - Spotify Only) ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MusicFriend Setup")
        self.setModal(True)
        self.setFixedSize(300, 150) # Smaller height as there's no choice
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter your nickname:"))
        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)
        
        info_label = QLabel("This version syncs with Spotify.")
        info_label.setStyleSheet("font-style: italic; color: #aaa;")
        layout.addWidget(info_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.username = ""
    def accept(self):
        self.username = self.username_input.text().strip()
        if not self.username:
            self.username_input.setStyleSheet("border: 1px solid red;")
            return
        super().accept()

# --- Main Application Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget { background-color: #2c2f33; color: #ffffff; } QLabel { background-color: transparent; }")
    
    settings_dialog = SettingsDialog()
    if settings_dialog.exec() != QDialog.Accepted:
        sys.exit(0)

    main_window = RoomWindow()
    
    # Create workers for macOS (Spotify only)
    detector = SongDetectorWorker()
    updater = StateUpdaterWorker(settings_dialog.username)
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
