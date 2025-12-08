import spotipy
from spotipy.oauth2 import SpotifyOAuth

# --- Configuration ---
SPOTIPY_CLIENT_ID = '46f8721f46e744cbb55391627aaa7d63'
SPOTIPY_CLIENT_SECRET = '4516266ea3cc4a53ab7b175cbc2ba41e'
# Use the recommended loopback IP address for the redirect URI
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8888/callback'
SCOPE = "user-read-currently-playing"

sp = None

def initialize_spotify():
    """Initializes the Spotify client."""
    global sp
    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE,
            open_browser=False
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        if not auth_manager.get_cached_token():
            auth_url = auth_manager.get_authorize_url()
            print(f"Spotify requires authorization. Please visit this URL:\n{auth_url}")
        
        sp.current_user()
        print("Spotify client initialized successfully.")
        return True
    except Exception as e:
        print(f"Error initializing Spotify: {e}")
        return False

def get_current_spotify_song():
    """
    Fetches the currently playing song from Spotify.
    Returns (song, artist, album_art_url) tuple or None.
    """
    if not sp: return None

    try:
        current_track = sp.current_user_playing_track()
        if current_track and current_track['is_playing']:
            item = current_track['item']
            song_name = item['name']
            artist_name = ', '.join(artist['name'] for artist in item['artists'])
            
            album_art_url = item['album']['images'][0]['url'] if item['album']['images'] else None
            
            return song_name, artist_name, album_art_url
        else:
            return None
    except Exception as e:
        print(f"Error fetching Spotify song: {e}")
        return None
