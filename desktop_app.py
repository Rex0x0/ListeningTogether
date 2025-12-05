import sys
import time
import requests
import certifi
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLineEdit, QPushButton, QRadioButton, QLabel, QGroupBox, QToolBar)
from PySide6.QtCore import QThread, QObject, Signal, Slot, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

import spotify_detector
from desktop_assistant import get_current_netease_song

# --- Configuration ---
WEB_APP_URL = "https://listeningtogether.onrender.com/" 
SERVER_URL = f"{WEB_APP_URL}update_song"

# --- Background Worker ---
class Worker(QObject):
    song_changed = Signal(str)
    status_updated = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, username, platform):
        super().__init__()
        self.username = username
        self.platform = platform
        self._is_running = True
        self.get_song_function = None

    def run(self):
        if self.platform == 'spotify':
            if not spotify_detector.initialize_spotify():
                self.error_occurred.emit("Spotify initialization failed. Check credentials.")
                return
            self.get_song_function = spotify_detector.get_current_spotify_song
        else:
            self.get_song_function = get_current_netease_song

        self.status_updated.emit(f"Monitoring {self.platform}...")
        last_song_title = None

        while self._is_running:
            try:
                song_info = self.get_song_function()
                if song_info:
                    song, artist = song_info
                    current_song_title = f"{song} - {artist}"
                    if current_song_title != last_song_title:
                        last_song_title = current_song_title
                        self.song_changed.emit(current_song_title)
                        self.post_to_server(current_song_title)
                else:
                    if last_song_title is not None:
                        self.status_updated.emit("Playback stopped.")
                        last_song_title = None
                time.sleep(5)
            except Exception as e:
                self.error_occurred.emit(f"An error occurred in main loop: {e}")
                time.sleep(10)

    def post_to_server(self, song_title):
        """Sends the song update to the server, with detailed error catching."""
        try:
            payload = {"user": self.username, "song": song_title, "platform": self.platform}
            response = requests.post(SERVER_URL, json=payload, timeout=7, verify=certifi.where())
            
            if response.status_code == 200:
                self.status_updated.emit("Update sent successfully.")
            else:
                # Show the server's response text if the status code is not 200
                self.status_updated.emit(f"Server Error: {response.status_code} - {response.text}")

        except requests.exceptions.RequestException as e:
            # --- THE CRITICAL CHANGE IS HERE ---
            # We now emit the full, detailed error message from the requests library.
            error_message = str(e)
            print(f"--- DETAILED CONNECTION ERROR ---\n{error_message}\n-------------------------------")
            self.error_occurred.emit(f"Connection Failed: {error_message}")

    def stop(self):
        self._is_running = False

# --- Main GUI Window (Unchanged from the last version) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MusicFriend Room")
        self.setGeometry(100, 100, 1280, 720)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        self.toolbar = QToolBar("Controls")
        self.addToolBar(self.toolbar)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter Nickname")
        self.toolbar.addWidget(QLabel("Nickname: "))
        self.toolbar.addWidget(self.username_input)
        self.toolbar.addSeparator()

        self.netease_radio = QRadioButton("NetEase")
        self.spotify_radio = QRadioButton("Spotify")
        self.netease_radio.setChecked(True)
        self.toolbar.addWidget(self.netease_radio)
        self.toolbar.addWidget(self.spotify_radio)
        self.toolbar.addSeparator()

        self.start_button = QPushButton("Start Syncing")
        self.stop_button = QPushButton("Stop Syncing")
        self.stop_button.setEnabled(False)
        self.toolbar.addWidget(self.start_button)
        self.toolbar.addWidget(self.stop_button)
        self.toolbar.addSeparator()
        
        self.status_label = QLabel("Status: Idle")
        self.toolbar.addWidget(self.status_label)

        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(WEB_APP_URL))
        main_layout.addWidget(self.browser)

        self.start_button.clicked.connect(self.start_worker)
        self.stop_button.clicked.connect(self.stop_worker)

        self.thread = None
        self.worker = None

    def start_worker(self):
        username = self.username_input.text().strip()
        if not username:
            self.status_label.setText("Status: Nickname required!")
            return

        platform = 'spotify' if self.spotify_radio.isChecked() else 'netease'
        
        self.thread = QThread()
        self.worker = Worker(username, platform)
        self.worker.moveToThread(self.thread)

        self.worker.status_updated.connect(self.update_status_label)
        self.worker.error_occurred.connect(self.show_error)
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.set_controls_enabled(False)
        self.status_label.setText("Status: Starting...")

    def stop_worker(self):
        if self.worker: self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.set_controls_enabled(True)
        self.status_label.setText("Status: Stopped.")

    def set_controls_enabled(self, enabled):
        self.start_button.setEnabled(enabled)
        self.stop_button.setEnabled(not enabled)
        self.username_input.setEnabled(enabled)
        self.netease_radio.setEnabled(enabled)
        self.spotify_radio.setEnabled(enabled)

    @Slot(str)
    def update_status_label(self, status):
        self.status_label.setText(f"Status: {status}")

    @Slot(str)
    def show_error(self, error_text):
        # This will now display the detailed error from the worker
        self.status_label.setText(f"Status: {error_text}")
        self.stop_worker()

    def closeEvent(self, event):
        self.stop_worker()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
