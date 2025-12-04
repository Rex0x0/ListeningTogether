import pyncm
from pyncm.apis import cloudsearch, album
import datetime
import win32gui

def get_current_netease_song():
    """
    Finds the NetEase Cloud Music window and extracts the current song and artist.
    This function is for Windows only.
    """
    try:
        hwnd = win32gui.FindWindow("OrpheusBrowserHost", None)
        if hwnd == 0:
            return None, "NetEase Music client not found. Is it running?"
        
        window_title = win32gui.GetWindowText(hwnd)
        
        if ' - ' in window_title:
            song, artist = window_title.split(' - ', 1)
            return (song.strip(), artist.strip()), None
        else:
            return None, "Could not detect song. Is a song currently playing?"
            
    except Exception as e:
        print(f"Error getting current song: {e}")
        return None, "An error occurred while detecting the song."

def get_track_info(song_name, artist_name):
    """
    Searches for a track and returns a dictionary with its detailed information,
    including the album cover URL.
    """
    keywords = f"{song_name} {artist_name}"
    try:
        search_results = cloudsearch.GetSearchResult(keywords, limit=1, stype=1)
        
        if not search_results or not search_results['result']['songs']:
            return None, f"Could not find '{song_name}' by {artist_name}."

        track = search_results['result']['songs'][0]
        
        album_id = track['al']['id']
        album_info = album.GetAlbumInfo(album_id)
        release_year = "an unknown year"
        if album_info and 'album' in album_info and 'publishTime' in album_info['album']:
            publish_time = album_info['album']['publishTime'] / 1000
            release_year = datetime.datetime.fromtimestamp(publish_time).strftime('%Y')

        track_details = {
            "name": track['name'],
            "artist": ', '.join(artist['name'] for artist in track['ar']),
            "album": track['al']['name'],
            "release_year": release_year,
            "cover_url": track['al']['picUrl'] + "?param=200y200" # Request a 200x200 image
        }
        
        return track_details, None
    except Exception as e:
        print(f"Error searching NetEase Cloud Music: {e}")
        return None, "An error occurred during the search."

def initialize_netease():
    """Initializes the NetEase client."""
    print("NetEase Cloud Music client is ready.")
    return True
