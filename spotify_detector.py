import spotipy
from spotipy.oauth2 import SpotifyOAuth

# --- IMPORTANT ---
# You must create an app in the Spotify Developer Dashboard to get these.
# Dashboard: https://developer.spotify.com/dashboard/
# 1. Create an app.
# 2. Get the Client ID and Client Secret.
# 3. Go to "Edit Settings" and add "http://localhost:8888/callback" as a Redirect URI.
SPOTIPY_CLIENT_ID = '46f8721f46e744cbb55391627aaa7d63'
SPOTIPY_CLIENT_SECRET = '4516266ea3cc4a53ab7b175cbc2ba41e'
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8000/callback'

# This defines what permissions our app is asking for.
# 'user-read-currently-playing' is exactly what we need.
SCOPE = "user-read-currently-playing"

sp = None

def initialize_spotify():
    """Initializes the Spotify client with user authorization."""
    global sp
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        # Try to get user info to force authentication if needed
        sp.current_user() 
        print("Spotify client initialized successfully.")
        return True
    except Exception as e:
        print(f"Error initializing Spotify. Have you filled in your credentials in spotify_detector.py?")
        print(f"Error details: {e}")
        return False

def get_current_spotify_song():
    """
    Fetches the currently playing song from Spotify.
    Returns (song, artist) tuple or None if not playing.
    """
    if not sp:
        return None

    try:
        current_track = sp.current_user_playing_track()
        
        if current_track and current_track['is_playing']:
            item = current_track['item']
            song_name = item['name']
            artist_name = ', '.join(artist['name'] for artist in item['artists'])
            return song_name, artist_name
        else:
            return None
    except Exception as e:
        print(f"Error fetching Spotify song: {e}")
        return None
