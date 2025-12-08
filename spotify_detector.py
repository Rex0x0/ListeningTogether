import spotipy
from spotipy.oauth2 import SpotifyOAuth

# --- Configuration (Ensure these are filled) ---
SPOTIPY_CLIENT_ID = 'YOUR_SPOTIFY_CLIENT_ID'
SPOTIPY_CLIENT_SECRET = 'YOUR_SPOTIFY_CLIENT_SECRET'
SPOTIPY_REDIRECT_URI = 'http://localhost:8888/callback'
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
            open_browser=False # Don't automatically open browser
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        # Check if we have a cached token, if not, get auth url
        if not auth_manager.get_cached_token():
            auth_url = auth_manager.get_authorize_url()
            print(f"Spotify requires authorization. Please visit this URL:\n{auth_url}")
            # The user needs to paste the callback URL back into the console.
            # This is a limitation of console apps.
        
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
            
            # --- THE NEW PART: Get Album Art URL ---
            # item['album']['images'] is a list of images in different sizes.
            # We'll grab the first one, which is usually the largest (640x640).
            # We can choose a smaller one if needed, e.g., images[1] (300x300) or images[2] (64x64).
            album_art_url = item['album']['images'][0]['url'] if item['album']['images'] else None
            
            return song_name, artist_name, album_art_url
        else:
            return None
    except Exception as e:
        print(f"Error fetching Spotify song: {e}")
        return None
