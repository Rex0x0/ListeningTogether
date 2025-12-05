import sys
import time
import requests
import certifi
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QThread, QObject, Signal, Slot, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage # Import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel # Import QWebChannel

# Import our existing detector logic
import spotify_detector
from desktop_assistant import get_current_netease_song

# --- Configuration ---
WEB_APP_URL = "https://listeningtogether.onrender.com/" 
SERVER_URL = f"{WEB_APP_URL}update_song"

# --- Background Worker (Unchanged) ---
class Worker(QObject):
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
                self.error_occurred.emit("Spotify initialization failed.")
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
                        self.post_to_server(current_song_title)
                else:
                    if last_song_title is not None:
                        self.status_updated.emit("Playback stopped.")
                        last_song_title = None
                time.sleep(5)
            except Exception as e:
                self.error_occurred.emit(f"Error in main loop: {e}")
                time.sleep(10)

    def post_to_server(self, song_title):
        try:
            payload = {"user": self.username, "song": song_title, "platform": self.platform}
            response = requests.post(SERVER_URL, json=payload, timeout=7, verify=certifi.where())
            if response.status_code == 200:
                self.status_updated.emit("Update sent successfully.")
            else:
                self.status_updated.emit(f"Server Error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Connection Failed: {e}")

    def stop(self):
        self._is_running = False

# --- Python-JS Bridge ---
class Bridge(QObject):
    # Signal to be emitted when JS calls the start_sync slot
    # It will carry the username and platform string
    sync_started = Signal(str, str)

    @Slot(str, str)
    def start_sync(self, username, platform):
        """This method is callable from JavaScript."""
        print(f"Bridge: Received start_sync call from JS with user: {username}, platform: {platform}")
        self.sync_started.emit(username, platform)

# --- Main GUI Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MusicFriend Room")
        self.setGeometry(100, 100, 1280, 720)

        # --- Web Engine View Setup ---
        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)

        # --- WebChannel Setup ---
        self.channel = QWebChannel()
        self.bridge = Bridge() # Create our Python bridge object
        self.channel.registerObject("qt_bridge", self.bridge) # Expose it to JS as "qt_bridge"
        self.browser.page().setWebChannel(self.channel)

        # Load the web page
        self.browser.setUrl(QUrl(WEB_APP_URL))

        # --- Worker Thread Management ---
        self.thread = None
        self.worker = None

        # Connect the signal from the bridge to our worker-starting slot
        self.bridge.sync_started.connect(self.on_sync_start_requested)

    @Slot(str, str)
    def on_sync_start_requested(self, username, platform):
        """This slot is called when the Bridge emits the sync_started signal."""
        print(f"MainWindow: Starting worker for user '{username}' on platform '{platform}'")
        # Stop any existing worker before starting a new one
        if self.thread and self.thread.isRunning():
            self.stop_worker()

        self.thread = QThread()
        self.worker = Worker(username, platform)
        self.worker.moveToThread(self.thread)

        # You can connect worker signals to slots here if you want to display status in the title, etc.
        # For example: self.worker.status_updated.connect(self.update_window_title)
        
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def stop_worker(self):
        if self.worker: self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        print("MainWindow: Worker stopped.")

    def closeEvent(self, event):
        self.stop_worker()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
