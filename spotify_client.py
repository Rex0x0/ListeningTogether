import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- IMPORTANT ---
# Replace with your own Spotify API credentials
# You can get these from the Spotify Developer Dashboard:
# https://developer.spotify.com/dashboard/
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

spotify = None

def initialize_spotify():
    """Initializes the Spotify client."""
    global spotify
    if CLIENT_ID == "YOUR_CLIENT_ID" or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("Warning: Spotify Client ID and Secret are not set.")
        print("Please update them in spotify_client.py")
        return False
    
    try:
        client_credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
        return True
    except Exception as e:
        print(f"Error initializing Spotify: {e}")
        return False

def get_track_info(song_name, artist_name):
    """Searches for a track and returns its information."""
    if not spotify:
        if not initialize_spotify():
            return "Error: Spotify client not initialized. Please set your credentials."

    query = f"track:{song_name} artist:{artist_name}"
    results = spotify.search(q=query, type='track', limit=1)

    if not results['tracks']['items']:
        return f"Could not find '{song_name}' by {artist_name}."

    track = results['tracks']['items'][0]
    
    # Extract relevant information
    track_name = track['name']
    artists = ', '.join(artist['name'] for artist in track['artists'])
    album_name = track['album']['name']
    release_date = track['album']['release_date']
    popularity = track['popularity'] # A number from 0 to 100

    # Format the commentary
    commentary = (
        f"Song: {track_name}\n"
        f"Artist(s): {artists}\n"
        f"Album: {album_name}\n"
        f"Released: {release_date}\n"
        f"Popularity Score: {popularity}/100\n\n"
        f"This seems to be a popular one! '{track_name}' from the album '{album_name}' is a great track. "
        f"Released in {release_date.split('-')[0]}, it has made quite an impact."
    )
    
    return commentary
