# Use the correct library name and functions
from pyncm import apis

def get_netease_album_art_url(song_name, artist_name):
    """
    Searches for a song on NetEase Cloud Music and returns the album art URL.
    
    Args:
        song_name (str): The name of the song.
        artist_name (str): The name of the artist.
        
    Returns:
        str: The URL of the album art, or None if not found.
    """
    query = f"{song_name} {artist_name}"
    print(f"Netease API: Searching for '{query}'...")
    
    try:
        # Use the 'cloudsearch' API for searching songs
        search_result = apis.cloudsearch.GetSearchResult(query, stype=1, limit=1)
        
        if search_result and search_result.get('result', {}).get('songs'):
            first_song = search_result['result']['songs'][0]
            
            # The album art URL is in the 'al' (album) dictionary under 'picUrl'
            if 'al' in first_song and 'picUrl' in first_song['al']:
                art_url = first_song['al']['picUrl']
                # Netease sometimes returns http links, let's upgrade them to https for safety
                if art_url.startswith('http://'):
                    art_url = art_url.replace('http://', 'https://', 1)
                print(f"Netease API: Found album art URL: {art_url}")
                return art_url
        
        print("Netease API: No songs or album art found for the query.")
        return None
            
    except Exception as e:
        print(f"An error occurred while searching NetEase API: {e}")
        return None

if __name__ == '__main__':
    # Example usage for testing
    test_song = "七里香"
    test_artist = "周杰伦"
    url = get_netease_album_art_url(test_song, test_artist)
    
    if url:
        print(f"\nSuccessfully found URL for '{test_song}': {url}")
    else:
        print(f"\nCould not find album art for '{test_song}'.")
