import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
import json # Import json for pretty printing

# --- Configuration ---
SPOTIPY_CLIENT_ID = '46f8721f46e744cbb55391627aaa7d63'
SPOTIPY_CLIENT_SECRET = '4516266ea3cc4a53ab7b175cbc2ba41e'
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8888/callback'
SCOPE = "user-read-currently-playing"

sp = None

def initialize_spotify():
    """Initializes the Spotify client."""
    global sp
    print("SpotifyDetector: Attempting to initialize Spotify client...")
    try:
        cache_path = os.path.join(os.getcwd(), '.spotify_cache')
        
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE,
            open_browser=False,
            cache_path=cache_path
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        token_info = auth_manager.get_access_token(check_cache=True)

        if not token_info:
            if 'YOUR_SPOTIFY_CLIENT_ID' in SPOTIPY_CLIENT_ID:
                print("\n!!! ERROR: Please paste your actual Spotify Client ID and Secret into spotify_detector.py !!!\n")
                return False
            
            auth_url = auth_manager.get_authorize_url()
            print(f"Spotify requires authorization. Please visit this URL:\n{auth_url}")
            print("\nAfter authorizing, copy the full URL from your browser's address bar and paste it below.")
            # This part of the flow is manual, so we can't proceed automatically.
            # The main loop will need to handle the re-initialization.
            return False

        sp.current_user()
        print("SpotifyDetector: Spotify client initialized and authenticated successfully.")
        return True
    except Exception as e:
        print(f"SpotifyDetector: ERROR - An exception occurred during initialization: {e}")
        return False

def get_current_spotify_song():
    """
    Fetches the currently playing song from Spotify.
    Returns (song, artist, album_art_url) tuple or None.
    """
    if not sp: 
        return None

    try:
        # --- THE ULTIMATE DIAGNOSTIC ---
        # Get the raw response from the Spotify API
        current_track = sp.current_user_playing_track()
        
        # Print the raw response to see exactly what Spotify is sending us
        print("\n--- Spotify API Raw Response ---")
        print(json.dumps(current_track, indent=2))
        print("--------------------------------\n")
        
        if current_track and current_track.get('is_playing'):
            item = current_track.get('item')
            if item:
                song_name = item.get('name')
                artists = item.get('artists', [])
                artist_name = ', '.join(artist.get('name') for artist in artists)
                
                album = item.get('album', {})
                images = album.get('images', [])
                album_art_url = images[0].get('url') if images else None
                
                return song_name, artist_name, album_art_url
        
        # If we reach here, it means nothing is playing or the structure is unexpected.
        return None
        
    except Exception as e:
        print(f"SpotifyDetector: ERROR - Error fetching Spotify song: {e}")
        return None
